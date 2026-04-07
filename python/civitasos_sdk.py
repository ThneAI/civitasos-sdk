"""CivitasOS Python Agent SDK

Provides a simple interface for third-party agents to interact
with the CivitasOS network: register, propose, vote, evolve,
and monitor cluster state.

Supports Ed25519 key generation, signing, and JWT-based authentication.

Usage:
    from civitasos_sdk import CivitasAgent

    agent = CivitasAgent("http://localhost:8099")
    # Generate keys and register with Ed25519 public key
    agent.generate_keys()
    agent.register("my-agent", "My Agent", ["compute", "inference"], stake=500)
    # Authenticate to get JWT
    agent.authenticate()
    # All subsequent calls include Authorization: Bearer header
    proposal_id = agent.create_proposal("Upgrade plan", "Details...", "ParameterChange")
    agent.vote(proposal_id, "approve", stake=100)
    status = agent.get_status()
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# ─── Ed25519 key support (optional dependency: PyNaCl) ───────────────
_HAS_NACL = False
try:
    from nacl.signing import SigningKey, VerifyKey
    from nacl.encoding import HexEncoder
    _HAS_NACL = True
except ImportError:
    pass


@dataclass
class ApiResponse:
    """Wrapper for CivitasOS API responses."""
    success: bool
    data: Any = None
    error: Optional[str] = None
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


# ─── System Agent IDs (鸡蛋同时存在: always available on any node) ────
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


class CivitasConnectionError(CivitasError):
    """Raised when the CivitasOS node is unreachable."""
    pass


class CivitasAPIError(CivitasError):
    """Raised when the API returns an error."""
    def __init__(self, message: str, status_code: int = 0):
        super().__init__(message)
        self.status_code = status_code


class CivitasAgent:
    """Client for interacting with a CivitasOS node.

    Args:
        base_url: Base URL of the CivitasOS API (e.g. "http://localhost:8099")
        timeout: Request timeout in seconds
    """

    def __init__(self, base_url: str = "http://localhost:8099", timeout: int = 10):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._agent_id: Optional[str] = None
        # ─── AP: Auth state ──────────────────────────────────────────
        self._signing_key: Any = None       # nacl.signing.SigningKey
        self._public_key_hex: Optional[str] = None
        self._jwt_token: Optional[str] = None
        self._jwt_expires_at: float = 0.0   # unix timestamp

    @property
    def agent_id(self) -> Optional[str]:
        """The registered agent ID, if any."""
        return self._agent_id

    @property
    def public_key_hex(self) -> Optional[str]:
        """Hex-encoded Ed25519 public key (64 hex chars), if generated."""
        return self._public_key_hex

    # ─── AP: Key management ──────────────────────────────────────────

    def generate_keys(self) -> str:
        """Generate a new Ed25519 key pair. Returns the public key hex.

        Requires the PyNaCl package (``pip install pynacl``).

        Returns:
            64-character hex string of the public key
        """
        if not _HAS_NACL:
            raise CivitasError(
                "PyNaCl is required for Ed25519 key management. "
                "Install with: pip install pynacl"
            )
        self._signing_key = SigningKey.generate()
        self._public_key_hex = self._signing_key.verify_key.encode(
            encoder=HexEncoder
        ).decode("ascii")
        return self._public_key_hex

    def load_keys(self, seed_hex: str) -> str:
        """Load an Ed25519 key pair from a 32-byte seed (64 hex chars).

        Args:
            seed_hex: Hex-encoded 32-byte seed

        Returns:
            Public key hex
        """
        if not _HAS_NACL:
            raise CivitasError(
                "PyNaCl is required for Ed25519 key management. "
                "Install with: pip install pynacl"
            )
        seed_bytes = bytes.fromhex(seed_hex)
        if len(seed_bytes) != 32:
            raise CivitasError(f"Seed must be 32 bytes, got {len(seed_bytes)}")
        self._signing_key = SigningKey(seed_bytes)
        self._public_key_hex = self._signing_key.verify_key.encode(
            encoder=HexEncoder
        ).decode("ascii")
        return self._public_key_hex

    def sign(self, message: bytes) -> str:
        """Sign a message with the agent's Ed25519 private key.

        Args:
            message: Raw bytes to sign

        Returns:
            Hex-encoded 64-byte Ed25519 signature
        """
        if self._signing_key is None:
            raise CivitasError("No signing key — call generate_keys() or load_keys() first")
        signed = self._signing_key.sign(message)
        return signed.signature.hex()

    def authenticate(self) -> str:
        """Authenticate with the CivitasOS node and obtain a JWT.

        Requires that keys have been generated and the agent has been
        registered (with its public key).

        Returns:
            The JWT token string
        """
        if self._signing_key is None:
            raise CivitasError("No signing key — call generate_keys() or load_keys() first")
        if self._agent_id is None:
            raise CivitasError("No agent registered — call register() first")

        # Sign a challenge message (current timestamp)
        challenge = f"civitasos-auth:{int(time.time())}".encode("utf-8")
        signature_hex = self.sign(challenge)
        message_hex = challenge.hex()

        # Call /auth/token (no JWT needed for this endpoint)
        url = f"{self.base_url}/api/v1/auth/token"
        body = json.dumps({
            "agent_id": self._agent_id,
            "signature": signature_hex,
            "message": message_hex,
        }).encode("utf-8")
        req = Request(url, data=body, method="POST")
        req.add_header("Content-Type", "application/json")

        try:
            with urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                self._jwt_token = data["token"]
                self._jwt_expires_at = time.time() + data.get("expires_in", 3600)
                return self._jwt_token
        except HTTPError as e:
            try:
                err = json.loads(e.read().decode("utf-8"))
                raise CivitasAPIError(
                    err.get("error", str(e)), e.code
                )
            except (json.JSONDecodeError, CivitasAPIError):
                raise
            except Exception:
                raise CivitasAPIError(str(e), e.code)
        except URLError as e:
            raise CivitasConnectionError(f"Cannot connect to {url}: {e.reason}")

    def _ensure_auth(self) -> None:
        """Re-authenticate if JWT is expired or missing."""
        if self._jwt_token is None:
            return  # no auth configured — allow unauthenticated calls
        if time.time() >= self._jwt_expires_at - 30:
            self.authenticate()

    # ─── Low-level HTTP ──────────────────────────────────────────────

    def _request(self, method: str, path: str, body: Any = None) -> ApiResponse:
        """Make an HTTP request to the CivitasOS API."""
        self._ensure_auth()
        url = f"{self.base_url}{self.api_prefix}{path}"
        data = json.dumps(body).encode("utf-8") if body else None
        req = Request(url, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        # Inject JWT Bearer token when available
        if self._jwt_token:
            req.add_header("Authorization", f"Bearer {self._jwt_token}")

        try:
            with urlopen(req, timeout=self.timeout) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
                return ApiResponse(
                    success=raw.get("success", False),
                    data=raw.get("data"),
                    error=raw.get("error"),
                    timestamp=raw.get("timestamp", 0),
                )
        except HTTPError as e:
            try:
                body_text = e.read().decode("utf-8")
                raw = json.loads(body_text)
                return ApiResponse(
                    success=False,
                    error=raw.get("error", str(e)),
                    timestamp=int(time.time()),
                )
            except Exception:
                raise CivitasAPIError(str(e), e.code)
        except URLError as e:
            raise CivitasConnectionError(f"Cannot connect to {url}: {e.reason}")

    def _get(self, path: str) -> ApiResponse:
        return self._request("GET", path)

    def _post(self, path: str, body: Any = None) -> ApiResponse:
        return self._request("POST", path, body)

    def _put(self, path: str, body: Any = None) -> ApiResponse:
        return self._request("PUT", path, body)

    # ─── Health ──────────────────────────────────────────────────────

    def ping(self) -> bool:
        """Check if the node is reachable."""
        try:
            resp = self._get("/status")
            return resp.success
        except CivitasError:
            return False

    def get_status(self) -> Dict[str, Any]:
        """Get node status (connected_nodes, active_agents, tps, etc.)."""
        resp = self._get("/status")
        if not resp.success:
            raise CivitasAPIError(resp.error or "Failed to get status")
        return resp.data

    # ─── System Agent discovery (星星之火) ────────────────────────────

    def list_system_agents(self) -> Dict[str, str]:
        """Return the well-known system agents available on every CivitasOS node.

        These agents are bootstrapped automatically when a node starts.
        You can immediately delegate tasks to them without any setup.

        Returns:
            Dict mapping agent ID to description.
        """
        return dict(SYSTEM_AGENTS)

    def ask_guardian(self, action: str) -> Any:
        """Validate an action against the 10 safety axioms via @guardian."""
        return self.delegate_task("@guardian", "axiom-validate", {"action": action})

    def query_reputation(self, agent_id: str) -> Any:
        """Query an agent's reputation score and trust tier via @reputation."""
        return self.delegate_task("@reputation", "reputation-query", {"agent_id": agent_id})

    def post_to_marketplace(self, capability: str, min_reputation: float = 0.3, **kwargs) -> Any:
        """Post a task to @marketplace for matching with capable agents."""
        payload = {"capability": capability, "min_reputation": min_reputation}
        payload.update(kwargs)
        return self.delegate_task("@marketplace", "task-post", payload)

    def find_best_agent(self, capability: str) -> Any:
        """Ask @marketplace to auto-match the best agent for a capability."""
        return self.delegate_task("@marketplace", "task-match", {"capability": capability})

    def negotiate_chain(self, agent_a: str, agent_b: str) -> Any:
        """Ask @settler to negotiate the best settlement chain between two agents."""
        return self.delegate_task("@settler", "chain-negotiate", {"agent_a": agent_a, "agent_b": agent_b})

    # ─── Agent lifecycle ─────────────────────────────────────────────

    def register(
        self,
        agent_id: str,
        name: str,
        capabilities: List[str],
        stake: int = 100,
    ) -> Agent:
        """Register a new agent on the network.

        If keys have been generated (via generate_keys()), the public key
        is included for Ed25519 authentication.

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
        """Get a specific agent by ID."""
        resp = self._get(f"/agents/{agent_id}")
        if not resp.success:
            raise CivitasAPIError(resp.error or f"Agent {agent_id} not found")
        return Agent(**(resp.data or {}))

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

    # ─── Governance ──────────────────────────────────────────────────

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
        # The API returns the proposal object or its ID
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

    # ─── Reputation ──────────────────────────────────────────────────

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

    # ─── Cluster ─────────────────────────────────────────────────────

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

    # ─── SLO Dashboard ───────────────────────────────────────────────

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

    # ─── Audit ───────────────────────────────────────────────────────

    def get_audit_events(self) -> List[Dict[str, Any]]:
        """Get the audit event log."""
        resp = self._get("/audit/events")
        if not resp.success:
            raise CivitasAPIError(resp.error or "Failed to get audit events")
        return resp.data or []

    # ─── Auto-repair ─────────────────────────────────────────────────

    def run_auto_repair(self) -> List[str]:
        """Trigger an auto-repair scan. Returns proposal IDs created."""
        resp = self._post("/auto-repair/scan")
        if not resp.success:
            raise CivitasAPIError(resp.error or "Auto-repair scan failed")
        return (resp.data or {}).get("repair_proposal_ids", [])

    # ─── Convenience ─────────────────────────────────────────────────

    def wait_ready(self, timeout: int = 30) -> bool:
        """Wait for the node to become ready.

        Args:
            timeout: Maximum seconds to wait

        Returns:
            True if node became ready, False if timed out
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.ping():
                return True
            time.sleep(1)
        return False

    def __repr__(self) -> str:
        return f"CivitasAgent(url={self.base_url!r}, agent_id={self._agent_id!r})"

    # ══════════════════════════════════════════════════════════════════
    # A2A (Agent-to-Agent) Protocol methods
    # ══════════════════════════════════════════════════════════════════

    def _a2a_request(self, method: str, path: str, body: Any = None) -> Any:
        """Low-level A2A request (returns raw JSON, no success wrapper)."""
        self._ensure_auth()
        url = f"{self.base_url}/api/v1/a2a{path}"
        data = json.dumps(body).encode("utf-8") if body else None
        req = Request(url, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        if self._jwt_token:
            req.add_header("Authorization", f"Bearer {self._jwt_token}")

        try:
            with urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except HTTPError as e:
            try:
                err_body = json.loads(e.read().decode("utf-8"))
                raise CivitasAPIError(
                    err_body.get("error", str(e)), e.code
                )
            except (json.JSONDecodeError, CivitasAPIError):
                raise
            except Exception:
                raise CivitasAPIError(str(e), e.code)
        except URLError as e:
            raise CivitasConnectionError(f"Cannot connect to {url}: {e.reason}")

    # ─── Agent Card Registry ─────────────────────────────────────────

    def a2a_quickstart(
        self,
        agent_id: str,
        name: str,
        endpoint: str,
        description: str = "",
        credentials: Optional[List[Dict[str, Any]]] = None,
        public_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """One-call agent registration with minimal parameters.

        Args:
            agent_id: Unique agent identifier
            name: Human-readable name
            endpoint: URL where this agent accepts A2A messages
            description: Optional description (auto-generated if omitted)
            credentials: Optional bootstrap credentials for higher initial reputation.
                Each credential is a dict with "type" and type-specific fields:
                - {"type": "identity_verified"}
                - {"type": "stake", "amount": 500}
                - {"type": "referral", "voucher_id": "trusted-agent-1"}
                - {"type": "capability", "capability_id": "data-analysis"}
            public_key: Optional hex-encoded Ed25519 public key (64 hex chars).
                When provided, the key is enrolled so the agent can authenticate
                via /api/v1/auth/token immediately. If omitted and the SDK has a
                generated identity, it is sent automatically.

        Returns:
            Dict with agent card, bootstrap result, and next steps guide
        """
        payload: Dict[str, Any] = {
            "id": agent_id,
            "name": name,
            "endpoint": endpoint,
        }
        if description:
            payload["description"] = description
        if credentials:
            payload["credentials"] = credentials
        pk = public_key or self._public_key_hex
        if pk:
            payload["public_key"] = pk
        result = self._a2a_request("POST", "/quickstart", payload)
        self._agent_id = agent_id
        return result

    def a2a_register(
        self,
        agent_id: str,
        name: str,
        description: str,
        capabilities: List[Dict[str, Any]],
        endpoint: str = "",
        stake: int = 0,
        initial_reputation: float = 0.3,
    ) -> Dict[str, Any]:
        """Register an agent card in the A2A directory.

        Args:
            agent_id: Unique agent identifier
            name: Human-readable name
            description: What this agent does
            capabilities: List of capability dicts with id, name, description
            endpoint: URL where this agent accepts A2A messages
            stake: Initial stake
            initial_reputation: Starting reputation (0.0-1.0)

        Returns:
            Agent card dict with trust tier info
        """
        card = self._a2a_request("POST", "/agents", {
            "id": agent_id,
            "name": name,
            "description": description,
            "endpoint": endpoint,
            "capabilities": capabilities,
            "stake": stake,
            "initial_reputation": initial_reputation,
        })
        self._agent_id = agent_id
        return card

    def a2a_get_agent(self, agent_id: str) -> Dict[str, Any]:
        """Get a specific agent's card from the A2A directory."""
        return self._a2a_request("GET", f"/agents/{agent_id}")

    def a2a_list_agents(self) -> List[Dict[str, Any]]:
        """List all agent cards in the A2A directory."""
        return self._a2a_request("GET", "/agents")

    # ─── Discovery ───────────────────────────────────────────────────

    def a2a_discover(
        self,
        capability_id: Optional[str] = None,
        min_reputation: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """Discover agents by capability and/or minimum reputation.

        Args:
            capability_id: Filter by capability
            min_reputation: Minimum reputation threshold

        Returns:
            List of matching agent cards
        """
        params = []
        if capability_id:
            params.append(f"capability_id={capability_id}")
        if min_reputation is not None:
            params.append(f"min_reputation={min_reputation}")
        qs = "&".join(params)
        path = f"/discover?{qs}" if qs else "/discover"
        return self._a2a_request("GET", path)

    # ─── Task Delegation ─────────────────────────────────────────────

    def a2a_submit_task(
        self,
        to_agent: str,
        capability_id: str,
        input_data: Any,
        from_agent: Optional[str] = None,
        deadline_secs: Optional[int] = None,
        metadata: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Submit a task to another agent.

        Args:
            to_agent: Target agent ID
            capability_id: Which capability to invoke
            input_data: Task input payload
            from_agent: Sender ID (defaults to self)
            deadline_secs: Optional deadline
            metadata: Optional metadata

        Returns:
            Dict with task_id, status, message
        """
        return self._a2a_request("POST", "/task", {
            "from_agent": from_agent or self._agent_id or "anonymous",
            "to_agent": to_agent,
            "capability_id": capability_id,
            "input": input_data,
            "deadline_secs": deadline_secs,
            "metadata": metadata,
        })

    # ─── Reputation & Auth ───────────────────────────────────────────

    def a2a_get_reputation(self, agent_id: Optional[str] = None) -> Dict[str, Any]:
        """Get A2A reputation record with trust tier info.

        Args:
            agent_id: Agent to query (defaults to self)

        Returns:
            Dict with reputation, tier, successful_tasks, etc.
        """
        aid = agent_id or self._agent_id
        if not aid:
            raise CivitasError("No agent_id specified")
        return self._a2a_request("GET", f"/reputation/{aid}")

    def a2a_check_auth(
        self,
        tool_name: str,
        permission_level: str = "write",
        agent_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Check if an agent is authorized for a tool at a given permission level.

        Args:
            tool_name: The tool to check authorization for
            permission_level: "readonly", "write", "admin", or "dangerous"
            agent_id: Agent to check (defaults to self)

        Returns:
            Dict with decision, tier, reputation, reason
        """
        return self._a2a_request("POST", "/auth/check", {
            "agent_id": agent_id or self._agent_id or "anonymous",
            "tool_name": tool_name,
            "permission_level": permission_level,
        })

    # ─── Scheduler ───────────────────────────────────────────────────

    def a2a_register_job(
        self,
        capability_id: str,
        interval_type: str,
        interval_value: str,
        input_data: Any = None,
        agent_id: Optional[str] = None,
        enabled: bool = True,
    ) -> Dict[str, Any]:
        """Register a scheduled recurring job.

        Args:
            capability_id: Capability to invoke on schedule
            interval_type: "seconds", "minutes", "hours", or "cron"
            interval_value: Numeric value or cron expression
            input_data: Job input payload
            agent_id: Agent that owns this job (defaults to self)
            enabled: Whether the job starts enabled

        Returns:
            Job registration response
        """
        return self._a2a_request("POST", "/jobs", {
            "agent_id": agent_id or self._agent_id or "anonymous",
            "capability_id": capability_id,
            "input": input_data or {},
            "interval_type": interval_type,
            "interval_value": interval_value,
            "enabled": enabled,
        })

    def a2a_list_jobs(self, agent_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """List scheduled jobs for an agent."""
        aid = agent_id or self._agent_id
        if not aid:
            raise CivitasError("No agent_id specified")
        return self._a2a_request("GET", f"/jobs/{aid}")

    def a2a_register_trigger(
        self,
        capability_id: str,
        event_type: str,
        event_value: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Register an event trigger.

        Args:
            capability_id: Capability to invoke when triggered
            event_type: "topic_exact", "topic_prefix", "agent_joined", "agent_left",
                        "reputation_changed", "proposal_status"
            event_value: Value for the event pattern (e.g., topic name)
            agent_id: Agent that owns this trigger (defaults to self)

        Returns:
            Trigger registration response
        """
        return self._a2a_request("POST", "/triggers", {
            "agent_id": agent_id or self._agent_id or "anonymous",
            "capability_id": capability_id,
            "event_type": event_type,
            "event_value": event_value,
        })

    # ─── Health ──────────────────────────────────────────────────────

    def a2a_health(self) -> List[Dict[str, Any]]:
        """Get health status for all monitored agents."""
        return self._a2a_request("GET", "/health")

    def a2a_agent_health(self, agent_id: Optional[str] = None) -> Dict[str, Any]:
        """Get health status for a specific agent."""
        aid = agent_id or self._agent_id
        if not aid:
            raise CivitasError("No agent_id specified")
        return self._a2a_request("GET", f"/health/{aid}")

    # ─── Audit ───────────────────────────────────────────────────────

    def a2a_audit_log(self) -> List[Dict[str, Any]]:
        """Get the A2A message audit log."""
        return self._a2a_request("GET", "/audit")

    # ─── Phase B: Task Pool ─────────────────────────────────────────

    def pool_post(
        self,
        required_capability: str,
        input_data: Any = None,
        reward: int = 100,
        min_reputation: float = 0.0,
        deadline_secs: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Post a task to the shared pool for any capable agent to claim."""
        body: Dict[str, Any] = {
            "requester": self._agent_id or "anonymous",
            "required_capability": required_capability,
            "input": input_data or {},
            "reward": reward,
            "min_reputation": min_reputation,
        }
        if deadline_secs is not None:
            body["deadline_secs"] = deadline_secs
        return self._a2a_request("POST", "/pool/post", body)

    def pool_discover(
        self,
        capability: str,
        min_reputation: float = 0.0,
    ) -> List[Dict[str, Any]]:
        """Discover open pool tasks matching a capability."""
        return self._a2a_request("POST", "/pool/discover", {
            "capability": capability,
            "min_reputation": min_reputation,
        })

    def pool_claim(self, task_id: str, agent_id: Optional[str] = None) -> Dict[str, Any]:
        """Claim a pool task for execution."""
        aid = agent_id or self._agent_id
        if not aid:
            raise CivitasError("No agent_id specified")
        return self._a2a_request("POST", "/pool/claim", {
            "task_id": task_id,
            "agent_id": aid,
        })

    def pool_complete(self, task_id: str) -> Dict[str, Any]:
        """Mark a pool task as completed."""
        return self._a2a_request("POST", f"/pool/complete/{task_id}")

    def pool_fail(self, task_id: str) -> Dict[str, Any]:
        """Mark a pool task as failed."""
        return self._a2a_request("POST", f"/pool/fail/{task_id}")

    def pool_list(self) -> List[Dict[str, Any]]:
        """List all tasks in the pool."""
        return self._a2a_request("GET", "/pool/tasks")

    # ─── Phase B: Capability Management ──────────────────────────────

    def update_capabilities(
        self,
        capabilities: List[Dict[str, str]],
        agent_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Replace all capabilities for an agent.

        Args:
            capabilities: List of {id, name, description} dicts
        """
        aid = agent_id or self._agent_id
        if not aid:
            raise CivitasError("No agent_id specified")
        return self._a2a_request("PUT", f"/agents/{aid}/capabilities", capabilities)

    # ─── Phase B: Scheduling ────────────────────────────────────────

    def scheduler_policy(self) -> Dict[str, Any]:
        """Get the current scheduling policy (tier→concurrency limits)."""
        return self._a2a_request("GET", "/scheduler/policy")

    def scheduler_can_accept(
        self, agent_id: str, reputation: float
    ) -> Dict[str, Any]:
        """Check if an agent can accept a new task given its reputation."""
        return self._a2a_request("POST", "/scheduler/can-accept", {
            "agent_id": agent_id,
            "reputation": reputation,
        })

    def scheduler_concurrency(self) -> Dict[str, Any]:
        """Get concurrency stats for all agents."""
        return self._a2a_request("GET", "/scheduler/concurrency")

    # ─── Phase B: Economics ─────────────────────────────────────────

    def economics_metrics(self) -> Dict[str, Any]:
        """Get network economic metrics (total staked, accounts, etc.)."""
        return self._a2a_request("GET", "/economics/metrics")

    def economics_parameters(self) -> Dict[str, Any]:
        """Get current economic parameters (fee rates, inflation, etc.)."""
        return self._a2a_request("GET", "/economics/parameters")

    def economics_adapt(self) -> Dict[str, Any]:
        """Trigger adaptive economic parameter tuning."""
        return self._a2a_request("POST", "/economics/adapt")

    # ─── Phase C: Multi-node Directory ──────────────────────────────

    def directory_publish(
        self,
        agent_id: str,
        name: str,
        endpoint: str,
        capabilities: List[str],
        stake: int = 100,
        reputation: float = 0.5,
        node_id: str = "local",
    ) -> Dict[str, Any]:
        """Publish an agent to the cluster-wide directory."""
        return self._a2a_request("POST", "/directory/publish", {
            "agent_id": agent_id,
            "name": name,
            "endpoint": endpoint,
            "capabilities": capabilities,
            "stake": stake,
            "reputation": reputation,
            "node_id": node_id,
        })

    def directory_discover(self, capability: str) -> List[Dict[str, Any]]:
        """Discover agents across all nodes by capability."""
        return self._a2a_request("POST", "/directory/discover", {
            "capability": capability,
        })

    def directory_list(self) -> List[Dict[str, Any]]:
        """List all entries in the multi-node directory."""
        return self._a2a_request("GET", "/directory/list")

    def directory_sync(self, entries: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Sync directory entries from another node (anti-entropy)."""
        return self._a2a_request("POST", "/directory/sync", entries)

    # ─── Phase C: Reputation Mesh ───────────────────────────────────

    def reputation_mesh_list(self) -> List[Dict[str, Any]]:
        """List all reputation snapshots in the CRDT mesh."""
        return self._a2a_request("GET", "/reputation/mesh")

    def reputation_mesh_sync(
        self, snapshots: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Sync reputation snapshots from another node."""
        return self._a2a_request("POST", "/reputation/mesh/sync", snapshots)

    # ─── AQ: Task Callbacks ─────────────────────────────────────────

    def list_callbacks(self) -> List[Dict[str, Any]]:
        """List all agents that have registered callback endpoints."""
        result = self._a2a_request("GET", "/callbacks")
        return result.get("callbacks", []) if isinstance(result, dict) else result

    # ─── AS: LLM Agent Execution Bridge ─────────────────────────────

    def task_execute(
        self,
        task_id: str,
        output: Any,
        success: bool = True,
        metadata: Optional[Dict[str, str]] = None,
        agent_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Submit a task result via the LLM execution bridge.

        This is the JSON-in/JSON-out execution path (no WASM required).
        Use after claiming a pool task with pool_claim().

        Args:
            task_id: The task pool ID
            output: The result produced by the agent (arbitrary JSON)
            success: Whether the task completed successfully
            metadata: Optional metadata (e.g., model used, execution time)
            agent_id: Agent submitting the result (defaults to self)

        Returns:
            Dict with task_id, status, reputation, tier, output_accepted
        """
        body: Dict[str, Any] = {
            "agent_id": agent_id or self._agent_id or "anonymous",
            "task_id": task_id,
            "output": output,
            "success": success,
        }
        if metadata:
            body["metadata"] = metadata
        return self._a2a_request("POST", "/task/execute", body)

    # ─── AT: Token Refresh ────────────────────────────────────────────

    def refresh_token(self) -> Dict[str, Any]:
        """Refresh the current JWT without re-signing.

        Updates the internal token automatically.

        Returns:
            Dict with token, expires_in, role
        """
        result = self._request("POST", "/auth/refresh")
        if "token" in result:
            self._jwt_token = result["token"]
            self._jwt_expires_at = time.time() + result.get("expires_in", 3600)
        return result

    # ─── AU: Role Promotion ───────────────────────────────────────────

    def promote_agent(self, agent_id: str, new_role: str) -> Dict[str, Any]:
        """Promote/demote an agent's role (Admin-only).

        Args:
            agent_id: Target agent to promote
            new_role: One of 'admin', 'operator', 'agent', 'readonly'

        Returns:
            Dict with agent_id, new_role, assigned_by
        """
        return self._request("POST", "/auth/promote", {
            "agent_id": agent_id,
            "new_role": new_role,
        })

    # ─── AW: DAG Orchestration ────────────────────────────────────────

    def dag_create(
        self,
        steps: List[Dict[str, Any]],
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a task DAG.

        Args:
            steps: List of step dicts with step_id, capability, input, depends_on
            description: Optional DAG description

        Returns:
            Dict with dag_id, status
        """
        body: Dict[str, Any] = {"steps": steps}
        if description:
            body["description"] = description
        return self._request("POST", "/multi/dag", body)

    def dag_get(self, dag_id: str) -> Dict[str, Any]:
        """Get DAG status."""
        return self._request("GET", f"/multi/dag/{dag_id}")

    def dag_execute(self, dag_id: str) -> Dict[str, Any]:
        """Start executing a DAG."""
        return self._request("POST", f"/multi/dag/{dag_id}/execute")

    def dag_step_complete(
        self, dag_id: str, step_id: str, output: Any
    ) -> Dict[str, Any]:
        """Mark a DAG step as completed with output."""
        return self._request(
            "POST", f"/multi/dag/{dag_id}/step/{step_id}/complete", {"output": output}
        )

    def dag_step_fail(
        self, dag_id: str, step_id: str, error: str
    ) -> Dict[str, Any]:
        """Mark a DAG step as failed."""
        return self._request(
            "POST", f"/multi/dag/{dag_id}/step/{step_id}/fail", {"error": error}
        )

    def dag_list(self) -> Dict[str, Any]:
        """List all DAGs."""
        return self._request("GET", "/multi/dag")

    # ─── AX: Shared KV Store ─────────────────────────────────────────

    def kv_set(self, key: str, value: Any) -> Dict[str, Any]:
        """Set a shared key-value pair."""
        return self._request("PUT", f"/multi/kv/{key}", {"value": value})

    def kv_get(self, key: str) -> Dict[str, Any]:
        """Get a value by key."""
        return self._request("GET", f"/multi/kv/{key}")

    def kv_delete(self, key: str) -> Dict[str, Any]:
        """Delete a key."""
        return self._request("DELETE", f"/multi/kv/{key}")

    def kv_list(self) -> Dict[str, Any]:
        """List all keys."""
        return self._request("GET", "/multi/kv")

    # ─── AY: Marketplace ─────────────────────────────────────────────

    def market_create_listing(
        self,
        capability: str,
        price: int,
        description: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a marketplace listing."""
        return self._request("POST", "/multi/market/list", {
            "agent_id": agent_id or self._agent_id or "anonymous",
            "capability": capability,
            "price": price,
            "description": description or "",
        })

    def market_search(
        self,
        capability: Optional[str] = None,
        max_price: Optional[int] = None,
        min_rating: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Search marketplace listings."""
        params = {}
        if capability:
            params["capability"] = capability
        if max_price is not None:
            params["max_price"] = str(max_price)
        if min_rating is not None:
            params["min_rating"] = str(min_rating)
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        path = f"/multi/market/search?{qs}" if qs else "/multi/market/search"
        return self._request("GET", path)

    def market_bid(
        self,
        capability: str,
        max_price: int,
        min_rating: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Find best match for a capability request."""
        return self._request("POST", "/multi/market/bid", {
            "capability": capability,
            "max_price": max_price,
            "min_rating": min_rating,
        })

    def market_stats(self) -> Dict[str, Any]:
        """Get marketplace statistics."""
        return self._request("GET", "/multi/market/stats")

    # ─── R2R: Relation-aware Runtime Protocol ────────────────────────

    def r2r_propose_relation(
        self,
        from_agent: str,
        to_agent: str,
        relation_type: str = "cooperative",
    ) -> Dict[str, Any]:
        """Propose a new R2R relation between two agents.

        Args:
            from_agent: Initiating agent ID
            to_agent: Target agent ID
            relation_type: cooperative, competitive, supervisory, adversarial, delegated
        """
        return self._request("POST", "/r2r/relations", {
            "from": from_agent,
            "to": to_agent,
            "relation_type": relation_type,
        })

    def r2r_terminate_relation(
        self,
        from_agent: str,
        to_agent: str,
        reason: str = "requested",
    ) -> Dict[str, Any]:
        """Terminate an existing R2R relation.

        Args:
            from_agent: Agent initiating termination
            to_agent: Other agent in the relation
            reason: Reason for termination
        """
        return self._request("POST", "/r2r/relations/terminate", {
            "from": from_agent,
            "to": to_agent,
            "reason": reason,
        })

    def r2r_revive_relation(
        self,
        agent_a: str,
        agent_b: str,
    ) -> Dict[str, Any]:
        """Revive a dormant R2R relation.

        Args:
            agent_a: First agent ID
            agent_b: Second agent ID
        """
        return self._request("PUT", "/r2r/relations/revive", {
            "agent_a": agent_a,
            "agent_b": agent_b,
        })

    def r2r_send_signal(
        self,
        from_agent: str,
        to_agent: str,
        intent: str = "heartbeat",
        payload: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send an R2R signal through relation routing.

        Args:
            from_agent: Sender agent ID
            to_agent: Receiver agent ID
            intent: Signal intent (heartbeat, broadcast, etc.)
            payload: Signal payload data
            correlation_id: Optional correlation ID for request-response pairing
        """
        body: Dict[str, Any] = {
            "from": from_agent,
            "to": to_agent,
            "intent": intent,
            "payload": payload or {},
        }
        if correlation_id:
            body["correlation_id"] = correlation_id
        return self._request("POST", "/r2r/signals", body)

    def r2r_send_task(
        self,
        from_agent: str,
        to_agent: str,
        capability_id: str,
        task_input: Optional[Dict[str, Any]] = None,
        deadline_secs: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Dispatch a task via R2R relation routing.

        Args:
            from_agent: Task requester agent ID
            to_agent: Task executor agent ID
            capability_id: Required capability
            task_input: Task input data
            deadline_secs: Optional deadline in seconds
        """
        body: Dict[str, Any] = {
            "from": from_agent,
            "to": to_agent,
            "capability_id": capability_id,
            "input": task_input or {},
        }
        if deadline_secs is not None:
            body["deadline_secs"] = deadline_secs
        return self._request("POST", "/r2r/tasks", body)

    def r2r_report_completion(
        self,
        task_id: str,
        success: bool = True,
    ) -> Dict[str, Any]:
        """Report task completion to update aspect metrics.

        Args:
            task_id: The task ID returned from r2r_send_task
            success: Whether the task completed successfully
        """
        return self._request("POST", "/r2r/tasks/complete", {
            "task_id": task_id,
            "success": success,
        })

    def r2r_rate_peer(
        self,
        rater: str,
        rated: str,
        dimension: str = "quality",
        score: float = 0.8,
    ) -> Dict[str, Any]:
        """Submit a peer rating.

        Args:
            rater: Agent submitting the rating
            rated: Agent being rated
            dimension: reliability, quality, responsiveness, honesty
            score: Rating score between 0.0 and 1.0
        """
        return self._request("POST", "/r2r/rate", {
            "rater": rater,
            "rated": rated,
            "dimension": dimension,
            "score": score,
        })

    def r2r_social_graph(self, agent_id: str) -> Dict[str, Any]:
        """Get agent's social graph (relations, essence, aspect, stats).

        Args:
            agent_id: The agent to query
        """
        return self._request("GET", f"/r2r/social-graph/{agent_id}")

    def r2r_aspect_gap(self, agent_id: str) -> Dict[str, Any]:
        """Get aspect gap report (self-view vs social-view divergence).

        Args:
            agent_id: The agent to analyze
        """
        return self._request("GET", f"/r2r/aspect-gap/{agent_id}")

    def r2r_detect_adversarial(self, agent_id: str) -> Dict[str, Any]:
        """Detect adversarial behavior for an agent.

        Args:
            agent_id: The agent to check
        """
        return self._request("GET", f"/r2r/adversarial/{agent_id}")

    def r2r_maintenance(self) -> Dict[str, Any]:
        """Run R2R maintenance cycle (temperature decay, aspect gap, adversarial detection)."""
        return self._request("POST", "/r2r/maintenance")

    def r2r_stats(self) -> Dict[str, Any]:
        """Get R2R runtime statistics (agents, relations, tracked tasks)."""
        return self._request("GET", "/r2r/stats")

    # ─── BL: API version negotiation ─────────────────────────────────

    def set_api_version(self, version: str = "v1") -> None:
        """Switch API version prefix (v1 or v2).

        Args:
            version: API version string, e.g. "v1" or "v2"
        """
        self._api_version = version

    @property
    def api_prefix(self) -> str:
        """Current API path prefix."""
        return f"/api/{getattr(self, '_api_version', 'v1')}"
