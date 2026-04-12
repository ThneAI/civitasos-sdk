"""CivitasOS data models and exception classes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ApiResponse:
    """Wrapper for CivitasOS API responses."""
    success: bool
    data: Any = None
    error: Optional[str] = None
    hint: Optional[str] = None
    timestamp: int = 0


@dataclass
class Agent:
    """Agent state snapshot."""
    id: str
    name: str
    capabilities: List[str]
    stake: int
    reputation: int = 0
    status: str = "online"


@dataclass
class Proposal:
    """Governance proposal snapshot."""
    id: str
    title: str
    description: str
    proposer: str
    status: str = "active"
    votes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SLODashboard:
    """SLO dashboard snapshot."""
    node_id: str = ""
    uptime_seconds: float = 0
    all_slo_pass: bool = False
    request_total: int = 0
    request_errors: int = 0
    p50_ms: float = 0
    p99_ms: float = 0
    agents_count: int = 0
    proposals_count: int = 0
    byzantine_suspects: int = 0
    state_hash: str = ""


class CivitasError(Exception):
    """Base exception for CivitasOS SDK errors."""
    pass


class CivitasConnectionError(CivitasError):
    """Raised when the CivitasOS node is unreachable."""
    pass


class CivitasAPIError(CivitasError):
    """Raised when the API returns an error."""
    def __init__(self, message: str, status_code: int = 0, hint: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.hint = hint


class CspServiceUnavailable(CivitasError):
    """Raised when a CSP service is required but not configured or unavailable."""
    def __init__(self, service: str):
        super().__init__(f"CSP service '{service}' is not available — configure cognitive_provider with this service")
        self.service = service


# ─── System Agent IDs ────────────────────────────────────────────────
SYSTEM_AGENTS = {
    "@guardian": "Constitutional Guardian — axiom validation, violation adjudication",
    "@reputation": "Reputation Oracle — trust queries, trust proofs, reputation history",
    "@marketplace": "Task Marketplace — post tasks, discover tasks, auto-matching",
    "@settler": "Settlement Coordinator — cross-chain settlement, chain negotiation",
    "@governor": "Governance Coordinator — proposals, voting, parameter changes",
    "@auditor": "System Auditor — audit trails, anomaly detection, compliance",
    "@oracle": "Data Oracle — chain state, timestamps, external data feeds",
}


def is_system_agent(agent_id: str) -> bool:
    """Check if an agent ID belongs to a CivitasOS system agent."""
    return agent_id in SYSTEM_AGENTS
