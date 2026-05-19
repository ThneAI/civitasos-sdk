from __future__ import annotations

import json
from io import BytesIO
from typing import Any
from urllib.error import HTTPError

import pytest

from civitasos import CivitasAgent, CivitasAPIError


class _Response:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


def test_authenticate_prefers_server_challenge(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    def fake_urlopen(req: Any, timeout: int = 10) -> _Response:
        payload = json.loads(req.data.decode("utf-8"))
        calls.append((req.full_url, payload))
        if req.full_url.endswith("/api/v1/auth/challenge"):
            return _Response(
                {
                    "success": True,
                    "data": {
                        "challenge_id": "auth-ch-1",
                        "message": "63697669746173",
                        "message_encoding": "hex",
                    },
                }
            )
        if req.full_url.endswith("/api/v1/auth/token"):
            assert payload["challenge_id"] == "auth-ch-1"
            assert payload["message"] == "63697669746173"
            assert len(payload["signature"]) == 128
            return _Response(
                {
                    "success": True,
                    "data": {
                        "token": "jwt-challenge",
                        "expires_in": 3600,
                        "auth_method": "did_signature_challenge",
                        "production_allowed": False,
                        "evidence_allowed": True,
                    },
                }
            )
        raise AssertionError(f"unexpected URL: {req.full_url}")

    monkeypatch.setattr("civitasos._core.urlopen", fake_urlopen)

    agent = CivitasAgent(base_url="http://backend", auto_discover=False)
    agent.generate_keys()
    agent._agent_id = "did:civ:devnet:test"

    assert agent.authenticate(allow_legacy_fallback=False) == "jwt-challenge"
    assert [url.rsplit("/", 1)[-1] for url, _ in calls] == ["challenge", "token"]
    assert agent.jwt_auth_context == {
        "auth_method": "did_signature_challenge",
        "production_allowed": False,
        "evidence_allowed": True,
    }


def test_authenticate_service_token_stores_scope_context(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    def fake_urlopen(req: Any, timeout: int = 10) -> _Response:
        payload = json.loads(req.data.decode("utf-8"))
        calls.append((req.full_url, payload))
        assert req.full_url == "http://backend/api/v1/auth/service-token"
        return _Response(
            {
                "success": True,
                "data": {
                    "token": "service-jwt",
                    "expires_in": 3600,
                    "auth_method": "service_token",
                    "service_id": payload["service_id"],
                    "scopes": payload["scopes"],
                    "role": "operator",
                    "production_allowed": False,
                    "evidence_allowed": False,
                    "non_claims": [
                        "service_token_is_controlled_operator_automation_only",
                        "service_token_does_not_prove_agent_did_control",
                    ],
                },
            }
        )

    monkeypatch.setattr("civitasos._core.urlopen", fake_urlopen)

    agent = CivitasAgent(base_url="http://backend", auto_discover=False)

    assert (
        agent.authenticate_service_token(
            service_id="runtime_birth_bootstrap",
            secret="service-secret",
            scopes=["agents:read", "agents:write"],
        )
        == "service-jwt"
    )
    assert calls == [
        (
            "http://backend/api/v1/auth/service-token",
            {
                "service_id": "runtime_birth_bootstrap",
                "secret": "service-secret",
                "scopes": ["agents:read", "agents:write"],
            },
        )
    ]
    assert agent.jwt_auth_context["auth_method"] == "service_token"
    assert agent.jwt_auth_context["service_id"] == "runtime_birth_bootstrap"
    assert agent.jwt_auth_context["scopes"] == ["agents:read", "agents:write"]
    assert agent.jwt_auth_context["evidence_allowed"] is False


def test_authenticate_falls_back_only_when_challenge_unavailable(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    def fake_urlopen(req: Any, timeout: int = 10) -> _Response:
        payload = json.loads(req.data.decode("utf-8"))
        calls.append((req.full_url, payload))
        if req.full_url.endswith("/api/v1/auth/challenge"):
            raise HTTPError(req.full_url, 404, "Not Found", {}, BytesIO(b"{}"))
        if req.full_url.endswith("/api/v1/auth/token"):
            assert "challenge_id" not in payload
            return _Response(
                {
                    "success": True,
                    "data": {
                        "token": "jwt-legacy",
                        "auth_method": "did_signature_legacy_message",
                        "evidence_allowed": False,
                    },
                }
            )
        raise AssertionError(f"unexpected URL: {req.full_url}")

    monkeypatch.setattr("civitasos._core.urlopen", fake_urlopen)

    agent = CivitasAgent(base_url="http://backend", auto_discover=False)
    agent.generate_keys()
    agent._agent_id = "did:civ:devnet:test"

    assert agent.authenticate() == "jwt-legacy"
    assert [url.rsplit("/", 1)[-1] for url, _ in calls] == ["challenge", "token"]
    assert agent.jwt_auth_context["auth_method"] == "did_signature_legacy_message"
    assert agent.jwt_auth_context["evidence_allowed"] is False


def test_authenticate_does_not_downgrade_after_challenge_token_failure(monkeypatch) -> None:
    calls: list[str] = []

    def fake_urlopen(req: Any, timeout: int = 10) -> _Response:
        calls.append(req.full_url)
        if req.full_url.endswith("/api/v1/auth/challenge"):
            return _Response(
                {
                    "success": True,
                    "data": {
                        "challenge_id": "auth-ch-1",
                        "message": "63697669746173",
                    },
                }
            )
        if req.full_url.endswith("/api/v1/auth/token"):
            raise HTTPError(
                req.full_url,
                404,
                "Not Found",
                {},
                BytesIO(b'{"error":"invalid or expired auth challenge"}'),
            )
        raise AssertionError(f"unexpected URL: {req.full_url}")

    monkeypatch.setattr("civitasos._core.urlopen", fake_urlopen)

    agent = CivitasAgent(base_url="http://backend", auto_discover=False)
    agent.generate_keys()
    agent._agent_id = "did:civ:devnet:test"

    with pytest.raises(CivitasAPIError, match="invalid or expired auth challenge"):
        agent.authenticate()
    assert [url.rsplit("/", 1)[-1] for url in calls] == ["challenge", "token"]
