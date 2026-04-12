"""Agent lifecycle mixin: register, evolve, reputation, state."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .models import Agent, CivitasAPIError, CivitasError


class AgentMixin:
    """Agent registration, discovery, evolution, and state management."""

    def register(
        self,
        agent_id: str,
        name: str,
        capabilities: List[str],
        stake: int = 100,
    ) -> Agent:
        """Register a new agent on the network.

        This creates an agent in the core registry (/api/v1/agents).
        For A2A directory registration with capabilities and trust tiers,
        see ``a2a_register()`` or ``a2a_quickstart()``.

        Args:
            agent_id: Unique identifier for the agent
            name: Human-readable name
            capabilities: List of capability tags (e.g. ["compute", "inference"])
            stake: Initial stake amount
        """
        body: Dict[str, Any] = {
            "id": agent_id,
            "name": name,
            "capabilities": capabilities,
            "stake": stake,
        }
        if self._public_key_hex:
            body["public_key"] = self._public_key_hex
        resp = self._post("/agents", body)
        if not resp.success:
            raise CivitasAPIError(resp.error or "Registration failed")
        self._agent_id = agent_id
        return Agent(id=agent_id, name=name, capabilities=capabilities, stake=stake)

    def get_agents(self) -> List[Agent]:
        """List all registered agents."""
        resp = self._get("/agents")
        if not resp.success:
            raise CivitasAPIError(resp.error or "Failed to get agents")
        return [Agent(**a) for a in (resp.data or [])]

    def get_agent(self, agent_id: str) -> Agent:
        """Get a specific agent by ID via A2A registry."""
        data = self._a2a_request("GET", f"/agents/{agent_id}")
        return Agent(**(data if isinstance(data, dict) else {}))

    def evolve(
        self,
        agent_id: Optional[str] = None,
        capabilities: Optional[List[str]] = None,
        stake: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Evolve an agent's capabilities or stake.

        Args:
            agent_id: Agent to evolve (defaults to self)
            capabilities: New capabilities to set
            stake: New stake value
        """
        aid = agent_id or self._agent_id
        if not aid:
            raise CivitasError("No agent_id specified and no agent registered")
        body: Dict[str, Any] = {}
        if capabilities is not None:
            body["capabilities"] = capabilities
        if stake is not None:
            body["stake"] = stake
        resp = self._put(f"/agents/{aid}/evolve", body)
        if not resp.success:
            raise CivitasAPIError(resp.error or "Evolution failed")
        return resp.data

    def get_reputation(self, agent_id: Optional[str] = None) -> Dict[str, Any]:
        """Get reputation scores for an agent.

        Args:
            agent_id: Agent to query (defaults to self)
        """
        aid = agent_id or self._agent_id
        if not aid:
            raise CivitasError("No agent_id specified")
        resp = self._get(f"/reputation/{aid}")
        if not resp.success:
            raise CivitasAPIError(resp.error or "Failed to get reputation")
        return resp.data

    def update_capabilities(
        self,
        capabilities: List[Dict[str, str]],
        agent_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Replace all capabilities for an agent via A2A directory.

        Args:
            capabilities: List of {id, name, description} dicts
            agent_id: Agent to update (defaults to self)
        """
        aid = agent_id or self._agent_id
        if not aid:
            raise CivitasError("No agent_id specified and no agent registered")
        return self._a2a_request("PUT", f"/agents/{aid}/capabilities", {
            "capabilities": capabilities,
        })

    def promote_agent(self, agent_id: str, new_role: str) -> Dict[str, Any]:
        """Promote/demote an agent's role (Admin-only).

        Args:
            agent_id: Target agent to promote
            new_role: One of 'admin', 'operator', 'agent', 'readonly'
        """
        return self._request("POST", "/auth/promote", {
            "agent_id": agent_id,
            "new_role": new_role,
        })

    def agent_state(self, agent_id: str) -> Dict[str, Any]:
        """Agent runtime state snapshot.

        Note:
            Backend route not yet implemented. Reserved for future use.
        """
        raise NotImplementedError(
            "agent_state: backend route GET /agents/:id/state not yet implemented"
        )

    def agent_learn(self, agent_id: str, data: str) -> Dict[str, Any]:
        """Feed learning data to an agent.

        Note:
            Backend route not yet implemented. Reserved for future use.
        """
        raise NotImplementedError(
            "agent_learn: backend route POST /agents/:id/learn not yet implemented"
        )

    def evolution_stats(self) -> Dict[str, Any]:
        """Agent evolution statistics.

        Note:
            Backend route not yet implemented. Reserved for future use.
        """
        raise NotImplementedError(
            "evolution_stats: backend route GET /evolution/stats not yet implemented"
        )

    def evolution_leaderboard(self) -> Dict[str, Any]:
        """Top evolving agents.

        Note:
            Backend route not yet implemented. Reserved for future use.
        """
        raise NotImplementedError(
            "evolution_leaderboard: backend route GET /evolution/leaderboard not yet implemented"
        )
