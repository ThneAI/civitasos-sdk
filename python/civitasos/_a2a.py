"""A2A (Agent-to-Agent) protocol mixin: agent cards, discovery, tasks, scheduling."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .models import CivitasError


class A2AMixin:
    """A2A protocol: agent card registry, discovery, task delegation, scheduling."""

    def a2a_quickstart(
        self,
        agent_id: str,
        name: str,
        endpoint: str,
        description: str = "",
        credentials: Optional[List[Dict[str, Any]]] = None,
        public_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """One-call agent registration with full card + bootstrap.

        Creates an A2A agent card, enrolls credentials for higher initial
        reputation, and returns next-steps guidance. Different from
        ``register()`` which only creates a core registry entry.

        Args:
            agent_id: Unique agent identifier
            name: Human-readable name
            endpoint: URL where this agent accepts A2A messages
            description: Optional description (auto-generated if omitted)
            credentials: Optional bootstrap credentials for higher initial reputation.
                Each credential is a dict with "type" and type-specific fields:
                - {"type": "identity_verified"}
                - {"type": "stake", "amount": 500}
                - {"type": "referral", "voucher_id": "trusted-agent-1"}
                - {"type": "capability", "capability_id": "data-analysis"}
            public_key: Optional Ed25519 public key hex. If omitted and the
                SDK has a generated identity, it is sent automatically.
        """
        payload: Dict[str, Any] = {
            "id": agent_id,
            "name": name,
            "endpoint": endpoint,
        }
        if description:
            payload["description"] = description
        if credentials:
            payload["credentials"] = credentials
        pk = public_key or self._public_key_hex
        if pk:
            payload["public_key"] = pk
        result = self._a2a_request("POST", "/quickstart", payload)
        self._agent_id = agent_id
        return result

    def a2a_register(
        self,
        agent_id: str,
        name: str,
        description: str,
        capabilities: List[Dict[str, Any]],
        endpoint: str = "",
        stake: int = 0,
        initial_reputation: float = 0.3,
    ) -> Dict[str, Any]:
        """Register an agent card in the A2A directory.

        Creates a full agent card with structured capabilities.
        Different from ``register()`` which uses the core API.

        Args:
            agent_id: Unique agent identifier
            name: Human-readable name
            description: What this agent does
            capabilities: List of capability dicts with id, name, description
            endpoint: URL where this agent accepts A2A messages
            stake: Initial stake
            initial_reputation: Starting reputation (0.0-1.0)
        """
        card = self._a2a_request("POST", "/agents", {
            "id": agent_id,
            "name": name,
            "description": description,
            "endpoint": endpoint,
            "capabilities": capabilities,
            "stake": stake,
            "initial_reputation": initial_reputation,
        })
        self._agent_id = agent_id
        return card

    def a2a_get_agent(self, agent_id: str) -> Dict[str, Any]:
        """Get a specific agent's card from the A2A directory."""
        return self._a2a_request("GET", f"/agents/{agent_id}")

    def a2a_list_agents(self) -> List[Dict[str, Any]]:
        """List all agent cards in the A2A directory."""
        return self._a2a_request("GET", "/agents")

    def a2a_discover(
        self,
        capability_id: Optional[str] = None,
        min_reputation: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """Discover agents by capability and/or minimum reputation.

        Searches the A2A agent directory. To discover open *tasks*
        in the pool, use ``pool_discover()`` instead.

        Args:
            capability_id: Filter by capability
            min_reputation: Minimum reputation threshold
        """
        params = []
        if capability_id:
            params.append(f"capability_id={capability_id}")
        if min_reputation is not None:
            params.append(f"min_reputation={min_reputation}")
        qs = "&".join(params)
        path = f"/discover?{qs}" if qs else "/discover"
        return self._a2a_request("GET", path)

    # ─── Task Delegation ─────────────────────────────────────────────

    def a2a_submit_task(
        self,
        to_agent: str,
        capability_id: str,
        input_data: Any,
        from_agent: Optional[str] = None,
        deadline_secs: Optional[int] = None,
        metadata: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Submit a task directly to another agent.

        Args:
            to_agent: Target agent ID
            capability_id: Which capability to invoke
            input_data: Task input payload
            from_agent: Sender ID (defaults to self)
            deadline_secs: Optional deadline
            metadata: Optional metadata
        """
        return self._a2a_request("POST", "/task", {
            "from_agent": from_agent or self._agent_id or "anonymous",
            "to_agent": to_agent,
            "capability_id": capability_id,
            "input": input_data,
            "deadline_secs": deadline_secs,
            "metadata": metadata,
        })

    # ─── Reputation & Auth ───────────────────────────────────────────

    def a2a_get_reputation(self, agent_id: Optional[str] = None) -> Dict[str, Any]:
        """Get A2A reputation record with trust tier info."""
        aid = agent_id or self._agent_id
        if not aid:
            raise CivitasError("No agent_id specified")
        return self._a2a_request("GET", f"/reputation/{aid}")

    def a2a_check_auth(
        self,
        tool_name: str,
        permission_level: str = "write",
        agent_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Check if an agent is authorized for a tool at a given permission level.

        Args:
            tool_name: The tool to check authorization for
            permission_level: "readonly", "write", "admin", or "dangerous"
            agent_id: Agent to check (defaults to self)
        """
        return self._a2a_request("POST", "/auth/check", {
            "agent_id": agent_id or self._agent_id or "anonymous",
            "tool_name": tool_name,
            "permission_level": permission_level,
        })

    # ─── Scheduler ───────────────────────────────────────────────────

    def a2a_register_job(
        self,
        capability_id: str,
        interval_type: str,
        interval_value: str,
        input_data: Any = None,
        agent_id: Optional[str] = None,
        enabled: bool = True,
    ) -> Dict[str, Any]:
        """Register a scheduled recurring job.

        Args:
            capability_id: Capability to invoke on schedule
            interval_type: "seconds", "minutes", "hours", or "cron"
            interval_value: Numeric value or cron expression
            input_data: Job input payload
            agent_id: Agent that owns this job (defaults to self)
            enabled: Whether the job starts enabled
        """
        return self._a2a_request("POST", "/jobs", {
            "agent_id": agent_id or self._agent_id or "anonymous",
            "capability_id": capability_id,
            "input": input_data or {},
            "interval_type": interval_type,
            "interval_value": interval_value,
            "enabled": enabled,
        })

    def a2a_list_jobs(self, agent_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """List scheduled jobs for an agent."""
        aid = agent_id or self._agent_id
        if not aid:
            raise CivitasError("No agent_id specified")
        return self._a2a_request("GET", f"/jobs/{aid}")

    def a2a_register_trigger(
        self,
        capability_id: str,
        event_type: str,
        event_value: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Register an event trigger.

        Args:
            capability_id: Capability to invoke when triggered
            event_type: "topic_exact", "topic_prefix", "agent_joined", "agent_left",
                        "reputation_changed", "proposal_status"
            event_value: Value for the event pattern (e.g., topic name)
            agent_id: Agent that owns this trigger (defaults to self)
        """
        return self._a2a_request("POST", "/triggers", {
            "agent_id": agent_id or self._agent_id or "anonymous",
            "capability_id": capability_id,
            "event_type": event_type,
            "event_value": event_value,
        })

    # ─── Health & Audit ──────────────────────────────────────────────

    def a2a_health(self) -> List[Dict[str, Any]]:
        """Get health status for all monitored agents."""
        return self._a2a_request("GET", "/health")

    def a2a_agent_health(self, agent_id: Optional[str] = None) -> Dict[str, Any]:
        """Get health status for a specific agent."""
        aid = agent_id or self._agent_id
        if not aid:
            raise CivitasError("No agent_id specified")
        return self._a2a_request("GET", f"/health/{aid}")

    def a2a_audit_log(self) -> List[Dict[str, Any]]:
        """Get the A2A message audit log."""
        return self._a2a_request("GET", "/audit")

    # ─── Task Settlement ─────────────────────────────────────────────

    def task_settle(
        self,
        task_id: str,
        worker_agent: str,
        requester_agent: str,
        success: bool = True,
        reward_amount: int = 100,
        result: str = "",
    ) -> Dict[str, Any]:
        """Settle a completed task — triggers gas deduction, reward split, and risk scoring.

        Settlement enforces CivitasOS philosophical economics:
        - Gas fee deducted from requester (aspect_gap-aware: gap<0.1 → 20% discount, gap>0.3 → 30% surcharge)
        - Reward split: 70% → reputation, 30% → balance (capped at BALANCE_CAP=10,000)
        - On failure: worker's risk_score increases (+5, max 200)
        - Balance overflow returns to circulation (众生之果)

        Args:
            task_id: The task to settle
            worker_agent: Agent that performed the work
            requester_agent: Agent that requested the work
            success: Whether the task succeeded
            reward_amount: Tokens to reward the worker
            result: Result summary

        Returns:
            Dict with settled, reward_applied, gas_fee_charged,
            worker_new_reputation, worker_tier, message
        """
        return self._a2a_request("POST", "/task/settle", {
            "task_id": task_id,
            "worker_agent": worker_agent,
            "requester_agent": requester_agent,
            "success": success,
            "reward_amount": reward_amount,
            "result": result,
        })
