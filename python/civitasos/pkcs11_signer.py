"""PKCS#11-backed Ed25519 service identity provider."""

from __future__ import annotations

from threading import RLock

from .models import CivitasError


class Pkcs11Ed25519Signer:
    """Ed25519 signer backed by a non-exportable PKCS#11 private key."""

    def __init__(
        self,
        module_path: str,
        token_label: str,
        key_label: str,
        public_key_hex: str | None = None,
        user_pin: str | None = None,
        *,
        key_id: bytes | str | None = None,
        pkcs11_module=None,
    ):
        if not module_path or not token_label or not key_label:
            raise CivitasError("PKCS#11 module, token label, and key label are required")
        normalized_key_id = self._normalize_key_id(key_id)
        if normalized_key_id is None:
            raise CivitasError("PKCS#11 key ID is required for unambiguous selection")
        if pkcs11_module is None:
            try:
                import pkcs11 as pkcs11_module
            except ImportError as error:
                raise CivitasError(
                    "Pkcs11Ed25519Signer requires the 'hardware' SDK extra"
                ) from error
        self._pkcs11 = pkcs11_module
        self._lock = RLock()
        self._session = None
        self._private_key = None
        self._module_path = module_path
        self._token_label = token_label
        self._key_label = key_label
        self._key_id = normalized_key_id
        try:
            library = pkcs11_module.lib(module_path)
            token = library.get_token(token_label=token_label)
            self._session = token.open(user_pin=user_pin)
            selector = {
                "label": key_label,
                "id": normalized_key_id,
            }
            self._private_key = self._session.get_key(
                object_class=pkcs11_module.ObjectClass.PRIVATE_KEY,
                **selector,
            )
            public_key = self._session.get_key(
                object_class=pkcs11_module.ObjectClass.PUBLIC_KEY,
                **selector,
            )
            token_public_key = self._decode_ed25519_point(
                bytes(public_key[pkcs11_module.Attribute.EC_POINT])
            )
            if public_key_hex is not None:
                expected_public_key = self._decode_public_key_hex(public_key_hex)
                if token_public_key != expected_public_key:
                    raise CivitasError(
                        "PKCS#11 public key does not match the selected token key"
                    )
            self._public_key_hex = token_public_key.hex()
        except Exception as error:
            try:
                self.close()
            except Exception:
                pass
            if isinstance(error, CivitasError):
                raise
            raise CivitasError(f"PKCS#11 key initialization failed: {error}") from error

    @staticmethod
    def _normalize_key_id(key_id: bytes | str | None) -> bytes | None:
        if key_id is None:
            return None
        if isinstance(key_id, str):
            try:
                key_id = bytes.fromhex(key_id)
            except ValueError as error:
                raise CivitasError("PKCS#11 key ID must be valid hex") from error
        if not isinstance(key_id, bytes) or not key_id:
            raise CivitasError("PKCS#11 key ID must be non-empty bytes or hex")
        return key_id

    @staticmethod
    def _decode_public_key_hex(public_key_hex: str) -> bytes:
        try:
            public_key = bytes.fromhex(public_key_hex)
        except ValueError as error:
            raise CivitasError("PKCS#11 public key must be valid hex") from error
        if len(public_key) != 32:
            raise CivitasError("PKCS#11 Ed25519 public key must be 32 bytes")
        return public_key

    @staticmethod
    def _decode_ed25519_point(encoded_point: bytes) -> bytes:
        if len(encoded_point) == 32:
            return encoded_point
        if len(encoded_point) == 34 and encoded_point[:2] == b"\x04\x20":
            return encoded_point[2:]
        raise CivitasError(
            f"Unsupported PKCS#11 Ed25519 EC_POINT encoding ({len(encoded_point)} bytes)"
        )

    @property
    def public_key_hex(self) -> str:
        return self._public_key_hex

    @property
    def key_reference(self) -> dict[str, str | None]:
        """Return the non-secret PKCS#11 inventory reference for this signer."""
        return {
            "provider": "pkcs11",
            "module_path": self._module_path,
            "token_label": self._token_label,
            "key_label": self._key_label,
            "key_id_hex": self._key_id.hex() if self._key_id is not None else None,
        }

    @property
    def private_key_exportable(self) -> bool:
        return False

    def sign(self, message: bytes) -> bytes:
        if not isinstance(message, bytes):
            raise CivitasError("PKCS#11 signer message must be bytes")
        with self._lock:
            if self._private_key is None:
                raise CivitasError("PKCS#11 signer is closed")
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
        with self._lock:
            session = self._session
            self._session = None
            self._private_key = None
            if session is not None:
                session.close()

    def __enter__(self) -> "Pkcs11Ed25519Signer":
        return self

    def __exit__(self, *_args) -> None:
        self.close()
