import pytest
from nacl.signing import SigningKey, VerifyKey

from civitasos import (
    CallbackSigner,
    CivitasAgent,
    CivitasError,
    Pkcs11Ed25519Signer,
    SoftwareEd25519Signer,
)


def test_software_signer_preserves_legacy_key_api():
    agent = CivitasAgent(auto_discover=False)
    public_key = agent.generate_keys()
    signature = bytes.fromhex(agent.sign(b"challenge"))
    VerifyKey(bytes.fromhex(public_key)).verify(b"challenge", signature)
    assert agent._signing_key is not None


def test_callback_signer_auth_contract_is_non_exportable(tmp_path):
    hardware_key = SigningKey.generate()
    signer = CallbackSigner(
        hardware_key.verify_key.encode().hex(),
        lambda message: hardware_key.sign(message).signature,
    )
    agent = CivitasAgent(auto_discover=False)
    assert agent.set_signer(signer) == signer.public_key_hex
    signature = bytes.fromhex(agent.sign(b"hardware-challenge"))
    hardware_key.verify_key.verify(b"hardware-challenge", signature)
    assert agent._signing_key is None
    with pytest.raises(CivitasError, match="non-exportable"):
        agent.save_identity(str(tmp_path / "identity.json"))


def test_callback_signer_rejects_invalid_signature_length():
    signer = CallbackSigner("ab" * 32, lambda _message: b"short")
    agent = CivitasAgent(auto_discover=False)
    agent.set_signer(signer)
    with pytest.raises(CivitasError, match="64-byte"):
        agent.sign(b"challenge")


def test_software_signer_seed_round_trip():
    signer = SoftwareEd25519Signer.generate()
    restored = SoftwareEd25519Signer.from_seed_hex(signer.export_seed_hex())
    assert restored.public_key_hex == signer.public_key_hex


def test_pkcs11_ed25519_signer_uses_private_key_and_eddsa_mechanism():
    calls = {}
    public_key = bytes.fromhex("ab" * 32)

    class PrivateKey:
        def sign(self, message, *, mechanism):
            calls["sign"] = (message, mechanism)
            return b"s" * 64

    class PublicKey:
        def __getitem__(self, attribute):
            assert attribute == "ec_point"
            return b"\x04\x20" + public_key

    class Session:
        def get_key(self, **kwargs):
            calls.setdefault("get_key", []).append(kwargs)
            return PrivateKey() if kwargs["object_class"] == "private" else PublicKey()

        def close(self):
            calls["closed"] = True

    class Token:
        def open(self, *, user_pin):
            calls["pin"] = user_pin
            return Session()

    class Library:
        def get_token(self, *, token_label):
            calls["token_label"] = token_label
            return Token()

    class FakePkcs11:
        class ObjectClass:
            PRIVATE_KEY = "private"
            PUBLIC_KEY = "public"

        class Attribute:
            EC_POINT = "ec_point"

        class Mechanism:
            EDDSA = "eddsa"

        @staticmethod
        def lib(path):
            calls["module"] = path
            return Library()

    with Pkcs11Ed25519Signer(
        "/opt/token.so",
        "civitas-token",
        "agent-key",
        None,
        "1234",
        key_id="01ab",
        pkcs11_module=FakePkcs11,
    ) as signer:
        assert signer.public_key_hex == public_key.hex()
        assert signer.key_reference == {
            "provider": "pkcs11",
            "module_path": "/opt/token.so",
            "token_label": "civitas-token",
            "key_label": "agent-key",
            "key_id_hex": "01ab",
        }
        assert signer.private_key_exportable is False
        assert signer.sign(b"challenge") == b"s" * 64

    signer.close()
    with pytest.raises(CivitasError, match="closed"):
        signer.sign(b"challenge")

    assert calls["get_key"] == [
        {"object_class": "private", "label": "agent-key", "id": b"\x01\xab"},
        {"object_class": "public", "label": "agent-key", "id": b"\x01\xab"},
    ]
    assert calls["sign"] == (b"challenge", "eddsa")
    assert calls["closed"] is True


def test_pkcs11_ed25519_signer_rejects_mismatched_public_key_and_closes_session():
    closed = False

    class Key:
        def __getitem__(self, _attribute):
            return b"\x04\x20" + bytes.fromhex("ab" * 32)

    class Session:
        def get_key(self, **_kwargs):
            return Key()

        def close(self):
            nonlocal closed
            closed = True

    class Token:
        def open(self, **_kwargs):
            return Session()

    class Library:
        def get_token(self, **_kwargs):
            return Token()

    class FakePkcs11:
        class ObjectClass:
            PRIVATE_KEY = "private"
            PUBLIC_KEY = "public"

        class Attribute:
            EC_POINT = "ec_point"

        @staticmethod
        def lib(_path):
            return Library()

    with pytest.raises(CivitasError, match="does not match"):
        Pkcs11Ed25519Signer(
            "/opt/token.so",
            "civitas-token",
            "agent-key",
            "cd" * 32,
            "1234",
            key_id="01",
            pkcs11_module=FakePkcs11,
        )

    assert closed is True


def test_pkcs11_signer_requires_key_id_before_loading_module():
    with pytest.raises(CivitasError, match="key ID is required"):
        Pkcs11Ed25519Signer(
            "/missing/module.so",
            "civitas-token",
            "agent-key",
            None,
            "1234",
        )


def test_agent_never_falls_back_to_software_when_hardware_signing_fails():
    class FailingHardwareSigner:
        public_key_hex = "ab" * 32
        private_key_exportable = False

        @staticmethod
        def sign(_message: bytes) -> bytes:
            raise CivitasError("hardware token unavailable")

    agent = CivitasAgent(auto_discover=False)
    agent.set_signer(FailingHardwareSigner())

    with pytest.raises(CivitasError, match="hardware token unavailable"):
        agent.sign(b"challenge")
    assert agent._signing_key is None
    assert agent._signer.__class__ is FailingHardwareSigner
