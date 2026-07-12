"""Signing abstractions for software, hardware, and WebAuthn-backed identities."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, runtime_checkable

from nacl.encoding import HexEncoder
from nacl.signing import SigningKey

from .models import CivitasError


@runtime_checkable
class Signer(Protocol):
    """Minimal Ed25519 signer contract used by CivitasOS challenge auth."""

    @property
    def public_key_hex(self) -> str: ...

    def sign(self, message: bytes) -> bytes: ...


class SoftwareEd25519Signer:
    """Legacy exportable Ed25519 seed adapter."""

    def __init__(self, signing_key: SigningKey):
        self._signing_key = signing_key

    @classmethod
    def generate(cls) -> "SoftwareEd25519Signer":
        return cls(SigningKey.generate())

    @classmethod
    def from_seed_hex(cls, seed_hex: str) -> "SoftwareEd25519Signer":
        try:
            seed = bytes.fromhex(seed_hex)
        except ValueError as error:
            raise CivitasError("Seed must be valid hex") from error
        if len(seed) != 32:
            raise CivitasError(f"Seed must be 32 bytes, got {len(seed)}")
        return cls(SigningKey(seed))

    @property
    def public_key_hex(self) -> str:
        return self._signing_key.verify_key.encode(encoder=HexEncoder).decode("ascii")

    def sign(self, message: bytes) -> bytes:
        return self._signing_key.sign(message).signature

    def export_seed_hex(self) -> str:
        return bytes(self._signing_key).hex()

    @property
    def signing_key(self) -> SigningKey:
        """Compatibility access for callers migrating from the legacy SDK field."""
        return self._signing_key


class CallbackSigner:
    """Non-exportable adapter for a hardware/WebAuthn bridge callback."""

    def __init__(self, public_key_hex: str, sign_callback: Callable[[bytes], bytes | str]):
        try:
            public_key = bytes.fromhex(public_key_hex)
        except ValueError as error:
            raise CivitasError("Signer public key must be valid hex") from error
        if len(public_key) != 32:
            raise CivitasError(f"Signer public key must be 32 bytes, got {len(public_key)}")
        self._public_key_hex = public_key_hex.lower()
        self._sign_callback = sign_callback

    @property
    def public_key_hex(self) -> str:
        return self._public_key_hex

    def sign(self, message: bytes) -> bytes:
        signature = self._sign_callback(message)
        if isinstance(signature, str):
            try:
                signature = bytes.fromhex(signature)
            except ValueError as error:
                raise CivitasError("Signer callback returned invalid signature hex") from error
        if not isinstance(signature, bytes) or len(signature) != 64:
            length = len(signature) if isinstance(signature, bytes) else "non-bytes"
            raise CivitasError(f"Signer callback must return a 64-byte Ed25519 signature, got {length}")
        return signature


class Pkcs11Ed25519Signer:
    """Ed25519 signer backed by a non-exportable PKCS#11 private key."""

    def __init__(
        self,
        module_path: str,
        token_label: str,
        key_label: str,
        public_key_hex: str,
        user_pin: str | None = None,
        *,
        pkcs11_module=None,
    ):
        try:
            public_key = bytes.fromhex(public_key_hex)
        except ValueError as error:
            raise CivitasError("PKCS#11 public key must be valid hex") from error
        if len(public_key) != 32:
            raise CivitasError("PKCS#11 Ed25519 public key must be 32 bytes")
        if not module_path or not token_label or not key_label:
            raise CivitasError("PKCS#11 module, token label, and key label are required")
        if pkcs11_module is None:
            try:
                import pkcs11 as pkcs11_module
            except ImportError as error:
                raise CivitasError(
                    "Pkcs11Ed25519Signer requires the 'hardware' SDK extra"
                ) from error
        self._public_key_hex = public_key_hex.lower()
        self._pkcs11 = pkcs11_module
        try:
            library = pkcs11_module.lib(module_path)
            token = library.get_token(token_label=token_label)
            self._session = token.open(user_pin=user_pin)
            self._private_key = self._session.get_key(
                object_class=pkcs11_module.ObjectClass.PRIVATE_KEY,
                label=key_label,
            )
        except Exception as error:
            raise CivitasError(f"PKCS#11 key initialization failed: {error}") from error

    @property
    def public_key_hex(self) -> str:
        return self._public_key_hex

    def sign(self, message: bytes) -> bytes:
        if not isinstance(message, bytes):
            raise CivitasError("PKCS#11 signer message must be bytes")
        try:
            signature = bytes(
                self._private_key.sign(message, mechanism=self._pkcs11.Mechanism.EDDSA)
            )
        except Exception as error:
            raise CivitasError(f"PKCS#11 Ed25519 signing failed: {error}") from error
        if len(signature) != 64:
            raise CivitasError(
                f"PKCS#11 Ed25519 signature must be 64 bytes, got {len(signature)}"
            )
        return signature

    def close(self) -> None:
        self._session.close()

    def __enter__(self) -> "Pkcs11Ed25519Signer":
        return self

    def __exit__(self, *_args) -> None:
        self.close()
