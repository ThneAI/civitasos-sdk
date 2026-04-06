"""
CivitasOS Python SDK — auto-generated client library.

Usage:
    from civitasos_client import CivitasOS

    client = CivitasOS("http://127.0.0.1:8099")
    status = client.status()
    agents = client.list_agents()
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from urllib import request as _req
from urllib.error import HTTPError


@dataclass
class CivitasOS:
    """CivitasOS REST API client (stdlib-only, no external deps)."""

    base_url: str
    """Base URL of the CivitasOS backend, e.g. ``http://127.0.0.1:8099``."""

    api_key: Optional[str] = None
    """Optional API key for tenant authentication."""

    timeout: int = 30
    """Request timeout in seconds."""

    # ── helpers ────────────────────────────────────────────────────────────

    def _url(self, path: str) -> str:
        return f"{self.base_url.rstrip('/')}/api/v1{path}"

    def _headers(self) -> Dict[str, str]:
        h: Dict[str, str] = {"Content-Type": "application/json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        if self.api_key:
            h["X-API-Key"] = self.api_key
        return h

    def _request(self, method: str, path: str, body: Any = None) -> Any:
        data = json.dumps(body).encode() if body is not None else None
        req = _req.Request(
            self._url(path),
            data=data,
            headers=self._headers(),
            method=method,
        )
        try:
            with _req.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read())
        except HTTPError as e:
            err_body = e.read().decode() if e.fp else ""
            raise RuntimeError(f"HTTP {e.code}: {err_body}") from e

    def _get(self, path: str) -> Any:
        return self._request("GET", path)

    def _post(self, path: str, body: Any = None) -> Any:
        return self._request("POST", path, body)

    def _put(self, path: str, body: Any = None) -> Any:
        return self._request("PUT", path, body)

    def _delete(self, path: str) -> Any:
        return self._request("DELETE", path)

    # ── System ────────────────────────────────────────────────────────────

    def status(self) -> dict:
        """GET /api/v1/status"""
        return self._get("/status")

    def health(self) -> dict:
        """GET /healthz"""
        return self._request("GET", "/healthz".replace("/api/v1", ""))

    def openapi(self) -> dict:
        """GET /api/v1/openapi.json"""
        return self._get("/openapi.json")

    # ── Agents ────────────────────────────────────────────────────────────

    def list_agents(self) -> dict:
        """GET /api/v1/agents"""
        return self._get("/agents")

    def register_agent(
        self,
        agent_id: str,
        name: str,
        capabilities: Optional[List[str]] = None,
        stake: float = 100.0,
    ) -> dict:
        """POST /api/v1/agents"""
        return self._post(
            "/agents",
            {
                "id": agent_id,
                "name": name,
                "capabilities": capabilities or [],
                "initial_stake": stake,
            },
        )

    def agent_state(self, agent_id: str) -> dict:
        """GET /api/v1/agents/:id/state"""
        return self._get(f"/agents/{agent_id}/state")

    def agent_learn(self, agent_id: str, data: str) -> dict:
        """POST /api/v1/agents/:id/learn"""
        return self._post(f"/agents/{agent_id}/learn", {"data": data})

    # ── Governance ────────────────────────────────────────────────────────

    def create_proposal(
        self,
        title: str,
        description: str,
        proposer: str,
        template_id: Optional[str] = None,
    ) -> dict:
        """POST /api/v1/governance-store/proposals"""
        return self._post(
            "/governance-store/proposals",
            {
                "title": title,
                "description": description,
                "proposer": proposer,
                "template_id": template_id,
            },
        )

    def list_proposals(
        self,
        status: Optional[str] = None,
        proposer: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        """GET /api/v1/governance-store/proposals"""
        params = f"?limit={limit}&offset={offset}"
        if status:
            params += f"&status={status}"
        if proposer:
            params += f"&proposer={proposer}"
        if search:
            params += f"&search={search}"
        return self._get(f"/governance-store/proposals{params}")

    def get_proposal(self, proposal_id: str) -> dict:
        """GET /api/v1/governance-store/proposals/:id"""
        return self._get(f"/governance-store/proposals/{proposal_id}")

    def vote(
        self,
        proposal_id: str,
        voter_id: str,
        choice: str,
        stake: int = 100,
        delegated: bool = False,
    ) -> dict:
        """POST /api/v1/governance-store/proposals/:id/vote"""
        return self._post(
            f"/governance-store/proposals/{proposal_id}/vote",
            {
                "voter_id": voter_id,
                "choice": choice,
                "stake": stake,
                "delegated": delegated,
            },
        )

    def finalize_proposal(self, proposal_id: str, approved: bool = True) -> dict:
        """POST /api/v1/governance-store/proposals/:id/finalize"""
        return self._post(
            f"/governance-store/proposals/{proposal_id}/finalize",
            {"approved": approved},
        )

    def governance_history(self, limit: int = 100) -> dict:
        """GET /api/v1/governance-store/history"""
        return self._get(f"/governance-store/history?limit={limit}")

    def governance_stats(self) -> dict:
        """GET /api/v1/governance-store/stats"""
        return self._get("/governance-store/stats")

    # ── ZK Proofs (Z) ────────────────────────────────────────────────────

    def zk_prove_membership(
        self, value: str, member_set: List[str], blinding: str = "default"
    ) -> dict:
        """POST /api/v1/zk/prove-membership"""
        return self._post(
            "/zk/prove-membership",
            {"value": value, "set": member_set, "blinding": blinding},
        )

    def zk_prove_range(
        self, value: int, threshold: int, blinding: str = "default"
    ) -> dict:
        """POST /api/v1/zk/prove-range"""
        return self._post(
            "/zk/prove-range",
            {"value": value, "threshold": threshold, "blinding": blinding},
        )

    def zk_prove_computation(
        self,
        program_hash: str,
        input_hash: str,
        output: str,
        blinding: str = "default",
    ) -> dict:
        """POST /api/v1/zk/prove-computation"""
        return self._post(
            "/zk/prove-computation",
            {
                "program_hash": program_hash,
                "input_hash": input_hash,
                "output": output,
                "blinding": blinding,
            },
        )

    def zk_verify(self, proof: dict) -> dict:
        """POST /api/v1/zk/verify"""
        return self._post("/zk/verify", {"proof": proof})

    def zk_stats(self) -> dict:
        """GET /api/v1/zk/stats"""
        return self._get("/zk/stats")

    # ── Multi-Tenant (AB) ────────────────────────────────────────────────

    def create_tenant(
        self, name: str, admin_id: str, api_key: Optional[str] = None
    ) -> dict:
        """POST /api/v1/tenants"""
        body: Dict[str, Any] = {"name": name, "admin_id": admin_id}
        if api_key:
            body["api_key"] = api_key
        return self._post("/tenants", body)

    def list_tenants(self) -> dict:
        """GET /api/v1/tenants"""
        return self._get("/tenants")

    def get_tenant(self, tenant_id: str) -> dict:
        """GET /api/v1/tenants/:id"""
        return self._get(f"/tenants/{tenant_id}")

    def suspend_tenant(self, tenant_id: str) -> dict:
        """POST /api/v1/tenants/:id/suspend"""
        return self._post(f"/tenants/{tenant_id}/suspend")

    def activate_tenant(self, tenant_id: str) -> dict:
        """POST /api/v1/tenants/:id/activate"""
        return self._post(f"/tenants/{tenant_id}/activate")

    def authenticate_tenant(self, api_key: str) -> dict:
        """POST /api/v1/tenants/authenticate"""
        return self._post("/tenants/authenticate", {"api_key": api_key})

    def register_resource(
        self,
        tenant_id: str,
        resource_type: str,
        resource_id: str,
        storage_bytes: Optional[int] = None,
    ) -> dict:
        """POST /api/v1/tenants/:id/resources"""
        body: Dict[str, Any] = {
            "resource_type": resource_type,
            "resource_id": resource_id,
        }
        if storage_bytes is not None:
            body["storage_bytes"] = storage_bytes
        return self._post(f"/tenants/{tenant_id}/resources", body)

    def update_quotas(self, tenant_id: str, **quotas: Any) -> dict:
        """PUT /api/v1/tenants/:id/quotas"""
        return self._put(f"/tenants/{tenant_id}/quotas", quotas)

    def tenant_stats(self) -> dict:
        """GET /api/v1/tenants/stats"""
        return self._get("/tenants/stats")

    # ── WASM (K) ─────────────────────────────────────────────────────────

    def wasm_deploy(self, name: str, bytecode_b64: str) -> dict:
        """POST /api/v1/wasm/contracts"""
        return self._post("/wasm/contracts", {"name": name, "bytecode": bytecode_b64})

    def wasm_contracts(self) -> dict:
        """GET /api/v1/wasm/contracts"""
        return self._get("/wasm/contracts")

    def wasm_stats(self) -> dict:
        """GET /api/v1/wasm/stats"""
        return self._get("/wasm/stats")

    # ── Observability (O2) ───────────────────────────────────────────────

    def alert_rules(self) -> dict:
        """GET /api/v1/observe/rules"""
        return self._get("/observe/rules")

    def fired_alerts(self) -> dict:
        """GET /api/v1/observe/alerts"""
        return self._get("/observe/alerts")

    def slo_status(self) -> dict:
        """GET /api/v1/observe/slo"""
        return self._get("/observe/slo")

    def logs(self, limit: int = 100) -> dict:
        """GET /api/v1/observe/logs"""
        return self._get(f"/observe/logs?limit={limit}")

    # ── Security (S) ─────────────────────────────────────────────────────

    def security_scan(self) -> dict:
        """GET /api/v1/security/scan"""
        return self._get("/security/scan")

    # ── Performance (U) ──────────────────────────────────────────────────

    def perf_tps(self) -> dict:
        """GET /api/v1/perf/tps"""
        return self._get("/perf/tps")

    def perf_latency(self) -> dict:
        """GET /api/v1/perf/latency"""
        return self._get("/perf/latency")

    # ── Evolution (M) ────────────────────────────────────────────────────

    def evolution_stats(self) -> dict:
        """GET /api/v1/evolution/stats"""
        return self._get("/evolution/stats")

    def evolution_leaderboard(self) -> dict:
        """GET /api/v1/evolution/leaderboard"""
        return self._get("/evolution/leaderboard")

    # ── Bridge (L2) ──────────────────────────────────────────────────────

    def bridge_chains(self) -> dict:
        """GET /api/v1/bridge/chains"""
        return self._get("/bridge/chains")

    def bridge_stats(self) -> dict:
        """GET /api/v1/bridge/stats"""
        return self._get("/bridge/stats")

    # ── Auth (AT/AU) ─────────────────────────────────────────────────────

    def auth_token(self, agent_id: str, role: str = "Agent") -> dict:
        """POST /api/v1/auth/token — obtain JWT, auto-stores token."""
        resp = self._post("/auth/token", {"agent_id": agent_id, "role": role})
        if "token" in resp:
            self.token = resp["token"]
        return resp

    def auth_refresh(self) -> dict:
        """POST /api/v1/auth/refresh — refresh JWT, auto-stores new token."""
        resp = self._post("/auth/refresh")
        if "token" in resp:
            self.token = resp["token"]
        return resp

    def auth_promote(self, agent_id: str, new_role: str) -> dict:
        """POST /api/v1/auth/promote — promote agent role (Admin only)."""
        return self._post("/auth/promote", {"agent_id": agent_id, "new_role": new_role})

    def auth_verify(self) -> dict:
        """GET /api/v1/auth/verify — verify current token."""
        return self._get("/auth/verify")

    # ── DAG Orchestration (AW) ───────────────────────────────────────────

    def dag_create(self, dag: dict) -> dict:
        """POST /api/v1/multi/dag"""
        return self._post("/multi/dag", dag)

    def dag_get(self, dag_id: str) -> dict:
        """GET /api/v1/multi/dag/:id"""
        return self._get(f"/multi/dag/{dag_id}")

    def dag_execute(self, dag_id: str) -> dict:
        """POST /api/v1/multi/dag/:id/execute"""
        return self._post(f"/multi/dag/{dag_id}/execute")

    def dag_step_complete(self, dag_id: str, step_id: str, output: Any = None) -> dict:
        """POST /api/v1/multi/dag/:dag_id/step/:step_id/complete"""
        body = {"output": output} if output is not None else {}
        return self._post(f"/multi/dag/{dag_id}/step/{step_id}/complete", body)

    def dag_step_fail(self, dag_id: str, step_id: str, error: str = "") -> dict:
        """POST /api/v1/multi/dag/:dag_id/step/:step_id/fail"""
        return self._post(f"/multi/dag/{dag_id}/step/{step_id}/fail", {"error": error})

    def dag_list(self) -> dict:
        """GET /api/v1/multi/dag"""
        return self._get("/multi/dag")

    # ── Shared KV Store (AX) ─────────────────────────────────────────────

    def kv_set(self, key: str, value: Any) -> dict:
        """PUT /api/v1/multi/kv/:key"""
        return self._put(f"/multi/kv/{key}", {"value": value})

    def kv_get(self, key: str) -> dict:
        """GET /api/v1/multi/kv/:key"""
        return self._get(f"/multi/kv/{key}")

    def kv_delete(self, key: str) -> dict:
        """DELETE /api/v1/multi/kv/:key"""
        return self._delete(f"/multi/kv/{key}")

    def kv_list(self) -> dict:
        """GET /api/v1/multi/kv"""
        return self._get("/multi/kv")

    # ── Agent Marketplace (AY) ───────────────────────────────────────────

    def market_create_listing(self, listing: dict) -> dict:
        """POST /api/v1/multi/market"""
        return self._post("/multi/market", listing)

    def market_search(self, capability: Optional[str] = None, max_price: Optional[float] = None) -> dict:
        """GET /api/v1/multi/market"""
        params = []
        if capability:
            params.append(f"capability={capability}")
        if max_price is not None:
            params.append(f"max_price={max_price}")
        qs = "?" + "&".join(params) if params else ""
        return self._get(f"/multi/market{qs}")

    def market_bid(self, listing_id: str, bidder_id: str, price: float) -> dict:
        """POST /api/v1/multi/market/:id/bid"""
        return self._post(f"/multi/market/{listing_id}/bid", {"bidder_id": bidder_id, "price": price})

    def market_stats(self) -> dict:
        """GET /api/v1/multi/market/stats"""
        return self._get("/multi/market/stats")
