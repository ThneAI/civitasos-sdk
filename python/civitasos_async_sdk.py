"""CivitasOS Async Python Agent SDK

Async-first variant of CivitasAgent using aiohttp.
All methods are async/await. Mirrors the sync SDK API exactly.

Usage:
    from civitasos_async_sdk import AsyncCivitasAgent

    async def main():
        async with AsyncCivitasAgent("http://localhost:8099") as agent:
            await agent.a2a_register(
                name="My Agent", description="Does things",
                capabilities=[{"id": "compute", "name": "Compute", "description": "..."}],
                endpoint="http://localhost:9001",
            )  # DID derived from public_key automatically
            agents = await agent.a2a_discover(capability_id="compute")
            print(agents)

Requires: pip install civitasos-sdk[async]   (installs aiohttp)
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urlencode

try:
    import aiohttp
except ImportError:
    raise ImportError(
        "aiohttp is required for async SDK. Install with: pip install civitasos-sdk[async]"
    )


class CivitasError(Exception):
    pass


class CivitasConnectionError(CivitasError):
    pass


class CivitasAPIError(CivitasError):
    def __init__(self, message: str, status_code: int = 0):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class ApiResponse:
    success: bool
    data: Any = None
    error: Optional[str] = None
    timestamp: int = 0


class AsyncCivitasAgent:
    """Async client for CivitasOS. Use as async context manager."""

    def __init__(self, base_url: str = "http://localhost:8099", timeout: int = 10):
        self.base_url = base_url.rstrip("/")
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: Optional[aiohttp.ClientSession] = None
        self._agent_id: Optional[str] = None
        self._jwt_token: Optional[str] = None
        self._jwt_expires_at: float = 0.0
        self._api_version = "v1"

    async def __aenter__(self):
        self._session = aiohttp.ClientSession(timeout=self.timeout)
        return self

    async def __aexit__(self, *exc):
        if self._session:
            await self._session.close()

    @property
    def api_prefix(self) -> str:
        return f"/api/{self._api_version}"

    def _headers(self) -> Dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self._jwt_token:
            h["Authorization"] = f"Bearer {self._jwt_token}"
        return h

    # ─── Low-level HTTP ──────────────────────────────────────────

    async def _request(self, method: str, path: str, body: Any = None) -> ApiResponse:
        if not self._session:
            self._session = aiohttp.ClientSession(timeout=self.timeout)
        url = f"{self.base_url}{self.api_prefix}{path}"
        kwargs: Dict[str, Any] = {"headers": self._headers()}
        if body is not None:
            kwargs["json"] = body
        try:
            async with self._session.request(method, url, **kwargs) as resp:
                raw = await resp.json()
                if resp.status >= 400:
                    return ApiResponse(success=False, error=raw.get("error", str(resp.status)))
                return ApiResponse(
                    success=raw.get("success", True),
                    data=raw.get("data", raw),
                    error=raw.get("error"),
                    timestamp=raw.get("timestamp", 0),
                )
        except aiohttp.ClientConnectorError as e:
            raise CivitasConnectionError(f"Cannot connect to {url}: {e}")

    async def _a2a_request(self, method: str, path: str, body: Any = None) -> Any:
        if not self._session:
            self._session = aiohttp.ClientSession(timeout=self.timeout)
        url = f"{self.base_url}/api/v1/a2a{path}"
        kwargs: Dict[str, Any] = {"headers": self._headers()}
        if body is not None:
            kwargs["json"] = body
        try:
            async with self._session.request(method, url, **kwargs) as resp:
                raw = await resp.json()
                if resp.status >= 400:
                    raise CivitasAPIError(raw.get("error", str(resp.status)), resp.status)
                return raw
        except aiohttp.ClientConnectorError as e:
            raise CivitasConnectionError(f"Cannot connect to {url}: {e}")

    async def _get(self, path: str) -> ApiResponse:
        return await self._request("GET", path)

    async def _post(self, path: str, body: Any = None) -> ApiResponse:
        return await self._request("POST", path, body)

    # ─── Health ──────────────────────────────────────────────────

    async def ping(self) -> bool:
        try:
            resp = await self._get("/status")
            return resp.success
        except CivitasError:
            return False

    async def get_status(self) -> Dict[str, Any]:
        resp = await self._get("/status")
        if not resp.success:
            raise CivitasAPIError(resp.error or "Failed to get status")
        return resp.data

    # ─── Agent lifecycle ─────────────────────────────────────────

    async def register(self, agent_id: str, name: str, capabilities: List[str], stake: int = 100):
        body = {"id": agent_id, "name": name, "capabilities": capabilities, "stake": stake}
        resp = await self._post("/agents", body)
        if not resp.success:
            raise CivitasAPIError(resp.error or "Registration failed")
        self._agent_id = agent_id
        return resp.data

    # ─── A2A ─────────────────────────────────────────────────────

    async def a2a_quickstart(
        self, name: str, endpoint: str,
        description: str = "",
        alias: Optional[str] = None,
        credentials: Optional[List[Dict[str, Any]]] = None,
        public_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """One-call agent registration. DID derived from public_key server-side."""
        pk = public_key or getattr(self, '_public_key_hex', None)
        if not pk:
            raise CivitasError("public_key is required")
        payload: Dict[str, Any] = {"public_key": pk, "name": name, "endpoint": endpoint}
        if alias:
            payload["alias"] = alias
        if description:
            payload["description"] = description
        if credentials:
            payload["credentials"] = credentials
        result = await self._a2a_request("POST", "/quickstart", payload)
        agent = result.get("agent", {})
        self._agent_id = agent.get("did") or result.get("did") or result.get("agent_id", "")
        return result

    async def a2a_register(
        self, name: str, description: str,
        capabilities: List[Dict[str, Any]], endpoint: str = "",
        stake: int = 0, initial_reputation: float = 0.3,
        alias: Optional[str] = None,
        public_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Register an agent card. DID derived from public_key server-side."""
        pk = public_key or getattr(self, '_public_key_hex', None)
        if not pk:
            raise CivitasError("public_key is required")
        card = await self._a2a_request("POST", "/agents", {
            "public_key": pk, "name": name, "description": description,
            "endpoint": endpoint, "capabilities": capabilities,
            "stake": stake, "initial_reputation": initial_reputation,
            "alias": alias,
        })
        agent = card.get("agent", {})
        self._agent_id = agent.get("did") or card.get("did") or card.get("agent_id", "")
        return card

    async def a2a_discover(
        self, capability_id: Optional[str] = None, min_reputation: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        params = []
        if capability_id:
            params.append(f"capability_id={capability_id}")
        if min_reputation is not None:
            params.append(f"min_reputation={min_reputation}")
        qs = "&".join(params)
        path = f"/discover?{qs}" if qs else "/discover"
        return await self._a2a_request("GET", path)

    async def a2a_submit_task(
        self, to_agent: str, capability_id: str, input_data: Any,
        from_agent: Optional[str] = None, deadline_secs: Optional[int] = None,
    ) -> Dict[str, Any]:
        return await self._a2a_request("POST", "/task", {
            "from_agent": from_agent or self._agent_id or "anonymous",
            "to_agent": to_agent, "capability_id": capability_id,
            "input": input_data, "deadline_secs": deadline_secs,
        })

    async def a2a_get_reputation(self, agent_id: Optional[str] = None) -> Dict[str, Any]:
        aid = agent_id or self._agent_id
        return await self._a2a_request("GET", f"/reputation/{aid}")

    # ─── Task Pool ───────────────────────────────────────────────

    async def pool_post(
        self, required_capability: str, input_data: Any = None,
        reward: int = 100, min_reputation: float = 0.0,
    ) -> Dict[str, Any]:
        return await self._a2a_request("POST", "/pool/post", {
            "requester": self._agent_id or "anonymous",
            "required_capability": required_capability,
            "input": input_data or {}, "reward": reward,
            "min_reputation": min_reputation,
        })

    async def pool_discover(self, capability: str = None, capabilities: list = None, min_reputation: float = 0.0) -> List[Dict[str, Any]]:
        caps = capabilities or ([capability] if capability else [])
        return await self._a2a_request("POST", "/pool/discover", {
            "agent_id": self._agent_id or "anonymous",
            "capabilities": caps,
        })

    async def pool_claim(self, task_id: str) -> Dict[str, Any]:
        return await self._a2a_request("POST", "/pool/claim", {
            "task_id": task_id, "agent_id": self._agent_id or "anonymous",
        })

    async def pool_list(self) -> List[Dict[str, Any]]:
        return await self._a2a_request("GET", "/pool/tasks")

    async def pool_get_task(self, task_id: str) -> Dict[str, Any]:
        try:
            resp = await self._a2a_request("GET", f"/pool/tasks/{quote(task_id, safe='')}")
            if isinstance(resp, dict):
                task = resp.get("task") or resp
                if isinstance(task, dict):
                    return task
        except CivitasError:
            pass

        records = await self.pool_list()
        if isinstance(records, dict):
            records = records.get("tasks") or records.get("data") or []
        for task in records:
            if isinstance(task, dict) and (
                task.get("id") == task_id or task.get("task_id") == task_id
            ):
                return task
        raise CivitasError(f"pool task not found: {task_id}")

    async def pool_failures(
        self,
        agent_id: Optional[str] = None,
        since: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> Dict[str, Any]:
        query: Dict[str, Any] = {}
        if agent_id:
            query["agent_id"] = agent_id
        if since:
            query["since"] = since
        if limit is not None:
            query["limit"] = int(limit)
        path = "/pool/failures"
        if query:
            path = f"{path}?{urlencode(query)}"
        return await self._a2a_request("GET", path)

    async def task_execute(
        self, task_id: str, output: Any, success: bool = True,
        metadata: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {
            "agent_id": self._agent_id or "anonymous",
            "task_id": task_id, "output": output, "success": success,
        }
        if metadata:
            body["metadata"] = metadata
        return await self._a2a_request("POST", "/task/execute", body)

    # ─── Governance ──────────────────────────────────────────────

    async def create_proposal(self, title: str, description: str, proposal_type: str = "ParameterChange") -> str:
        resp = await self._post("/proposals", {
            "title": title, "description": description,
            "proposal_type": proposal_type,
            "proposer": self._agent_id or "anonymous",
        })
        if not resp.success:
            raise CivitasAPIError(resp.error or "Proposal creation failed")
        return resp.data.get("id", "") if isinstance(resp.data, dict) else str(resp.data or "")

    async def vote(self, proposal_id: str, vote_type: str = "approve", stake: int = 100) -> Dict[str, Any]:
        resp = await self._post("/vote", {
            "proposal_id": proposal_id,
            "voter_id": self._agent_id or "anonymous",
            "vote": vote_type, "stake": stake,
        })
        if not resp.success:
            raise CivitasAPIError(resp.error or "Vote failed")
        return resp.data

    # ─── Marketplace ─────────────────────────────────────────────

    async def market_create_listing(self, capability: str, price: int, description: str = "") -> Dict[str, Any]:
        resp = await self._request("POST", "/multi/market/list", {
            "agent_id": self._agent_id or "anonymous",
            "capability": capability, "price": price, "description": description,
        })
        return resp.data

    async def market_search(
        self, capability: Optional[str] = None, max_price: Optional[int] = None,
    ) -> Dict[str, Any]:
        params = {}
        if capability:
            params["capability"] = capability
        if max_price is not None:
            params["max_price"] = str(max_price)
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        path = f"/multi/market/search?{qs}" if qs else "/multi/market/search"
        return (await self._request("GET", path)).data

    # ─── DAG ─────────────────────────────────────────────────────

    async def dag_create(self, steps: List[Dict[str, Any]], description: Optional[str] = None) -> Dict[str, Any]:
        body: Dict[str, Any] = {"steps": steps}
        if description:
            body["description"] = description
        return (await self._request("POST", "/multi/dag", body)).data

    async def dag_execute(self, dag_id: str) -> Dict[str, Any]:
        return (await self._request("POST", f"/multi/dag/{dag_id}/execute")).data

    # ─── KV Store ────────────────────────────────────────────────

    async def kv_set(self, key: str, value: Any) -> Dict[str, Any]:
        return (await self._request("PUT", f"/multi/kv/{key}", {"value": value})).data

    async def kv_get(self, key: str) -> Dict[str, Any]:
        return (await self._request("GET", f"/multi/kv/{key}")).data

    # ─── Economics ───────────────────────────────────────────────

    async def economics_metrics(self) -> Dict[str, Any]:
        return await self._a2a_request("GET", "/economics/metrics")

    # ─── R2R: Relation-aware Runtime Protocol ────────────────────

    async def r2r_propose_relation(
        self, from_agent: str, to_agent: str, relation_type: str = "cooperative",
    ) -> Dict[str, Any]:
        """Propose a new R2R relation between two agents."""
        resp = await self._request("POST", "/r2r/relations", {
            "from": from_agent, "to": to_agent, "relation_type": relation_type,
        })
        return resp.data

    async def r2r_terminate_relation(
        self, from_agent: str, to_agent: str, reason: str = "requested",
    ) -> Dict[str, Any]:
        """Terminate an existing R2R relation."""
        resp = await self._request("POST", "/r2r/relations/terminate", {
            "from": from_agent, "to": to_agent, "reason": reason,
        })
        return resp.data

    async def r2r_revive_relation(self, agent_a: str, agent_b: str) -> Dict[str, Any]:
        """Revive a dormant R2R relation."""
        resp = await self._request("PUT", "/r2r/relations/revive", {
            "agent_a": agent_a, "agent_b": agent_b,
        })
        return resp.data

    async def r2r_send_signal(
        self, from_agent: str, to_agent: str, intent: str = "heartbeat",
        payload: Optional[Dict[str, Any]] = None, correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send an R2R signal through relation routing."""
        body: Dict[str, Any] = {
            "from": from_agent, "to": to_agent,
            "intent": intent, "payload": payload or {},
        }
        if correlation_id:
            body["correlation_id"] = correlation_id
        resp = await self._request("POST", "/r2r/signals", body)
        return resp.data

    async def r2r_send_task(
        self, from_agent: str, to_agent: str, capability_id: str,
        task_input: Optional[Dict[str, Any]] = None, deadline_secs: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Dispatch a task via R2R relation routing."""
        body: Dict[str, Any] = {
            "from": from_agent, "to": to_agent,
            "capability_id": capability_id, "input": task_input or {},
        }
        if deadline_secs is not None:
            body["deadline_secs"] = deadline_secs
        resp = await self._request("POST", "/r2r/tasks", body)
        return resp.data

    async def r2r_report_completion(self, task_id: str, success: bool = True) -> Dict[str, Any]:
        """Report task completion to update aspect metrics."""
        resp = await self._request("POST", "/r2r/tasks/complete", {
            "task_id": task_id, "success": success,
        })
        return resp.data

    async def r2r_rate_peer(
        self, rater: str, rated: str, dimension: str = "quality", score: float = 0.8,
    ) -> Dict[str, Any]:
        """Submit a peer rating."""
        resp = await self._request("POST", "/r2r/rate", {
            "rater": rater, "rated": rated, "dimension": dimension, "score": score,
        })
        return resp.data

    async def r2r_get_relations(self, agent_id: str) -> Dict[str, Any]:
        """List all R2R relations for a specific agent."""
        resp = await self._request("GET", f"/r2r/relations/{agent_id}")
        return resp.data

    async def r2r_social_graph(self, agent_id: str) -> Dict[str, Any]:
        """Get agent's social graph."""
        resp = await self._request("GET", f"/r2r/social-graph/{agent_id}")
        return resp.data

    async def r2r_aspect_gap(self, agent_id: str) -> Dict[str, Any]:
        """Get aspect gap report."""
        resp = await self._request("GET", f"/r2r/aspect-gap/{agent_id}")
        return resp.data

    async def r2r_detect_adversarial(self, agent_id: str) -> Dict[str, Any]:
        """Detect adversarial behavior for an agent."""
        resp = await self._request("GET", f"/r2r/adversarial/{agent_id}")
        return resp.data

    async def r2r_maintenance(self) -> Dict[str, Any]:
        """Run R2R maintenance cycle."""
        resp = await self._request("POST", "/r2r/maintenance")
        return resp.data

    async def r2r_stats(self) -> Dict[str, Any]:
        """Get R2R runtime statistics."""
        resp = await self._request("GET", "/r2r/stats")
        return resp.data

    # ─── P3: Trust Transitivity ──────────────────────────────────────

    async def r2r_discover_by_trust(
        self, agent_id: str, max_hops: int = 3, capability: Optional[str] = None
    ) -> Dict[str, Any]:
        """Discover agents via transitive trust paths."""
        qs = f"?max_hops={max_hops}"
        if capability:
            qs += f"&capability={capability}"
        resp = await self._request("GET", f"/r2r/discover/{agent_id}{qs}")
        return resp.data

    # ─── P5: Immune Response ─────────────────────────────────────────

    async def r2r_immune_response(self, agent_id: str) -> Dict[str, Any]:
        """Trigger immune system response (quarantine/cool-down)."""
        resp = await self._request("POST", f"/r2r/immune-response/{agent_id}")
        return resp.data

    # ─── P4: Constitutional Guardian Multi-sig ───────────────────────

    async def ratify_amendment(
        self, proposal_id: str, steward_id: str, signature_hex: str
    ) -> Dict[str, Any]:
        """Submit steward signature to ratify a constitutional amendment."""
        resp = await self._request("POST", "/constitution/ratify", {
            "proposal_id": proposal_id, "steward_id": steward_id, "signature_hex": signature_hex,
        })
        return resp.data

    async def reject_amendment(self, proposal_id: str, steward_id: str) -> Dict[str, Any]:
        """Reject a pending constitutional amendment."""
        resp = await self._request("POST", "/constitution/reject", {
            "proposal_id": proposal_id, "steward_id": steward_id,
        })
        return resp.data

    async def get_pending_amendments(self) -> Dict[str, Any]:
        """List pending constitutional amendments."""
        resp = await self._request("GET", "/constitution/pending")
        return resp.data

    async def get_stewards(self) -> Dict[str, Any]:
        """List constitutional stewards and config."""
        resp = await self._request("GET", "/constitution/stewards")
        return resp.data

    async def add_steward(self, steward_id: str, public_key: str) -> Dict[str, Any]:
        """Add a new constitutional steward."""
        resp = await self._request("POST", "/constitution/stewards", {
            "id": steward_id, "public_key": public_key,
        })
        return resp.data

    async def close(self):
        if self._session:
            await self._session.close()
