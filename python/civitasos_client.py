"""
CivitasOS Python SDK — compatibility wrapper.

DEPRECATED: Use ``civitasos_sdk.CivitasAgent`` directly instead.

This module re-exports CivitasAgent as CivitasOS for backward compatibility.

Usage:
    from civitasos_client import CivitasOS

    client = CivitasOS("http://127.0.0.1:8099")
    status = client.get_status()
"""

from civitasos_sdk import CivitasAgent as CivitasOS  # noqa: F401

__all__ = ["CivitasOS"]
