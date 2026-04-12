"""CivitasOS ↔ CrewAI Adapter

Wraps a CrewAI crew or agent as a CivitasOS citizen. The adapter handles:
- Registration with the CivitasOS network
- Mapping CivitasOS tasks to CrewAI tasks
- Result conversion and reputation feedback

Usage:
    from crewai import Agent, Task, Crew
    from adapters.crewai_adapter import CivitasCrewAgent

    researcher = Agent(role="Researcher", goal="Research topics", ...)
    civitas = CivitasCrewAgent(
        base_url="http://localhost:8099",
        alias="crew-researcher",
        name="CrewAI Researcher",
        capabilities=[{"id": "research", "name": "Research", "description": "Deep research"}],
    )
    civitas.wrap(researcher)
    civitas.run()
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional

from civitasos_sdk import CivitasAgent


class CivitasCrewAgent:
    """Adapter that bridges a CrewAI agent into CivitasOS."""

    def __init__(
        self,
        base_url: str = "http://localhost:8099",
        alias: str = "crewai-agent",
        name: str = "CrewAI Agent",
        description: str = "A CrewAI-powered agent on CivitasOS",
        capabilities: Optional[List[Dict[str, str]]] = None,
        endpoint: str = "",
        poll_interval: int = 5,
    ):
        self.client = CivitasAgent(base_url)
        self.alias = alias
        self.name = name
        self.description = description
        self.capabilities = capabilities or [
            {"id": "general", "name": "General", "description": "General purpose task"}
        ]
        self.endpoint = endpoint
        self.poll_interval = poll_interval
        self._crew_agent: Any = None
        self._crew: Any = None

    def wrap(self, crew_agent_or_crew: Any) -> "CivitasCrewAgent":
        """Wrap a CrewAI Agent or Crew for CivitasOS execution.

        Args:
            crew_agent_or_crew: A CrewAI Agent or Crew instance
        """
        # Check if it's a Crew (has .kickoff())
        if hasattr(crew_agent_or_crew, "kickoff"):
            self._crew = crew_agent_or_crew
        # Or a CrewAI Agent (has .execute_task())
        elif hasattr(crew_agent_or_crew, "execute_task"):
            self._crew_agent = crew_agent_or_crew
        else:
            raise TypeError(
                f"Expected a CrewAI Agent or Crew, got {type(crew_agent_or_crew)}"
            )
        return self

    def register(self) -> Dict[str, Any]:
        """Register this agent with CivitasOS."""
        self.client.generate_keys()
        return self.client.a2a_register(
            name=self.name, description=self.description,
            capabilities=self.capabilities, endpoint=self.endpoint,
            alias=self.alias,
        )

    def run(self, max_iterations: Optional[int] = None) -> None:
        """Start the work loop: discover → claim → execute → repeat."""
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
        """Claim and execute a single task using CrewAI."""
        task_id = task.get("id", task.get("task_id", ""))
        try:
            self.client.pool_claim(task_id)
            print(f"[CivitasOS] Claimed task {task_id}")

            input_data = task.get("input", {})

            if self._crew:
                # Run entire crew
                result = self._crew.kickoff(inputs=input_data)
                output = {"result": str(result)}
            elif self._crew_agent:
                # Run single agent
                description = input_data.get("description", str(input_data))
                try:
                    from crewai import Task as CrewTask
                    crew_task = CrewTask(description=description, agent=self._crew_agent)
                    result = self._crew_agent.execute_task(crew_task)
                except ImportError:
                    result = str(input_data)
                output = {"result": str(result)}
            else:
                output = {"error": "No CrewAI agent or crew wrapped"}

            self.client.task_execute(
                task_id=task_id, output=output, success=True,
                metadata={"framework": "crewai"},
            )
            print(f"[CivitasOS] Completed task {task_id}")

        except Exception as e:
            print(f"[CivitasOS] Task {task_id} failed: {e}")
            try:
                self.client.pool_fail(task_id)
            except Exception:
                pass
