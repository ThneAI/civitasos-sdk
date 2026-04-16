"""R2R (Relation-aware Runtime) protocol mixin."""

from __future__ import annotations

from typing import Any, Dict, Optional


class R2RMixin:
    """R2R protocol: relations, signals, tasks, ratings, social graph, trust."""

    def r2r_propose_relation(
        self,
        to_agent: str,
        relation_type: str = "cooperative",
        from_agent: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Propose a new R2R relation between two agents.

        Args:
            to_agent: Target agent ID
            relation_type: cooperative, competitive, supervisory, adversarial, delegated
            from_agent: Initiating agent ID (defaults to self.agent_id)
        """
        return self._request("POST", "/r2r/relations", {
            "from": from_agent or self._agent_id,
            "to": to_agent,
            "relation_type": relation_type,
        })

    def r2r_terminate_relation(
        self,
        to_agent: str,
        reason: str = "requested",
        from_agent: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Terminate an existing R2R relation.

        Args:
            to_agent: Other agent in the relation
            reason: Reason for termination
            from_agent: Agent initiating termination (defaults to self.agent_id)
        """
        return self._request("POST", "/r2r/relations/terminate", {
            "from": from_agent or self._agent_id,
            "to": to_agent,
            "reason": reason,
        })

    def r2r_revive_relation(
        self,
        to_agent: str,
        from_agent: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Revive a dormant R2R relation.

        Args:
            to_agent: Other agent in the relation
            from_agent: Agent initiating revival (defaults to self.agent_id)
        """
        a = from_agent or self._agent_id
        return self._request("PUT", "/r2r/relations/revive", {
            "agent_a": a,
            "agent_b": to_agent,
        })

    def r2r_send_signal(
        self,
        to_agent: str,
        intent: str = "heartbeat",
        payload: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
        from_agent: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send an R2R signal through relation routing.

        Args:
            to_agent: Receiver agent ID
            intent: Signal intent (heartbeat, broadcast, etc.)
            payload: Signal payload data
            correlation_id: Optional correlation ID for request-response pairing
            from_agent: Sender agent ID (defaults to self.agent_id)
        """
        body: Dict[str, Any] = {
            "from": from_agent or self._agent_id,
            "to": to_agent,
            "intent": intent,
            "payload": payload or {},
        }
        if correlation_id:
            body["correlation_id"] = correlation_id
        return self._request("POST", "/r2r/signals", body)

    def r2r_send_task(
        self,
        to_agent: str,
        capability_id: str,
        task_input: Optional[Dict[str, Any]] = None,
        deadline_secs: Optional[int] = None,
        from_agent: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Dispatch a task via R2R relation routing.

        Args:
            to_agent: Task executor agent ID
            capability_id: Required capability
            task_input: Task input data
            deadline_secs: Optional deadline in seconds
            from_agent: Task requester agent ID (defaults to self.agent_id)
        """
        body: Dict[str, Any] = {
            "from": from_agent or self._agent_id,
            "to": to_agent,
            "capability_id": capability_id,
            "input": task_input or {},
        }
        if deadline_secs is not None:
            body["deadline_secs"] = deadline_secs
        return self._request("POST", "/r2r/tasks", body)

    def r2r_report_completion(
        self,
        task_id: str,
        success: bool = True,
    ) -> Dict[str, Any]:
        """Report task completion to update aspect metrics."""
        return self._request("POST", "/r2r/tasks/complete", {
            "task_id": task_id,
            "success": success,
        })

    def r2r_rate_peer(
        self,
        rated: str,
        dimension: str = "quality",
        score: float = 0.8,
        rater: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Submit a peer rating.

        Args:
            rated: Agent being rated
            dimension: reliability, quality, responsiveness, honesty
            score: Rating score between 0.0 and 1.0
            rater: Agent submitting the rating (defaults to self.agent_id)
        """
        return self._request("POST", "/r2r/rate", {
            "rater": rater or self._agent_id,
            "rated": rated,
            "dimension": dimension,
            "score": score,
        })

    def r2r_get_relations(self, agent_id: str) -> Dict[str, Any]:
        """List all R2R relations for a specific agent."""
        return self._request("GET", f"/r2r/relations/{agent_id}")

    def r2r_social_graph(self, agent_id: str) -> Dict[str, Any]:
        """Get agent's social graph (relations, essence, aspect, stats)."""
        return self._request("GET", f"/r2r/social-graph/{agent_id}")

    def r2r_aspect_gap(self, agent_id: str) -> Dict[str, Any]:
        """Get aspect gap report (self-view vs social-view divergence)."""
        return self._request("GET", f"/r2r/aspect-gap/{agent_id}")

    def r2r_detect_adversarial(self, agent_id: str) -> Dict[str, Any]:
        """Detect adversarial behavior for an agent."""
        return self._request("GET", f"/r2r/adversarial/{agent_id}")

    def r2r_maintenance(self) -> Dict[str, Any]:
        """Run R2R maintenance cycle (temperature decay, aspect gap, adversarial detection)."""
        return self._request("POST", "/r2r/maintenance")

    def r2r_stats(self) -> Dict[str, Any]:
        """Get R2R runtime statistics (agents, relations, tracked tasks)."""
        return self._request("GET", "/r2r/stats")

    def r2r_flow_health(self) -> Dict[str, Any]:
        """Get R2R relationship flow health (alias for r2r_stats).

        Returns network_density, online_agents, active_relations, etc.
        Used by the runtime to assess peer trust environment.
        """
        return self.r2r_stats()

    def r2r_discover_by_trust(
        self,
        agent_id: str,
        capability: Optional[str] = None,
        max_hops: int = 3,
    ) -> Dict[str, Any]:
        """Discover agents reachable via transitive trust paths.

        Args:
            agent_id: The starting agent
            capability: Optional capability filter
            max_hops: Maximum hops in trust chain (default 3, max 6)
        """
        params = f"?max_hops={max_hops}"
        if capability:
            params += f"&capability={capability}"
        return self._request("GET", f"/r2r/discover/{agent_id}{params}")

    def r2r_immune_response(self, agent_id: str) -> Dict[str, Any]:
        """Trigger immune system response for an agent (quarantine/cool-down)."""
        return self._request("POST", f"/r2r/immune-response/{agent_id}")

    def r2r_poll_inbox(self, agent_id: Optional[str] = None) -> Dict[str, Any]:
        """Poll for pending R2R signals/tasks delivered while agent was offline.

        Returns queued messages (signals, task requests, lifecycle events)
        and clears the inbox. Call periodically to receive R2R messages.

        Args:
            agent_id: Agent ID to poll for (defaults to self.agent_id)
        """
        aid = agent_id or self._agent_id
        return self._request("GET", f"/r2r/inbox/{aid}")
