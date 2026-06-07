from __future__ import annotations

from civitasos import CivitasAgent


def test_csp_memory_keys_are_url_encoded(monkeypatch) -> None:
    agent = CivitasAgent(
        "http://core.invalid",
        auto_discover=False,
        cognitive_provider={"url": "http://csp.invalid", "services": ["memory"]},
    )
    agent._agent_id = "did:civ:devnet:zAgent"  # noqa: SLF001
    calls = []

    def fake_request(method, path, body=None):
        calls.append((method, path, body))
        return {"value": {"ok": True}}

    monkeypatch.setattr(agent, "_csp_request", fake_request)
    key = "relation_expectation:rel|did:a->did:b|predicted"

    agent.remember(key, {"ok": True})
    assert agent.recall(key) == {"ok": True}
    agent.forget(key)

    assert [call[1] for call in calls] == [
        "/memory/did%3Aciv%3Adevnet%3AzAgent/"
        "relation_expectation%3Arel%7Cdid%3Aa-%3Edid%3Ab%7Cpredicted",
        "/memory/did%3Aciv%3Adevnet%3AzAgent/"
        "relation_expectation%3Arel%7Cdid%3Aa-%3Edid%3Ab%7Cpredicted",
        "/memory/did%3Aciv%3Adevnet%3AzAgent/"
        "relation_expectation%3Arel%7Cdid%3Aa-%3Edid%3Ab%7Cpredicted",
    ]
