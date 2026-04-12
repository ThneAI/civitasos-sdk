"""CivitasOS Python Agent SDK — modular package.

Usage::

    from civitasos import CivitasAgent

    agent = CivitasAgent("http://localhost:8099")
    agent.generate_keys()
    agent.register("my-agent", "My Agent", ["compute"], stake=500)
    agent.authenticate()
    # DID-based A2A registration:
    agent.a2a_quickstart(name="My Agent", endpoint="http://localhost:9001")
"""

from .models import (
    ApiResponse,
    Agent,
    Proposal,
    SLODashboard,
    CivitasError,
    CivitasConnectionError,
    CivitasAPIError,
    CspServiceUnavailable,
    SYSTEM_AGENTS,
    is_system_agent,
)
from ._core import CoreMixin
from ._agent import AgentMixin
from ._governance import GovernanceMixin
from ._cluster import ClusterMixin
from ._a2a import A2AMixin
from ._pool import PoolMixin
from ._r2r import R2RMixin
from ._advanced import AdvancedMixin


class CivitasAgent(
    CoreMixin,
    AgentMixin,
    GovernanceMixin,
    ClusterMixin,
    A2AMixin,
    PoolMixin,
    R2RMixin,
    AdvancedMixin,
):
    """Client for interacting with a CivitasOS cluster.

    Supports multi-node failover: pass a single URL or a list of seed URLs.
    The SDK will auto-discover all cluster nodes and failover on connection errors.

    Args:
        base_url: Single URL or list of seed URLs (e.g. "http://node1:8099"
                  or ["http://node1:8099", "http://node2:8100"])
        timeout: Request timeout in seconds
        auto_discover: If True, query /api/v1/cluster/discovery to find all nodes
    """
    pass


__all__ = [
    "CivitasAgent",
    "ApiResponse",
    "Agent",
    "Proposal",
    "SLODashboard",
    "CivitasError",
    "CivitasConnectionError",
    "CivitasAPIError",
    "SYSTEM_AGENTS",
    "is_system_agent",
]
