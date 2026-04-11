"""Core mixin: transport, auth, key management, multi-node failover."""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .models import (
    ApiResponse,
    CivitasAPIError,
    CivitasConnectionError,
    CivitasError,
    SYSTEM_AGENTS,
)

# ─── Ed25519 key support (required dependency: PyNaCl) ───────────────
from nacl.signing import SigningKey
from nacl.encoding import HexEncoder


class CoreMixin:
    """Init, HTTP transport, auth, key management, health checks, multi-node failover."""

    def __init__(
        self,
        base_url: "str | List[str] | None" = None,
        timeout: int = 10,
        auto_discover: bool = True,
    ):
        # Default: env var CIVITASOS_URL > http://localhost:8099
        if base_url is None:
            base_url = os.environ.get("CIVITASOS_URL", "http://localhost:8099")
        # Normalize to a list of URLs
        if isinstance(base_url, str):
            self._nodes: List[str] = [base_url.rstrip("/")]
        else:
            self._nodes = [u.rstrip("/") for u in base_url]
        self.base_url = self._nodes[0]  # current active node
        self.timeout = timeout
        self._agent_id: Optional[str] = None
        # ─── Auth state ──────────────────────────────────────────────
        self._signing_key: Any = None       # nacl.signing.SigningKey
        self._public_key_hex: Optional[str] = None
        self._jwt_token: Optional[str] = None
        self._jwt_expires_at: float = 0.0   # unix timestamp
        # ─── Multi-node state ────────────────────────────────────────
        self._node_index: int = 0
        self._task_handlers: Dict[str, Any] = {}
        self._worker_running: bool = False
        # Auto-discover cluster nodes on startup
        if auto_discover and len(self._nodes) >= 1:
            try:
                self.discover_nodes()
            except CivitasError:
                pass  # seed node may be offline; proceed with what we have

    # ─── Properties ──────────────────────────────────────────────────

    @property
    def agent_id(self) -> Optional[str]:
        """The registered agent ID, if any."""
        return self._agent_id

    @property
    def public_key_hex(self) -> Optional[str]:
        """Hex-encoded Ed25519 public key (64 hex chars), if generated."""
        return self._public_key_hex

    @property
    def nodes(self) -> List[str]:
        """All known cluster node URLs."""
        return list(self._nodes)

    # ─── Multi-node discovery & failover ─────────────────────────────

    def discover_nodes(self) -> List[Dict[str, Any]]:
        """Query the current node's /api/v1/cluster/discovery to find all nodes.

        Returns list of node info dicts with address, status, active_agents, etc.
        Healthy nodes are added to the internal node list for failover.
        """
        resp = self._get("/cluster/discovery")
        if not resp.success or not resp.data:
            return []
        nodes_data = resp.data.get("nodes", [])
        for node in nodes_data:
            addr = node.get("address", "")
            if addr and node.get("status") == "healthy":
                normalized = addr.rstrip("/")
                if normalized not in self._nodes:
                    self._nodes.append(normalized)
        return nodes_data

    def _failover(self) -> bool:
        """Switch to the next available node. Returns True if a new node was found."""
        if len(self._nodes) <= 1:
            return False
        original_index = self._node_index
        for _ in range(len(self._nodes) - 1):
            self._node_index = (self._node_index + 1) % len(self._nodes)
            candidate = self._nodes[self._node_index]
            try:
                req = Request(f"{candidate}/healthz", method="GET")
                with urlopen(req, timeout=2) as resp:
                    if resp.status == 200:
                        self.base_url = candidate
                        return True
            except Exception:
                continue
        self._node_index = original_index
        return False

    # ─── Key management ──────────────────────────────────────────────

    def generate_keys(self) -> str:
        """Generate a new Ed25519 key pair. Returns the public key hex."""
        self._signing_key = SigningKey.generate()
        self._public_key_hex = self._signing_key.verify_key.encode(
            encoder=HexEncoder
        ).decode("ascii")
        return self._public_key_hex

    def load_keys(self, seed_hex: str) -> str:
        """Load an Ed25519 key pair from a 32-byte seed (64 hex chars)."""
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

        Returns hex-encoded 64-byte Ed25519 signature.
        """
        if self._signing_key is None:
            raise CivitasError("No signing key — call generate_keys() or load_keys() first")
        signed = self._signing_key.sign(message)
        return signed.signature.hex()

    def authenticate(self) -> str:
        """Authenticate with the CivitasOS node and obtain a JWT.

        Requires that keys have been generated and the agent has been registered.
        """
        if self._signing_key is None:
            raise CivitasError("No signing key — call generate_keys() or load_keys() first")
        if self._agent_id is None:
            raise CivitasError("No agent registered — call register() first")

        challenge = f"civitasos-auth:{int(time.time())}".encode("utf-8")
        signature_hex = self.sign(challenge)
        message_hex = challenge.hex()

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
                raise CivitasAPIError(err.get("error", str(e)), e.code)
            except (json.JSONDecodeError, CivitasAPIError):
                raise
            except Exception:
                raise CivitasAPIError(str(e), e.code)
        except URLError as e:
            raise CivitasConnectionError(f"Cannot connect to {url}: {e.reason}")

    def _ensure_auth(self) -> None:
        """Re-authenticate if JWT is expired or missing."""
        if self._jwt_token is None:
            return
        if time.time() >= self._jwt_expires_at - 30:
            self.authenticate()

    # ─── Low-level HTTP ──────────────────────────────────────────────

    def _request(self, method: str, path: str, body: Any = None) -> ApiResponse:
        """Make an HTTP request to the CivitasOS API with automatic failover."""
        self._ensure_auth()
        url = f"{self.base_url}{self.api_prefix}{path}"
        data = json.dumps(body).encode("utf-8") if body else None
        req = Request(url, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        if self._jwt_token:
            req.add_header("Authorization", f"Bearer {self._jwt_token}")

        try:
            with urlopen(req, timeout=self.timeout) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
                return ApiResponse(
                    success=raw.get("success", False),
                    data=raw.get("data"),
                    error=raw.get("error"),
                    hint=raw.get("hint"),
                    timestamp=raw.get("timestamp", 0),
                )
        except HTTPError as e:
            try:
                body_text = e.read().decode("utf-8")
                raw = json.loads(body_text)
                return ApiResponse(
                    success=False,
                    error=raw.get("error", str(e)),
                    hint=raw.get("hint"),
                    timestamp=int(time.time()),
                )
            except Exception:
                raise CivitasAPIError(str(e), e.code)
        except URLError as e:
            if self._failover():
                return self._request(method, path, body)
            raise CivitasConnectionError(f"Cannot connect to {url}: {e.reason}")

    def _get(self, path: str) -> ApiResponse:
        return self._request("GET", path)

    def _post(self, path: str, body: Any = None) -> ApiResponse:
        return self._request("POST", path, body)

    def _put(self, path: str, body: Any = None) -> ApiResponse:
        return self._request("PUT", path, body)

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
                hint = err_body.get("hint", "")
                msg = err_body.get("error", str(e))
                if hint:
                    msg = f"{msg} (hint: {hint})"
                raise CivitasAPIError(msg, e.code, hint=hint)
            except (json.JSONDecodeError, CivitasAPIError):
                raise
            except Exception:
                raise CivitasAPIError(str(e), e.code)
        except URLError as e:
            if self._failover():
                return self._a2a_request(method, path, body)
            raise CivitasConnectionError(f"Cannot connect to {url}: {e.reason}")

    # ─── API version ─────────────────────────────────────────────────

    def set_api_version(self, version: str = "v1") -> None:
        """Switch API version prefix (v1 or v2)."""
        self._api_version = version

    @property
    def api_prefix(self) -> str:
        """Current API path prefix."""
        return f"/api/{getattr(self, '_api_version', 'v1')}"

    # ─── Health & convenience ────────────────────────────────────────

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

    def list_system_agents(self) -> Dict[str, str]:
        """Return the well-known system agents available on every CivitasOS node."""
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

    def wait_ready(self, timeout: int = 30) -> bool:
        """Wait for the node to become ready.

        Args:
            timeout: Maximum seconds to wait
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.ping():
                return True
            time.sleep(1)
        return False

    def __repr__(self) -> str:
        return f"CivitasAgent(url={self.base_url!r}, agent_id={self._agent_id!r})"
