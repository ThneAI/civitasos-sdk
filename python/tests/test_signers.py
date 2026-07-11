import pytest
from nacl.signing import SigningKey, VerifyKey

from civitasos import CallbackSigner, CivitasAgent, CivitasError, SoftwareEd25519Signer


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
