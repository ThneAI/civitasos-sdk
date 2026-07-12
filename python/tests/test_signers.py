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

    class PrivateKey:
        def sign(self, message, *, mechanism):
            calls["sign"] = (message, mechanism)
            return b"s" * 64

    class Session:
        def get_key(self, **kwargs):
            calls["get_key"] = kwargs
            return PrivateKey()

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
        "ab" * 32,
        "1234",
        pkcs11_module=FakePkcs11,
    ) as signer:
        assert signer.sign(b"challenge") == b"s" * 64

    assert calls["get_key"] == {"object_class": "private", "label": "agent-key"}
    assert calls["sign"] == (b"challenge", "eddsa")
    assert calls["closed"] is True
