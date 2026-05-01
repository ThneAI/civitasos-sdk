"""Governance mixin: proposals, voting, constitutional amendments."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .models import CivitasAPIError, CivitasError, Proposal


class GovernanceMixin:
    """Proposals, voting, constitutional guardian, governance store."""

    def create_proposal(
        self,
        title: str,
        description: str,
        proposal_type: str = "ParameterChange",
        proposer: Optional[str] = None,
    ) -> str:
        """Create a governance proposal. Returns proposal ID.

        Args:
            title: Proposal title
            description: Detailed description
            proposal_type: Type (ParameterChange, ValidatorManagement, etc.)
            proposer: Proposer agent ID (defaults to self)
        """
        resp = self._post("/proposals", {
            "title": title,
            "description": description,
            "proposal_type": proposal_type,
            "proposer": proposer or self._agent_id or "anonymous",
        })
        if not resp.success:
            raise CivitasAPIError(resp.error or "Proposal creation failed")
        if isinstance(resp.data, dict):
            return resp.data.get("id", "")
        return str(resp.data) if resp.data else ""

    def get_proposals(self) -> List[Proposal]:
        """List all governance proposals."""
        resp = self._get("/proposals")
        if not resp.success:
            raise CivitasAPIError(resp.error or "Failed to get proposals")
        return [
            Proposal(
                id=p.get("id", ""),
                title=p.get("title", ""),
                description=p.get("description", ""),
                proposer=p.get("proposer", ""),
                status=p.get("status", ""),
                votes=p.get("votes", {}),
            )
            for p in (resp.data or [])
        ]

    def vote(
        self,
        proposal_id: str,
        vote_type: str = "approve",
        voter_id: Optional[str] = None,
        stake: int = 100,
    ) -> Dict[str, Any]:
        """Cast a vote on a proposal.

        Args:
            proposal_id: ID of the proposal
            vote_type: "approve" or "reject"
            voter_id: Voter agent ID (defaults to self)
            stake: Voting stake weight
        """
        resp = self._post("/vote", {
            "proposal_id": proposal_id,
            "voter_id": voter_id or self._agent_id or "anonymous",
            "vote": vote_type,
            "stake": stake,
        })
        if not resp.success:
            raise CivitasAPIError(resp.error or "Vote failed")
        return resp.data

    # ─── Constitutional Guardian Multi-sig ────────────────────────────

    def ratify_amendment(
        self,
        proposal_id: str,
        steward_id: str,
        signature_hex: str,
    ) -> Dict[str, Any]:
        """Submit a steward signature to ratify a pending constitutional amendment.

        Args:
            proposal_id: The amendment proposal ID
            steward_id: The signing steward's ID
            signature_hex: Hex-encoded Ed25519 signature over SHA-256 of content
        """
        return self._request("POST", "/constitution/ratify", {
            "proposal_id": proposal_id,
            "steward_id": steward_id,
            "signature_hex": signature_hex,
        })

    def reject_amendment(
        self,
        proposal_id: str,
        steward_id: str,
    ) -> Dict[str, Any]:
        """Reject a pending constitutional amendment."""
        return self._request("POST", "/constitution/reject", {
            "proposal_id": proposal_id,
            "steward_id": steward_id,
        })

    def get_pending_amendments(self) -> Dict[str, Any]:
        """List pending constitutional amendments awaiting ratification."""
        return self._request("GET", "/constitution/pending")

    def get_stewards(self) -> Dict[str, Any]:
        """List current constitutional stewards and ratification config."""
        return self._request("GET", "/constitution/stewards")

    def add_steward(self, steward_id: str, public_key: str) -> Dict[str, Any]:
        """Add a new constitutional steward.

        Args:
            steward_id: Unique steward identifier
            public_key: Hex-encoded Ed25519 public key
        """
        return self._request("POST", "/constitution/stewards", {
            "id": steward_id,
            "public_key": public_key,
        })

    # ─── Governance Store (advanced) ─────────────────────────────────

    def finalize_proposal(self, proposal_id: str, approved: bool = True) -> Dict[str, Any]:
        """POST /api/v1/governance-store/proposals/:id/finalize."""
        return self._post(f"/governance-store/proposals/{proposal_id}/finalize",
                          {"approved": approved}).data

    def create_normative_revision(
        self,
        proposer: str,
        rule_id: str,
        old_value: Any,
        new_value: Any,
        authority: str = "governance_council",
        source: str = "backend_governance_read_model",
        iem_anchor: Optional[Dict[str, Any]] = None,
        title: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """POST /api/v1/governance-store/normative-revisions."""
        body: Dict[str, Any] = {
            "proposer": proposer,
            "rule_id": rule_id,
            "old_value": old_value,
            "new_value": new_value,
            "authority": authority,
            "source": source,
        }
        if iem_anchor is not None:
            body["iem_anchor"] = iem_anchor
        if title:
            body["title"] = title
        if description:
            body["description"] = description
        return self._post("/governance-store/normative-revisions", body).data

    def get_normative_revision(self, revision_id: str) -> Dict[str, Any]:
        """GET /api/v1/governance-store/normative-revisions/:id."""
        return self._get(f"/governance-store/normative-revisions/{revision_id}").data

    def get_proposal_governed_revision(self, proposal_id: str) -> Dict[str, Any]:
        """GET /api/v1/governance-store/proposals/:id/governed-revision."""
        return self._get(
            f"/governance-store/proposals/{proposal_id}/governed-revision"
        ).data

    def vote_governance_proposal(
        self,
        proposal_id: str,
        voter_id: str,
        choice: str = "yes",
        stake: int = 100,
        delegated: bool = False,
    ) -> Dict[str, Any]:
        """POST /api/v1/governance-store/proposals/:id/vote."""
        return self._post(f"/governance-store/proposals/{proposal_id}/vote", {
            "voter_id": voter_id,
            "choice": choice,
            "stake": stake,
            "delegated": delegated,
        }).data

    def governance_history(self, limit: int = 100) -> Dict[str, Any]:
        """GET /api/v1/governance-store/history."""
        return self._get(f"/governance-store/history?limit={limit}").data

    def governance_stats(self) -> Dict[str, Any]:
        """GET /api/v1/governance-store/stats."""
        return self._get("/governance-store/stats").data
