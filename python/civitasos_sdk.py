"""CivitasOS Python Agent SDK — backward-compatibility wrapper.

The SDK has been modularized into the ``civitasos`` package.
This file re-exports all public symbols so existing code continues to work:

    from civitasos_sdk import CivitasAgent   # still works
    from civitasos import CivitasAgent       # preferred
"""

from civitasos import (  # noqa: F401
    CivitasAgent,
    ApiResponse,
    Agent,
    Proposal,
    SLODashboard,
    CivitasError,
    CivitasConnectionError,
    CivitasAPIError,
    SYSTEM_AGENTS,
    is_system_agent,
)
