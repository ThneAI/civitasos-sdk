"""Advanced features mixin: DAG, KV, marketplace, MCP, ZK, observability, tenants, WASM, bridge."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen

from .models import CivitasError


class AdvancedMixin:
    """Economics, scheduling, directory, DAG, KV store, marketplace,
    MCP tools, ZK proofs, observability, multi-tenant, WASM, cross-chain bridge."""

    # ─── Scheduling ──────────────────────────────────────────────────

    def scheduler_policy(self) -> Dict[str, Any]:
        """Get the current scheduling policy (tier→concurrency limits)."""
        return self._a2a_request("GET", "/scheduler/policy")

    def scheduler_can_accept(self, agent_id: str, reputation: float) -> Dict[str, Any]:
        """Check if an agent can accept a new task given its reputation."""
        return self._a2a_request("POST", "/scheduler/can-accept", {
            "agent_id": agent_id, "reputation": reputation,
        })

    def scheduler_concurrency(self) -> Dict[str, Any]:
        """Get concurrency stats for all agents."""
        return self._a2a_request("GET", "/scheduler/concurrency")

    # ─── Economics ───────────────────────────────────────────────────

    def economics_metrics(self) -> Dict[str, Any]:
        """Get network economic metrics (total staked, accounts, etc.)."""
        return self._a2a_request("GET", "/economics/metrics")

    def economics_parameters(self) -> Dict[str, Any]:
        """Get current economic parameters (fee rates, inflation, etc.)."""
        return self._a2a_request("GET", "/economics/parameters")

    def economics_adapt(self) -> Dict[str, Any]:
        """Trigger adaptive economic parameter tuning."""
        return self._a2a_request("POST", "/economics/adapt")

    def economics_accounts(self) -> Dict[str, Any]:
        """Get all economic accounts with balance, reputation, risk, and potential.

        Returns account_count, accounts list (each with id, balance,
        reputation_score, risk_score, staked_amount), circulation,
        and total_supply.
        """
        return self._request("GET", "/economics/accounts")

    def get_account(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get a single agent's economic account.

        Returns balance, reputation_score, risk_score, potential,
        staked_amount, or None if not found.
        """
        data = self.economics_accounts()
        accounts = data.get("accounts", data.get("data", {}).get("accounts", []))
        for acct in accounts:
            if acct.get("id") == agent_id:
                return acct
        return None

    def economics_gas_market(self) -> Dict[str, Any]:
        """Get gas market state and pricing parameters."""
        return self._request("GET", "/economics/gas-market")

    # ─── Multi-node Directory ────────────────────────────────────────

    def directory_publish(
        self,
        agent_id: str,
        name: str,
        endpoint: str,
        capabilities: List[str],
        stake: int = 100,
        reputation: float = 0.5,
        node_id: str = "local",
    ) -> Dict[str, Any]:
        """Publish an agent to the cluster-wide directory."""
        return self._a2a_request("POST", "/directory/publish", {
            "agent_id": agent_id, "name": name, "endpoint": endpoint,
            "capabilities": capabilities, "stake": stake,
            "reputation": reputation, "node_id": node_id,
        })

    def directory_discover(self, capability: str) -> List[Dict[str, Any]]:
        """Discover agents across all nodes by capability."""
        return self._a2a_request("POST", "/directory/discover", {"capability": capability})

    def directory_list(self) -> List[Dict[str, Any]]:
        """List all entries in the multi-node directory."""
        return self._a2a_request("GET", "/directory/list")

    def directory_sync(self, entries: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Sync directory entries from another node (anti-entropy)."""
        return self._a2a_request("POST", "/directory/sync", entries)

    # ─── Reputation Mesh ─────────────────────────────────────────────

    def reputation_mesh_list(self) -> List[Dict[str, Any]]:
        """List all reputation snapshots in the CRDT mesh."""
        return self._a2a_request("GET", "/reputation/mesh")

    def reputation_mesh_sync(self, snapshots: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Sync reputation snapshots from another node."""
        return self._a2a_request("POST", "/reputation/mesh/sync", snapshots)

    # ─── Task Callbacks ──────────────────────────────────────────────

    def list_callbacks(self) -> List[Dict[str, Any]]:
        """List all agents that have registered callback endpoints."""
        result = self._a2a_request("GET", "/callbacks")
        return result.get("callbacks", []) if isinstance(result, dict) else result

    # ─── LLM Agent Execution Bridge ──────────────────────────────────

    def task_execute(
        self,
        task_id: str,
        output: Any,
        success: bool = True,
        metadata: Optional[Dict[str, str]] = None,
        agent_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Submit a task result via the LLM execution bridge.

        This is the JSON-in/JSON-out execution path (no WASM required).
        Use after claiming a pool task with pool_claim().

        Args:
            task_id: The task pool ID
            output: The result produced by the agent (arbitrary JSON)
            success: Whether the task completed successfully
            metadata: Optional metadata (e.g., model used, execution time)
            agent_id: Agent submitting the result (defaults to self)
        """
        body: Dict[str, Any] = {
            "agent_id": agent_id or self._agent_id or "anonymous",
            "task_id": task_id,
            "output": output,
            "success": success,
        }
        if metadata:
            body["metadata"] = metadata
        return self._a2a_request("POST", "/task/execute", body)

    # ─── Token Refresh ───────────────────────────────────────────────

    def refresh_token(self) -> Dict[str, Any]:
        """Refresh the current JWT without re-signing."""
        import time as _time
        result = self._request("POST", "/auth/refresh")
        if "token" in result:
            self._jwt_token = result["token"]
            self._jwt_expires_at = _time.time() + result.get("expires_in", 3600)
        return result

    # ─── DAG Orchestration ───────────────────────────────────────────

    def dag_create(
        self,
        steps: List[Dict[str, Any]],
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a task DAG.

        Args:
            steps: List of step dicts with step_id, capability, input, depends_on
            description: Optional DAG description
        """
        body: Dict[str, Any] = {"steps": steps}
        if description:
            body["description"] = description
        return self._request("POST", "/multi/dag", body)

    def dag_get(self, dag_id: str) -> Dict[str, Any]:
        """Get DAG status."""
        return self._request("GET", f"/multi/dag/{dag_id}")

    def dag_execute(self, dag_id: str) -> Dict[str, Any]:
        """Start executing a DAG."""
        return self._request("POST", f"/multi/dag/{dag_id}/execute")

    def dag_step_complete(self, dag_id: str, step_id: str, output: Any) -> Dict[str, Any]:
        """Mark a DAG step as completed with output."""
        return self._request("POST", f"/multi/dag/{dag_id}/step/{step_id}/complete", {"output": output})

    def dag_step_fail(self, dag_id: str, step_id: str, error: str) -> Dict[str, Any]:
        """Mark a DAG step as failed."""
        return self._request("POST", f"/multi/dag/{dag_id}/step/{step_id}/fail", {"error": error})

    def dag_list(self) -> Dict[str, Any]:
        """List all DAGs."""
        return self._request("GET", "/multi/dag")

    # ─── Shared KV Store ─────────────────────────────────────────────

    def kv_set(self, key: str, value: Any) -> Dict[str, Any]:
        """Set a shared key-value pair."""
        return self._request("PUT", f"/multi/kv/{key}", {"value": value})

    def kv_get(self, key: str) -> Dict[str, Any]:
        """Get a value by key."""
        return self._request("GET", f"/multi/kv/{key}")

    def kv_delete(self, key: str) -> Dict[str, Any]:
        """Delete a key."""
        return self._request("DELETE", f"/multi/kv/{key}")

    def kv_list(self) -> Dict[str, Any]:
        """List all keys."""
        return self._request("GET", "/multi/kv")

    # ─── Marketplace ─────────────────────────────────────────────────

    def market_create_listing(
        self,
        capability: str,
        price: int,
        description: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a marketplace listing."""
        return self._request("POST", "/multi/market/list", {
            "agent_id": agent_id or self._agent_id or "anonymous",
            "capability": capability,
            "price": price,
            "description": description or "",
        })

    def market_search(
        self,
        capability: Optional[str] = None,
        max_price: Optional[int] = None,
        min_rating: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Search marketplace listings."""
        params = {}
        if capability:
            params["capability"] = capability
        if max_price is not None:
            params["max_price"] = str(max_price)
        if min_rating is not None:
            params["min_rating"] = str(min_rating)
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        path = f"/multi/market/search?{qs}" if qs else "/multi/market/search"
        return self._request("GET", path)

    def market_bid(self, capability: str, max_price: int, min_rating: Optional[float] = None) -> Dict[str, Any]:
        """Find best match for a capability request."""
        return self._request("POST", "/multi/market/bid", {
            "capability": capability, "max_price": max_price, "min_rating": min_rating,
        })

    def market_stats(self) -> Dict[str, Any]:
        """Get marketplace statistics."""
        return self._request("GET", "/multi/market/stats")

    # ─── MCP Tool Marketplace ────────────────────────────────────────

    def mcp_publish(self, name: str, description: str, input_schema: Dict[str, Any],
                    endpoint: str, transport: str = "http") -> Dict[str, Any]:
        """Publish a tool to the MCP marketplace."""
        return self._request("POST", "/fg/mcp/publish", {
            "name": name, "description": description,
            "input_schema": input_schema, "endpoint": endpoint, "transport": transport,
        })

    def mcp_search(self, query: str = "", capability: str = "") -> Dict[str, Any]:
        """Search for tools in the MCP marketplace."""
        return self._request("POST", "/fg/mcp/search", {"query": query, "capability": capability})

    def mcp_install(self, tool_id: str, agent_id: str = "") -> Dict[str, Any]:
        """Install a tool from the MCP marketplace."""
        return self._request("POST", "/fg/mcp/install", {
            "tool_id": tool_id, "agent_id": agent_id or self._agent_id or "",
        })

    def mcp_uninstall(self, tool_id: str) -> Dict[str, Any]:
        """Uninstall a previously installed MCP tool."""
        return self._request("POST", f"/fg/mcp/uninstall/{tool_id}", {})

    def mcp_invoke(self, tool_id: str, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Invoke an installed MCP tool."""
        return self._request("POST", "/fg/mcp/invoke", {"tool_id": tool_id, "input": input_data})

    def mcp_stats(self) -> Dict[str, Any]:
        """Get MCP marketplace statistics."""
        return self._request("GET", "/fg/mcp/stats")

    # ─── ZK Proof System ─────────────────────────────────────────────

    def zk_prove_membership(self, value: int, member_set: list, blinding: int = 0) -> Dict[str, Any]:
        """Generate a zero-knowledge membership proof."""
        return self._request("POST", "/zk/prove-membership", {
            "value": value, "set": member_set, "blinding": blinding,
        })

    def zk_prove_range(self, value: int, threshold: int, blinding: int = 0) -> Dict[str, Any]:
        """Generate a zero-knowledge range proof (value >= threshold)."""
        return self._request("POST", "/zk/prove-range", {
            "value": value, "threshold": threshold, "blinding": blinding,
        })

    def zk_prove_computation(self, program_hash: str, input_hash: str, output: int) -> Dict[str, Any]:
        """Generate a zero-knowledge computation proof."""
        return self._request("POST", "/zk/prove-computation", {
            "program_hash": program_hash, "input_hash": input_hash, "output": output,
        })

    def zk_verify(self, proof: Dict[str, Any]) -> Dict[str, Any]:
        """Verify a zero-knowledge proof."""
        return self._request("POST", "/zk/verify", proof)

    def zk_stats(self) -> Dict[str, Any]:
        """Get ZK proof system statistics."""
        return self._request("GET", "/zk/stats")

    # ─── System / Observability ──────────────────────────────────────

    def health(self) -> Dict[str, Any]:
        """GET /healthz — liveness check."""
        url = f"{self.base_url.rstrip('/')}/healthz"
        req = Request(url, method="GET")
        with urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read())

    def openapi(self) -> Dict[str, Any]:
        """GET /api/v1/openapi.json — OpenAPI spec."""
        return self._get("/openapi.json").data

    def alert_rules(self) -> Dict[str, Any]:
        """GET /api/v1/observe/rules — alerting rules."""
        return self._get("/observe/rules").data

    def fired_alerts(self) -> Dict[str, Any]:
        """GET /api/v1/observe/alerts — recently fired alerts."""
        return self._get("/observe/alerts").data

    def slo_status(self) -> Dict[str, Any]:
        """GET /api/v1/observe/slo — SLO compliance status."""
        return self._get("/observe/slo").data

    def logs(self, limit: int = 100) -> Dict[str, Any]:
        """GET /api/v1/observe/logs — recent logs."""
        return self._get(f"/observe/logs?limit={limit}").data

    def security_scan(self) -> Dict[str, Any]:
        """GET /api/v1/security/scan — run security scan."""
        return self._get("/security/scan").data

    def perf_tps(self) -> Dict[str, Any]:
        """GET /api/v1/perf/tps — current throughput."""
        return self._get("/perf/tps").data

    def perf_latency(self) -> Dict[str, Any]:
        """GET /api/v1/perf/latency — latency percentiles."""
        return self._get("/perf/latency").data

    # ─── Multi-Tenant ────────────────────────────────────────────────

    def create_tenant(self, name: str, admin_id: str) -> Dict[str, Any]:
        """Create a new tenant."""
        return self._post("/tenants", {"name": name, "admin_id": admin_id}).data

    def list_tenants(self) -> Dict[str, Any]:
        """List all tenants."""
        return self._get("/tenants").data

    def get_tenant(self, tenant_id: str) -> Dict[str, Any]:
        """Get tenant details."""
        return self._get(f"/tenants/{tenant_id}").data

    def suspend_tenant(self, tenant_id: str) -> Dict[str, Any]:
        """Suspend a tenant."""
        return self._post(f"/tenants/{tenant_id}/suspend").data

    def activate_tenant(self, tenant_id: str) -> Dict[str, Any]:
        """Activate a suspended tenant."""
        return self._post(f"/tenants/{tenant_id}/activate").data

    def tenant_stats(self) -> Dict[str, Any]:
        """Get tenant usage statistics."""
        return self._get("/tenants/stats").data

    # ─── WASM Contracts ──────────────────────────────────────────────

    def wasm_deploy(self, name: str, bytecode_b64: str) -> Dict[str, Any]:
        """Deploy a WASM contract."""
        return self._post("/wasm/deploy", {"name": name, "bytecode": bytecode_b64}).data

    def wasm_contracts(self) -> Dict[str, Any]:
        """List deployed WASM contracts."""
        return self._get("/wasm/contracts").data

    def wasm_stats(self) -> Dict[str, Any]:
        """Get WASM execution stats."""
        return self._get("/wasm/stats").data

    # ─── Cross-Chain Bridge ──────────────────────────────────────────

    def bridge_chains(self) -> Dict[str, Any]:
        """List supported chains."""
        return self._get("/bridge/chains").data

    def bridge_stats(self) -> Dict[str, Any]:
        """Get bridge usage statistics."""
        return self._get("/bridge/stats").data
