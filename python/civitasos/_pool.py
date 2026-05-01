"""Task pool mixin: pool, webhooks, subtask rules, auto-claim, worker pattern."""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import quote, urlencode

from .models import CivitasError


class PoolMixin:
    """Task pool, webhooks, subtask rules, auto-claim, worker decorator pattern."""

    def pool_post(
        self,
        required_capability: Optional[str] = None,
        input_data: Any = None,
        reward: int = 100,
        min_reputation: float = 0.0,
        deadline_secs: Optional[int] = None,
        allowed_agents: Optional[List[str]] = None,
        blocked_agents: Optional[List[str]] = None,
        required_stake: int = 0,
        *,
        description: Optional[str] = None,
        required_capabilities: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Post a task to the shared pool for any capable agent to claim.

        Args:
            required_capability: Primary capability needed (e.g. "translation").
            description: Task description (sent as input if input_data is None).
            required_capabilities: Alternative to required_capability (uses first item).
            input_data: Arbitrary JSON input for the task.
            reward: CIV reward for successful completion.
        """
        cap = required_capability
        if not cap and required_capabilities:
            cap = required_capabilities[0]
        if not cap:
            cap = "general"
        body: Dict[str, Any] = {
            "requester": self._agent_id or "anonymous",
            "required_capability": cap,
            "input": input_data or ({"description": description} if description else {}),
            "reward": reward,
            "min_reputation": min_reputation,
        }
        if description:
            body["description"] = description
        if deadline_secs is not None:
            body["deadline_secs"] = deadline_secs
        if allowed_agents:
            body["allowed_agents"] = allowed_agents
        if blocked_agents:
            body["blocked_agents"] = blocked_agents
        if required_stake > 0:
            body["required_stake"] = required_stake
        return self._a2a_request("POST", "/pool/post", body)

    def pool_discover(
        self,
        capability: Optional[str] = None,
        capabilities: Optional[List[str]] = None,
        min_reputation: float = 0.0,
    ) -> List[Dict[str, Any]]:
        """Discover open pool tasks matching capabilities.

        Searches the task pool for claimable tasks. To discover *agents*
        by capability, use ``a2a_discover()`` instead.
        """
        caps: List[str] = capabilities or ([capability] if capability else [])
        aid = self._agent_id or "anonymous"
        return self._a2a_request("POST", "/pool/discover", {
            "agent_id": aid,
            "capabilities": caps,
        })

    def pool_claim(self, task_id: str, agent_id: Optional[str] = None, stake_amount: int = 0) -> Dict[str, Any]:
        """Claim a pool task for execution.

        Args:
            stake_amount: Collateral to lock. Must meet the task's required_stake.
        """
        aid = agent_id or self._agent_id
        if not aid:
            raise CivitasError("No agent_id specified")
        body: Dict[str, Any] = {
            "task_id": task_id,
            "agent_id": aid,
        }
        if stake_amount > 0:
            body["stake_amount"] = stake_amount
        return self._a2a_request("POST", "/pool/claim", body)

    def pool_complete(
        self,
        task_id: str,
        output: Any = None,
        success: bool = True,
    ) -> Dict[str, Any]:
        """Mark a pool task as completed.

        If ``output`` is provided, delegates to ``task_execute`` so the result
        is recorded and settlement occurs.  Otherwise does a simple state flip.
        """
        if output is not None:
            return self.task_execute(task_id=task_id, output=output, success=success)
        return self._a2a_request("POST", f"/pool/complete/{task_id}")

    def pool_fail(self, task_id: str) -> Dict[str, Any]:
        """Mark a pool task as failed."""
        return self._a2a_request("POST", f"/pool/fail/{task_id}")

    def pool_abandon(self, task_id: str) -> Dict[str, Any]:
        """Abandon a claimed pool task (alias for pool_fail).

        Use when the agent cannot complete a task it previously claimed.
        Stake collateral may be forfeited.
        """
        return self.pool_fail(task_id)

    def pool_confirm(self, task_id: str) -> Dict[str, Any]:
        """Requester confirms delivered output — triggers settlement.

        Call this after reviewing the worker's output (status = Delivered).
        Transitions: Delivered → Completed. Worker stake is released and
        reward is paid.
        """
        return self._a2a_request("POST", f"/pool/confirm/{task_id}")

    def pool_dispute(self, task_id: str, reason: str = "") -> Dict[str, Any]:
        """Requester disputes delivered output — penalizes worker.

        Call this when the worker's output is empty, wrong, or low quality.
        Transitions: Delivered → Disputed. Worker stake is forfeited and
        reputation is penalized.
        """
        body: Dict[str, Any] = {}
        if reason:
            body["reason"] = reason
        return self._a2a_request("POST", f"/pool/dispute/{task_id}", body or None)

    def pool_list(self) -> List[Dict[str, Any]]:
        """List all tasks in the pool."""
        return self._a2a_request("GET", "/pool/tasks")

    def pool_get_task(self, task_id: str) -> Dict[str, Any]:
        """Return one pooled task by scanning the current pool snapshot.

        Exposes a stable SDK-level read surface for G.1 challenge-window fields
        such as ``challenge_deadline_at`` and ``failure_reason``. Falls back to
        pool-wide scan for compatibility with older backends.
        """
        try:
            resp = self._a2a_request("GET", f"/pool/tasks/{quote(task_id, safe='')}")
            if isinstance(resp, dict):
                task = resp.get("task") or resp
                if isinstance(task, dict):
                    return task
        except CivitasError:
            pass

        records = self.pool_list()
        if isinstance(records, dict):
            records = records.get("tasks") or records.get("data") or []
        for task in records:
            if isinstance(task, dict) and (
                task.get("id") == task_id or task.get("task_id") == task_id
            ):
                return task
        raise CivitasError(f"pool task not found: {task_id}")

    def pool_failures(
        self,
        agent_id: Optional[str] = None,
        requester_id: Optional[str] = None,
        relation_id: Optional[str] = None,
        since: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Query the failure-time index, optionally scoped to a relation pair."""
        query: Dict[str, Any] = {}
        if agent_id:
            query["agent_id"] = agent_id
        if requester_id:
            query["requester_id"] = requester_id
        if relation_id:
            query["relation_id"] = relation_id
        if since:
            query["since"] = since
        if limit is not None:
            query["limit"] = int(limit)
        path = "/pool/failures"
        if query:
            path = f"{path}?{urlencode(query)}"
        return self._a2a_request("GET", path)

    # ─── Webhooks ────────────────────────────────────────────────────

    def webhook_register(
        self,
        callback_url: str,
        events: Optional[List[str]] = None,
        agent_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Register a webhook subscription for A2A task events.

        Args:
            callback_url: URL to receive webhook POST notifications
            events: List of event types to subscribe to. Defaults to all events.
                Valid events: task.posted, task.claimed, task.completed,
                task.failed, task.settled, agent.registered
            agent_id: Agent registering the webhook (defaults to self)
        """
        return self._a2a_request("POST", "/webhooks/register", {
            "agent_id": agent_id or self._agent_id or "anonymous",
            "callback_url": callback_url,
            "events": events or [
                "task.posted", "task.claimed", "task.completed",
                "task.failed", "task.settled",
            ],
        })

    def webhook_unregister(self, subscription_id: str) -> Dict[str, Any]:
        """Unregister a webhook subscription."""
        return self._a2a_request("POST", "/webhooks/unregister", {
            "subscription_id": subscription_id,
        })

    def webhook_list(self) -> Dict[str, Any]:
        """List all active webhook subscriptions."""
        return self._a2a_request("GET", "/webhooks/list")

    # ─── Subtask Rules ───────────────────────────────────────────────

    def subtask_rule_register(
        self,
        trigger_capability: str,
        subtask_capability: str,
        description: str,
        trigger_on: str = "success",
        reward: int = 100,
    ) -> Dict[str, Any]:
        """Register a dynamic subtask generation rule.

        When a task with trigger_capability is settled, a new subtask
        requiring subtask_capability is automatically created.

        Args:
            trigger_capability: Source capability that triggers generation
            subtask_capability: Capability required for the generated subtask
            description: Description of the subtask
            trigger_on: When to trigger — "success", "failure", or "always"
            reward: Reward for the generated subtask
        """
        return self._a2a_request("POST", "/subtask-rules", {
            "trigger_capability": trigger_capability,
            "subtask_capability": subtask_capability,
            "description": description,
            "trigger_on": trigger_on,
            "reward": reward,
        })

    def subtask_rule_list(self) -> Dict[str, Any]:
        """List all subtask generation rules."""
        return self._a2a_request("GET", "/subtask-rules")

    def subtask_rule_delete(self, rule_id: int) -> Dict[str, Any]:
        """Delete a subtask generation rule by index."""
        return self._a2a_request("DELETE", f"/subtask-rules/{rule_id}")

    # ─── Auto-Claim ──────────────────────────────────────────────────

    def auto_claim_register(
        self,
        capabilities: List[str],
        agent_id: Optional[str] = None,
        min_reward: Optional[int] = None,
        max_reward: Optional[int] = None,
        enabled: bool = True,
    ) -> Dict[str, Any]:
        """Register auto-claim preferences for an agent.

        When a new task is posted matching one of the listed capabilities,
        the agent will automatically claim it (if concurrency allows and
        reward is within range).

        Args:
            capabilities: Capabilities the agent wants to auto-claim
            agent_id: Agent ID (defaults to self)
            min_reward: Minimum reward threshold
            max_reward: Maximum reward threshold
            enabled: Whether auto-claim is active
        """
        body: Dict[str, Any] = {
            "agent_id": agent_id or self._agent_id or "anonymous",
            "capabilities": capabilities,
            "enabled": enabled,
        }
        if min_reward is not None:
            body["min_reward"] = min_reward
        if max_reward is not None:
            body["max_reward"] = max_reward
        return self._a2a_request("POST", "/auto-claim/register", body)

    def auto_claim_list(self) -> Dict[str, Any]:
        """List all auto-claim preferences."""
        return self._a2a_request("GET", "/auto-claim/list")

    def auto_claim_delete(self, agent_id: Optional[str] = None) -> Dict[str, Any]:
        """Remove auto-claim preferences for an agent."""
        aid = agent_id or self._agent_id
        if not aid:
            raise CivitasError("No agent_id specified")
        return self._a2a_request("DELETE", f"/auto-claim/{aid}")

    # ─── Worker Decorator Pattern ────────────────────────────────────

    def task_handler(self, capability: str):
        """Decorator to register a function as a handler for pool tasks.

        Usage::

            agent = CivitasAgent("http://localhost:8099")
            agent.generate_keys()
            agent.register("translator", "Translator", ["translation"])
            agent.authenticate()

            @agent.task_handler("translation")
            def handle_translation(task):
                text = task["input"].get("text", "")
                return {"translated": text.upper()}

            agent.start_worker()   # blocks, polling for tasks
        """
        def decorator(fn: Callable):
            self._task_handlers[capability] = fn
            return fn
        return decorator

    def start_worker(self, poll_interval: float = 5.0, daemon: bool = False):
        """Start polling for pool tasks and dispatching to registered handlers.

        Args:
            poll_interval: Seconds between discover polls
            daemon: If True, run in a background thread and return immediately.
        """
        if not self._task_handlers:
            raise CivitasError("No task handlers registered — use @agent.task_handler(capability)")
        if not self._agent_id:
            raise CivitasError("Agent not registered — call register() first")

        self._worker_running = True
        if daemon:
            t = threading.Thread(target=self._worker_loop, args=(poll_interval,), daemon=True)
            t.start()
            return t
        else:
            self._worker_loop(poll_interval)

    def stop_worker(self):
        """Signal the worker loop to stop after the current poll cycle."""
        self._worker_running = False

    def _worker_loop(self, poll_interval: float):
        """Internal: poll → discover → claim → dispatch → complete/fail."""
        caps = list(self._task_handlers.keys())
        while self._worker_running:
            try:
                result = self.pool_discover(capabilities=caps)
                if isinstance(result, dict):
                    tasks = result.get("tasks", [])
                else:
                    tasks = result if isinstance(result, list) else []
                for task in tasks:
                    if not isinstance(task, dict):
                        continue
                    task_id = task.get("task_id") or task.get("id")
                    cap = task.get("required_capability", "")
                    handler = self._task_handlers.get(cap)
                    if not task_id or not handler:
                        continue
                    try:
                        self.pool_claim(task_id)
                        result = handler(task)
                        self.pool_complete(task_id)
                    except Exception:
                        try:
                            self.pool_fail(task_id)
                        except Exception:
                            pass
            except Exception:
                pass
            time.sleep(poll_interval)
