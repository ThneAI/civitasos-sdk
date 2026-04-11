"""Cluster mixin: state hash, byzantine detection, peers, SLO, audit, auto-repair."""

from __future__ import annotations

from typing import Any, Dict, List

from .models import CivitasAPIError, SLODashboard


class ClusterMixin:
    """Cluster health, state sync, SLO dashboard, audit events."""

    def get_state_hash(self) -> Dict[str, Any]:
        """Get current state Merkle hash."""
        resp = self._get("/sync/hash")
        if not resp.success:
            raise CivitasAPIError(resp.error or "Failed to get state hash")
        return resp.data

    def get_byzantine_suspects(self) -> List[Dict[str, Any]]:
        """Get list of byzantine suspect peers."""
        resp = self._get("/cluster/byzantine")
        if not resp.success:
            raise CivitasAPIError(resp.error or "Failed to get byzantine suspects")
        return resp.data or []

    def get_peers(self) -> List[str]:
        """Get cluster peer list."""
        resp = self._get("/cluster/peers")
        if not resp.success:
            raise CivitasAPIError(resp.error or "Failed to get peers")
        return resp.data or []

    def get_slo_dashboard(self) -> SLODashboard:
        """Get the SLO dashboard snapshot."""
        resp = self._get("/slo/dashboard")
        if not resp.success:
            raise CivitasAPIError(resp.error or "Failed to get SLO dashboard")
        d = resp.data or {}
        req = d.get("request_metrics", {})
        cluster = d.get("cluster_metrics", {})
        return SLODashboard(
            node_id=d.get("node_id", ""),
            uptime_seconds=d.get("uptime_seconds", 0),
            all_slo_pass=d.get("all_slo_pass", False),
            request_total=req.get("total", 0),
            request_errors=req.get("errors", 0),
            p50_ms=req.get("p50_ms", 0),
            p99_ms=req.get("p99_ms", 0),
            agents_count=cluster.get("agents", 0),
            proposals_count=cluster.get("proposals", 0),
            byzantine_suspects=cluster.get("byzantine_suspects", 0),
            state_hash=cluster.get("state_hash", ""),
        )

    def get_audit_events(self) -> List[Dict[str, Any]]:
        """Get the audit event log."""
        resp = self._get("/audit/events")
        if not resp.success:
            raise CivitasAPIError(resp.error or "Failed to get audit events")
        return resp.data or []

    def run_auto_repair(self) -> List[str]:
        """Trigger an auto-repair scan. Returns proposal IDs created."""
        resp = self._post("/auto-repair/scan")
        if not resp.success:
            raise CivitasAPIError(resp.error or "Auto-repair scan failed")
        return (resp.data or {}).get("repair_proposal_ids", [])
