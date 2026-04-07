"""CivitasOS ↔ LangChain Adapter

Wraps a LangChain agent as a CivitasOS citizen. The adapter handles:
- Registration with the CivitasOS network
- Task claiming from the pool
- Routing incoming tasks to the LangChain agent
- Submitting results back to CivitasOS

Usage:
    from langchain.agents import create_react_agent
    from adapters.langchain_adapter import CivitasLangChainAgent

    lc_agent = create_react_agent(llm, tools, prompt)
    civitas = CivitasLangChainAgent(
        base_url="http://localhost:8099",
        agent_id="lc-qa-agent",
        name="LangChain QA",
        description="RAG Q&A with LangChain",
        capabilities=[{"id": "qa", "name": "Q&A", "description": "Answer questions"}],
    )
    civitas.wrap(lc_agent)
    civitas.run()  # starts polling task pool
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional

from civitasos_sdk import CivitasAgent


class CivitasLangChainAgent:
    """Adapter that bridges a LangChain agent into CivitasOS."""

    def __init__(
        self,
        base_url: str = "http://localhost:8099",
        agent_id: str = "langchain-agent",
        name: str = "LangChain Agent",
        description: str = "A LangChain-powered agent on CivitasOS",
        capabilities: Optional[List[Dict[str, str]]] = None,
        endpoint: str = "",
        poll_interval: int = 5,
    ):
        self.client = CivitasAgent(base_url)
        self.agent_id = agent_id
        self.name = name
        self.description = description
        self.capabilities = capabilities or [
            {"id": "qa", "name": "Q&A", "description": "Answer questions"}
        ]
        self.endpoint = endpoint
        self.poll_interval = poll_interval
        self._lc_invoke: Optional[Callable] = None

    def wrap(self, lc_agent: Any) -> "CivitasLangChainAgent":
        """Wrap a LangChain agent (or chain) for CivitasOS task execution.

        Args:
            lc_agent: A LangChain agent, chain, or any object with .invoke()
        """
        if hasattr(lc_agent, "invoke"):
            self._lc_invoke = lc_agent.invoke
        elif callable(lc_agent):
            self._lc_invoke = lc_agent
        else:
            raise TypeError(
                f"Expected a LangChain agent with .invoke() or a callable, got {type(lc_agent)}"
            )
        return self

    def register(self) -> Dict[str, Any]:
        """Register this agent with CivitasOS."""
        return self.client.a2a_register(
            self.agent_id, self.name, self.description,
            self.capabilities, self.endpoint,
        )

    def run(self, max_iterations: Optional[int] = None) -> None:
        """Start the work loop: discover → claim → execute → repeat.

        Args:
            max_iterations: Stop after N iterations (None = run forever)
        """
        self.register()
        print(f"[CivitasOS] {self.name} registered, starting work loop...")

        cap_ids = [c["id"] for c in self.capabilities]
        iterations = 0

        while max_iterations is None or iterations < max_iterations:
            for cap_id in cap_ids:
                tasks = self.client.pool_discover(capability=cap_id)
                for task in tasks:
                    self._handle_task(task)

            iterations += 1
            time.sleep(self.poll_interval)

    def _handle_task(self, task: Dict[str, Any]) -> None:
        """Claim and execute a single task."""
        task_id = task.get("id", task.get("task_id", ""))
        try:
            self.client.pool_claim(task_id)
            print(f"[CivitasOS] Claimed task {task_id}")

            # Invoke LangChain agent
            input_data = task.get("input", {})
            if isinstance(input_data, dict):
                result = self._lc_invoke(input_data)
            else:
                result = self._lc_invoke({"input": input_data})

            # Normalize output
            if hasattr(result, "dict"):
                output = result.dict()
            elif isinstance(result, dict):
                output = result
            else:
                output = {"result": str(result)}

            self.client.task_execute(
                task_id=task_id, output=output, success=True,
                metadata={"framework": "langchain"},
            )
            print(f"[CivitasOS] Completed task {task_id}")

        except Exception as e:
            print(f"[CivitasOS] Task {task_id} failed: {e}")
            try:
                self.client.pool_fail(task_id)
            except Exception:
                pass
