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
