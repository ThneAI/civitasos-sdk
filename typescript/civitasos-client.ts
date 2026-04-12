/**
 * CivitasOS TypeScript SDK — auto-generated client library.
 *
 * @example
 * ```ts
 * import { CivitasOS } from "./civitasos-client";
 * // Single node
 * const client = new CivitasOS("http://127.0.0.1:8099");
 * // Multi-node with auto-discovery
 * const cluster = new CivitasOS(["http://node1:8099", "http://node2:8100"]);
 * const status = await client.status();
 *
 * // DID-based A2A registration
 * client.generateKeys();
 * const result = await client.quickstart({ name: "My Agent", endpoint: "http://localhost:9001" });
 * console.log(result.did);
 * ```
 */

import { createPrivateKey, createPublicKey, sign, verify, randomBytes, KeyObject } from "node:crypto";

export interface CivitasOSConfig {
    baseUrl: string | string[];
    apiKey?: string;
    /** JWT bearer token for authenticated requests. */
    token?: string;
    timeout?: number;
    /** Agent ID (DID) for pool/task operations. */
    agentId?: string;
    /** Auto-discover cluster nodes on startup (default: true). */
    autoDiscover?: boolean;
}

export class CivitasOS {
    private baseUrl: string;
    private apiKey?: string;
    private token?: string;
    private timeout: number;
    agentId?: string;
    private nodes: string[];
    private nodeIndex = 0;
    /** Ed25519 private key (Node.js KeyObject). */
    private privateKey?: KeyObject;
    /** Ed25519 public key hex (32 bytes, 64 hex chars). */
    private publicKeyHex?: string;

    constructor(baseUrlOrConfig: string | string[] | CivitasOSConfig) {
        if (typeof baseUrlOrConfig === "string") {
            this.nodes = [baseUrlOrConfig.replace(/\/+$/, "")];
            this.timeout = 30_000;
        } else if (Array.isArray(baseUrlOrConfig)) {
            this.nodes = baseUrlOrConfig.map((u) => u.replace(/\/+$/, ""));
            this.timeout = 30_000;
        } else {
            const urls = baseUrlOrConfig.baseUrl;
            if (typeof urls === "string") {
                this.nodes = [urls.replace(/\/+$/, "")];
            } else {
                this.nodes = urls.map((u) => u.replace(/\/+$/, ""));
            }
            this.apiKey = baseUrlOrConfig.apiKey;
            this.token = baseUrlOrConfig.token;
            this.timeout = baseUrlOrConfig.timeout ?? 30_000;
            this.agentId = baseUrlOrConfig.agentId;
        }
        this.baseUrl = this.nodes[0];
    }

    /** Auto-discover cluster nodes. Call after construction if desired. */
    async discoverNodes(): Promise<{ address: string; status: string }[]> {
        try {
            const resp = await this.get<{
                data?: { nodes?: { address: string; status: string }[] };
                nodes?: { address: string; status: string }[];
            }>("/cluster/discovery");
            const nodesData =
                (resp as any)?.data?.nodes ?? (resp as any)?.nodes ?? [];
            for (const n of nodesData) {
                const addr = n.address?.replace(/\/+$/, "");
                if (addr && n.status === "healthy" && !this.nodes.includes(addr)) {
                    this.nodes.push(addr);
                }
            }
            return nodesData;
        } catch {
            return [];
        }
    }

    /** Get all known cluster node URLs. */
    getNodes(): string[] {
        return [...this.nodes];
    }

    /** Set the JWT bearer token for authenticated requests. */
    setToken(token: string) {
        this.token = token;
    }

    /** Clear the current JWT token. */
    clearToken() {
        this.token = undefined;
    }

    /** BL: Set the API version prefix (default "v1"). */
    private apiVersion = "v1";
    setApiVersion(version: "v1" | "v2") {
        this.apiVersion = version;
    }

    // ── helpers ──────────────────────────────────────────────────────────

    private url(path: string): string {
        return `${this.baseUrl}/api/${this.apiVersion}${path}`;
    }

    private async request<T = unknown>(
        method: string,
        path: string,
        body?: unknown
    ): Promise<T> {
        const headers: Record<string, string> = {
            "Content-Type": "application/json",
        };
        if (this.token) headers["Authorization"] = `Bearer ${this.token}`;
        if (this.apiKey) headers["X-API-Key"] = this.apiKey;

        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), this.timeout);

        try {
            const resp = await fetch(this.url(path), {
                method,
                headers,
                body: body !== undefined ? JSON.stringify(body) : undefined,
                signal: controller.signal,
            });
            if (!resp.ok) {
                const text = await resp.text();
                throw new Error(`HTTP ${resp.status}: ${text}`);
            }
            return (await resp.json()) as T;
        } catch (err) {
            // On network error, try failover to next node
            if (
                err instanceof TypeError ||
                (err instanceof DOMException && err.name === "AbortError")
            ) {
                if (await this.failover()) {
                    clearTimeout(timer);
                    return this.request<T>(method, path, body);
                }
            }
            throw err;
        } finally {
            clearTimeout(timer);
        }
    }

    /** Try to switch to the next healthy node. */
    private async failover(): Promise<boolean> {
        if (this.nodes.length <= 1) return false;
        const original = this.nodeIndex;
        for (let i = 0; i < this.nodes.length - 1; i++) {
            this.nodeIndex = (this.nodeIndex + 1) % this.nodes.length;
            const candidate = this.nodes[this.nodeIndex];
            try {
                const ctrl = new AbortController();
                const t = setTimeout(() => ctrl.abort(), 2000);
                const resp = await fetch(`${candidate}/healthz`, {
                    signal: ctrl.signal,
                });
                clearTimeout(t);
                if (resp.ok) {
                    this.baseUrl = candidate;
                    return true;
                }
            } catch {
                continue;
            }
        }
        this.nodeIndex = original;
        return false;
    }

    private get<T = unknown>(path: string) {
        return this.request<T>("GET", path);
    }
    private post<T = unknown>(path: string, body?: unknown) {
        return this.request<T>("POST", path, body);
    }
    private put<T = unknown>(path: string, body?: unknown) {
        return this.request<T>("PUT", path, body);
    }
    private del<T = unknown>(path: string) {
        return this.request<T>("DELETE", path);
    }

    // ── System ───────────────────────────────────────────────────────────

    status() {
        return this.get("/status");
    }
    openapi() {
        return this.get("/openapi.json");
    }

    // ── Agents ───────────────────────────────────────────────────────────

    listAgents() {
        return this.get("/agents");
    }

    // ── Ed25519 Key Management ───────────────────────────────────────────

    /**
     * Generate a new Ed25519 key pair. Returns the public key as hex (64 chars).
     *
     * The public key is used for DID derivation on the server and for signing.
     */
    generateKeys(): string {
        this.privateKey = createPrivateKey({
            key: Buffer.concat([
                // PKCS8 DER prefix for Ed25519: 16 bytes
                Buffer.from("302e020100300506032b657004220420", "hex"),
                randomBytes(32),
            ]),
            format: "der",
            type: "pkcs8",
        });
        const pub = createPublicKey(this.privateKey);
        // Export raw 32-byte public key from SubjectPublicKeyInfo DER
        const spki = pub.export({ format: "der", type: "spki" });
        this.publicKeyHex = (spki as Buffer).subarray(-32).toString("hex");
        return this.publicKeyHex;
    }

    /**
     * Load an Ed25519 key pair from a 32-byte seed (64 hex chars).
     * Returns the public key hex.
     */
    loadKeys(seedHex: string): string {
        const seedBytes = Buffer.from(seedHex, "hex");
        if (seedBytes.length !== 32) {
            throw new Error(`Seed must be 32 bytes, got ${seedBytes.length}`);
        }
        this.privateKey = createPrivateKey({
            key: Buffer.concat([
                Buffer.from("302e020100300506032b657004220420", "hex"),
                seedBytes,
            ]),
            format: "der",
            type: "pkcs8",
        });
        const pub = createPublicKey(this.privateKey);
        const spki = pub.export({ format: "der", type: "spki" });
        this.publicKeyHex = (spki as Buffer).subarray(-32).toString("hex");
        return this.publicKeyHex;
    }

    /** Get the current public key hex, or undefined if not generated. */
    getPublicKeyHex(): string | undefined {
        return this.publicKeyHex;
    }

    /**
     * Sign a message with the agent's Ed25519 private key.
     * Returns hex-encoded 64-byte signature.
     */
    sign(message: Buffer | string): string {
        if (!this.privateKey) {
            throw new Error("No signing key — call generateKeys() or loadKeys() first");
        }
        const buf = typeof message === "string" ? Buffer.from(message) : message;
        const sig = sign(null, buf, this.privateKey);
        return sig.toString("hex");
    }

    /**
     * Verify an Ed25519 signature.
     */
    verify(message: Buffer | string, signatureHex: string, publicKeyHex: string): boolean {
        const pub = createPublicKey({
            key: Buffer.concat([
                Buffer.from("302a300506032b6570032100", "hex"),
                Buffer.from(publicKeyHex, "hex"),
            ]),
            format: "der",
            type: "spki",
        });
        const buf = typeof message === "string" ? Buffer.from(message) : message;
        return verify(null, buf, pub, Buffer.from(signatureHex, "hex"));
    }

    /**
     * Authenticate with the CivitasOS node and obtain a JWT.
     *
     * Requires that keys have been generated and the agent has been registered.
     */
    async authenticate(): Promise<{ token: string; expires_in: number; role: string }> {
        if (!this.privateKey) {
            throw new Error("No signing key — call generateKeys() or loadKeys() first");
        }
        if (!this.agentId) {
            throw new Error("No agent registered — call quickstart() first");
        }
        const challenge = `civitasos-auth:${Math.floor(Date.now() / 1000)}`;
        const signatureHex = this.sign(challenge);
        const messageHex = Buffer.from(challenge).toString("hex");
        const result = await this.post<{ token: string; expires_in: number; role: string }>(
            "/auth/token",
            { agent_id: this.agentId, signature: signatureHex, message: messageHex },
        );
        if (result.token) {
            this.token = result.token;
        }
        return result;
    }

    // ── A2A Registration (DID-based) ─────────────────────────────────────

    /**
     * One-call agent registration with DID derived from Ed25519 public key.
     *
     * Call `generateKeys()` first to create the key pair used for DID derivation.
     *
     * @param opts.name        Human-readable agent name
     * @param opts.endpoint    URL where this agent accepts A2A messages
     * @param opts.description Optional description
     * @param opts.alias       Optional human-readable alias
     * @param opts.credentials Bootstrap credentials for initial reputation boost:
     *   - `{ type: "identity_verified" }`
     *   - `{ type: "stake", amount: 500 }`
     *   - `{ type: "referral", voucher_id: "trusted-agent-1" }`
     *   - `{ type: "capability", capability_id: "data-analysis" }`
     * @param opts.publicKey  Override public key hex (defaults to auto-generated)
     * @returns Agent card with DID, bootstrap result, and next steps guide
     */
    async quickstart(opts: {
        name: string;
        endpoint: string;
        description?: string;
        alias?: string;
        credentials?: Array<Record<string, unknown>>;
        publicKey?: string;
    }) {
        const pk = opts.publicKey ?? this.publicKeyHex;
        if (!pk) {
            throw new Error("public_key is required — call generateKeys() first or pass publicKey");
        }
        const payload: Record<string, unknown> = {
            public_key: pk,
            name: opts.name,
            endpoint: opts.endpoint,
        };
        if (opts.alias) payload.alias = opts.alias;
        if (opts.description) payload.description = opts.description;
        if (opts.credentials) payload.credentials = opts.credentials;

        const result = await this.post<Record<string, unknown>>("/a2a/quickstart", payload);
        const agent = (result.agent as Record<string, unknown>) ?? {};
        this.agentId = (agent.did as string) ?? (result.did as string) ?? (result.agent_id as string) ?? undefined;
        return result;
    }

    /**
     * Full A2A agent card registration with DID derived from public key.
     *
     * Call `generateKeys()` first to create the key pair.
     */
    async a2aRegister(opts: {
        name: string;
        description: string;
        capabilities: Array<{ id: string; name: string; description?: string }>;
        endpoint?: string;
        stake?: number;
        initialReputation?: number;
        alias?: string;
        publicKey?: string;
    }) {
        const pk = opts.publicKey ?? this.publicKeyHex;
        if (!pk) {
            throw new Error("public_key is required — call generateKeys() first or pass publicKey");
        }
        const result = await this.post<Record<string, unknown>>("/a2a/agents", {
            public_key: pk,
            name: opts.name,
            description: opts.description,
            capabilities: opts.capabilities,
            endpoint: opts.endpoint ?? "",
            stake: opts.stake ?? 0,
            initial_reputation: opts.initialReputation ?? 0.3,
            alias: opts.alias,
        });
        const agentData = (result.agent as Record<string, unknown>) ?? {};
        this.agentId = (agentData.did as string) ?? (result.did as string) ?? (result.agent_id as string) ?? undefined;
        return result;
    }

    registerAgent(
        id: string,
        name: string,
        capabilities: string[] = [],
        initialStake = 100
    ) {
        return this.post("/agents", {
            id,
            name,
            capabilities,
            initial_stake: initialStake,
        });
    }

    agentState(agentId: string) {
        return this.get(`/agents/${agentId}/state`);
    }

    agentLearn(agentId: string, data: string) {
        return this.post(`/agents/${agentId}/learn`, { data });
    }

    // ── Governance (AA) ──────────────────────────────────────────────────

    createProposal(
        title: string,
        description: string,
        proposer: string,
        templateId?: string
    ) {
        return this.post("/governance-store/proposals", {
            title,
            description,
            proposer,
            template_id: templateId,
        });
    }

    listProposals(opts?: {
        status?: string;
        proposer?: string;
        search?: string;
        limit?: number;
        offset?: number;
    }) {
        const p = new URLSearchParams();
        if (opts?.status) p.set("status", opts.status);
        if (opts?.proposer) p.set("proposer", opts.proposer);
        if (opts?.search) p.set("search", opts.search);
        p.set("limit", String(opts?.limit ?? 50));
        p.set("offset", String(opts?.offset ?? 0));
        return this.get(`/governance-store/proposals?${p}`);
    }

    getProposal(id: string) {
        return this.get(`/governance-store/proposals/${id}`);
    }

    vote(
        proposalId: string,
        voterId: string,
        choice: "yes" | "no" | "abstain",
        stake = 100,
        delegated = false
    ) {
        return this.post(`/governance-store/proposals/${proposalId}/vote`, {
            voter_id: voterId,
            choice,
            stake,
            delegated,
        });
    }

    finalizeProposal(proposalId: string, approved = true) {
        return this.post(`/governance-store/proposals/${proposalId}/finalize`, {
            approved,
        });
    }

    governanceHistory(limit = 100) {
        return this.get(`/governance-store/history?limit=${limit}`);
    }

    governanceStats() {
        return this.get("/governance-store/stats");
    }

    // ── ZK Proofs (Z) ────────────────────────────────────────────────────

    zkProveMembership(value: string, set: string[], blinding = "default") {
        return this.post("/zk/prove-membership", { value, set, blinding });
    }

    zkProveRange(value: number, threshold: number, blinding = "default") {
        return this.post("/zk/prove-range", { value, threshold, blinding });
    }

    zkProveComputation(
        programHash: string,
        inputHash: string,
        output: string,
        blinding = "default"
    ) {
        return this.post("/zk/prove-computation", {
            program_hash: programHash,
            input_hash: inputHash,
            output,
            blinding,
        });
    }

    zkVerify(proof: unknown) {
        return this.post("/zk/verify", { proof });
    }

    zkStats() {
        return this.get("/zk/stats");
    }

    // ── Multi-Tenant (AB) ────────────────────────────────────────────────

    createTenant(name: string, adminId: string, apiKey?: string) {
        return this.post("/tenants", {
            name,
            admin_id: adminId,
            api_key: apiKey,
        });
    }

    listTenants() {
        return this.get("/tenants");
    }

    getTenant(tenantId: string) {
        return this.get(`/tenants/${tenantId}`);
    }

    suspendTenant(tenantId: string) {
        return this.post(`/tenants/${tenantId}/suspend`);
    }

    activateTenant(tenantId: string) {
        return this.post(`/tenants/${tenantId}/activate`);
    }

    authenticateTenant(apiKey: string) {
        return this.post("/tenants/authenticate", { api_key: apiKey });
    }

    registerResource(
        tenantId: string,
        resourceType: string,
        resourceId: string,
        storageBytes?: number
    ) {
        return this.post(`/tenants/${tenantId}/resources`, {
            resource_type: resourceType,
            resource_id: resourceId,
            storage_bytes: storageBytes,
        });
    }

    updateQuotas(tenantId: string, quotas: Record<string, number>) {
        return this.put(`/tenants/${tenantId}/quotas`, quotas);
    }

    tenantStats() {
        return this.get("/tenants/stats");
    }

    // ── WASM (K) ─────────────────────────────────────────────────────────

    wasmDeploy(name: string, bytecodeB64: string) {
        return this.post("/wasm/contracts", { name, bytecode: bytecodeB64 });
    }

    wasmContracts() {
        return this.get("/wasm/contracts");
    }

    wasmStats() {
        return this.get("/wasm/stats");
    }

    // ── Observability (O2) ───────────────────────────────────────────────

    alertRules() {
        return this.get("/observe/rules");
    }
    firedAlerts() {
        return this.get("/observe/alerts");
    }
    sloStatus() {
        return this.get("/observe/slo");
    }
    logs(limit = 100) {
        return this.get(`/observe/logs?limit=${limit}`);
    }

    // ── Security (S) ─────────────────────────────────────────────────────

    securityScan() {
        return this.get("/security/scan");
    }

    // ── Performance (U) ──────────────────────────────────────────────────

    perfTps() {
        return this.get("/perf/tps");
    }
    perfLatency() {
        return this.get("/perf/latency");
    }

    // ── Evolution (M) ────────────────────────────────────────────────────

    evolutionStats() {
        return this.get("/evolution/stats");
    }
    evolutionLeaderboard() {
        return this.get("/evolution/leaderboard");
    }

    // ── Bridge (L2) ──────────────────────────────────────────────────────

    bridgeChains() {
        return this.get("/bridge/chains");
    }
    bridgeStats() {
        return this.get("/bridge/stats");
    }

    // ── Auth (AT/AU) ─────────────────────────────────────────────────────

    /** POST /auth/token — authenticate with Ed25519 signature, get JWT. */
    authToken(agentId: string, signature: string, message: string) {
        return this.post<{ token: string; expires_in: number; role: string }>(
            "/auth/token",
            { agent_id: agentId, signature, message }
        );
    }

    /** POST /auth/refresh — refresh current JWT without re-signing. */
    authRefresh() {
        return this.post<{ token: string; expires_in: number; role: string }>(
            "/auth/refresh"
        );
    }

    /** POST /auth/promote — promote/demote an agent's role (Admin-only). */
    authPromote(agentId: string, newRole: "admin" | "operator" | "agent" | "readonly") {
        return this.post("/auth/promote", { agent_id: agentId, new_role: newRole });
    }

    /** POST /auth/verify — verify an Ed25519 signature. */
    authVerify(agentId: string, message: string, signature: string) {
        return this.post("/auth/verify", {
            agent_id: agentId,
            message,
            signature,
        });
    }

    // ── DAG Orchestration (AW) ───────────────────────────────────────────

    /** POST /multi/dag — create a task DAG. */
    dagCreate(steps: Array<{ step_id: string; capability: string; input: unknown; depends_on?: string[] }>, description?: string) {
        return this.post<{ dag_id: string; status: string }>(
            "/multi/dag",
            { steps, description }
        );
    }

    /** GET /multi/dag/:id — get DAG status. */
    dagGet(dagId: string) {
        return this.get(`/multi/dag/${dagId}`);
    }

    /** POST /multi/dag/:id/execute — start executing a DAG. */
    dagExecute(dagId: string) {
        return this.post<{ dag_id: string; status: string; ready_steps: string[] }>(
            `/multi/dag/${dagId}/execute`
        );
    }

    /** POST /multi/dag/:id/step/:stepId/complete — mark a step as completed. */
    dagStepComplete(dagId: string, stepId: string, output: unknown) {
        return this.post(`/multi/dag/${dagId}/step/${stepId}/complete`, { output });
    }

    /** POST /multi/dag/:id/step/:stepId/fail — mark a step as failed. */
    dagStepFail(dagId: string, stepId: string, error: string) {
        return this.post(`/multi/dag/${dagId}/step/${stepId}/fail`, { error });
    }

    /** GET /multi/dag — list all DAGs. */
    dagList() {
        return this.get("/multi/dag");
    }

    // ── Shared KV Store (AX) ─────────────────────────────────────────────

    /** PUT /multi/kv/:key — set a key-value pair. */
    kvSet(key: string, value: unknown) {
        return this.put(`/multi/kv/${key}`, { value });
    }

    /** GET /multi/kv/:key — get a value by key. */
    kvGet(key: string) {
        return this.get(`/multi/kv/${key}`);
    }

    /** DELETE /multi/kv/:key — delete a key. */
    kvDelete(key: string) {
        return this.del(`/multi/kv/${key}`);
    }

    /** GET /multi/kv — list all keys. */
    kvList() {
        return this.get("/multi/kv");
    }

    // ── Marketplace (AY) ─────────────────────────────────────────────────

    /** POST /multi/market/list — create a marketplace listing. */
    marketCreateListing(agentId: string, capability: string, price: number, description?: string) {
        return this.post<{ listing_id: string; status: string }>(
            "/multi/market/list",
            { agent_id: agentId, capability, price, description }
        );
    }

    /** GET /multi/market/search — search marketplace listings. */
    marketSearch(opts?: { capability?: string; max_price?: number; min_rating?: number }) {
        const p = new URLSearchParams();
        if (opts?.capability) p.set("capability", opts.capability);
        if (opts?.max_price !== undefined) p.set("max_price", String(opts.max_price));
        if (opts?.min_rating !== undefined) p.set("min_rating", String(opts.min_rating));
        const qs = p.toString();
        return this.get(`/multi/market/search${qs ? "?" + qs : ""}`);
    }

    /** POST /multi/market/bid — find best match for a capability request. */
    marketBid(capability: string, maxPrice: number, minRating?: number) {
        return this.post("/multi/market/bid", {
            capability,
            max_price: maxPrice,
            min_rating: minRating,
        });
    }

    /** GET /multi/market/stats — marketplace statistics. */
    marketStats() {
        return this.get("/multi/market/stats");
    }

    // ── Webhook 推送通知 ─────────────────────────────────────────────────

    /** Register a webhook subscription for A2A task events. */
    webhookRegister(
        callbackUrl: string,
        events: string[] = ["task.posted", "task.claimed", "task.completed", "task.failed", "task.settled"],
        agentId?: string,
    ) {
        return this.post<{ subscription_id: string; agent_id: string; events: string[]; registered: boolean }>(
            "/a2a/webhooks/register",
            { agent_id: agentId, callback_url: callbackUrl, events },
        );
    }

    /** Unregister a webhook subscription. */
    webhookUnregister(subscriptionId: string) {
        return this.post("/a2a/webhooks/unregister", { subscription_id: subscriptionId });
    }

    /** List all active webhook subscriptions. */
    webhookList() {
        return this.get<{ subscriptions: unknown[]; count: number }>("/a2a/webhooks/list");
    }

    // ── 动态任务生成 (Subtask Rules) ─────────────────────────────────────

    /** Register a dynamic subtask generation rule. */
    subtaskRuleRegister(
        triggerCapability: string,
        subtaskCapability: string,
        description: string,
        triggerOn: "success" | "failure" | "always" = "success",
        reward = 100,
    ) {
        return this.post("/a2a/subtask-rules", {
            trigger_capability: triggerCapability,
            subtask_capability: subtaskCapability,
            description,
            trigger_on: triggerOn,
            reward,
        });
    }

    /** List all subtask generation rules. */
    subtaskRuleList() {
        return this.get<{ rules: unknown[]; count: number }>("/a2a/subtask-rules");
    }

    /** Delete a subtask generation rule by index. */
    subtaskRuleDelete(ruleId: number) {
        return this.del(`/a2a/subtask-rules/${ruleId}`);
    }

    // ── Task Pool (A2A Shared Pool) ────────────────────────────────────

    /** POST /a2a/pool/post — post a task to the shared pool. */
    poolPost(
        requiredCapability: string,
        input?: unknown,
        reward = 100,
        minReputation = 0,
        deadlineSecs?: number,
    ) {
        return this.post<{ task_id: string; status: string; auto_claimed_by: string | null }>(
            "/a2a/pool/post",
            {
                requester: this.agentId ?? "anonymous",
                required_capability: requiredCapability,
                input: input ?? {},
                reward,
                min_reputation: minReputation,
                ...(deadlineSecs !== undefined && { deadline_secs: deadlineSecs }),
            },
        );
    }

    /** POST /a2a/pool/discover — discover open tasks matching capabilities. */
    poolDiscover(capabilities: string[]) {
        return this.post<{ agent_id: string; reputation: number; tasks: unknown[]; total: number }>(
            "/a2a/pool/discover",
            { agent_id: this.agentId ?? "anonymous", capabilities },
        );
    }

    /** POST /a2a/pool/claim — claim a pool task. */
    poolClaim(taskId: string, agentId?: string) {
        return this.post<{ claimed: boolean; task: unknown }>(
            "/a2a/pool/claim",
            { task_id: taskId, agent_id: agentId ?? this.agentId ?? "anonymous" },
        );
    }

    /** POST /a2a/pool/complete/:taskId — mark a pool task as completed. */
    poolComplete(taskId: string) {
        return this.post<{ task_id: string; status: string }>(`/a2a/pool/complete/${taskId}`);
    }

    /** POST /a2a/pool/fail/:taskId — mark a pool task as failed. */
    poolFail(taskId: string) {
        return this.post<{ task_id: string; status: string }>(`/a2a/pool/fail/${taskId}`);
    }

    /** GET /a2a/pool/tasks — list all tasks in the pool. */
    poolList() {
        return this.get<{ tasks: unknown[]; total: number }>("/a2a/pool/tasks");
    }

    // ── Task Settlement (哲学经济结算) ───────────────────────────────────

    /**
     * POST /a2a/task/settle — settle a completed task.
     *
     * Triggers gas deduction, reward split (70% reputation / 30% balance),
     * risk scoring, and balance cap enforcement (BALANCE_CAP=10,000).
     */
    taskSettle(opts: {
        taskId: string;
        workerAgent: string;
        requesterAgent: string;
        success?: boolean;
        rewardAmount?: number;
        result?: string;
    }) {
        return this.post<{
            task_id: string;
            settled: boolean;
            worker_new_reputation: number;
            worker_tier: string;
            reward_applied: number;
            gas_fee_charged: number;
            message: string;
        }>("/a2a/task/settle", {
            task_id: opts.taskId,
            worker_agent: opts.workerAgent,
            requester_agent: opts.requesterAgent,
            success: opts.success ?? true,
            reward_amount: opts.rewardAmount ?? 100,
            result: opts.result ?? "",
        });
    }

    // ── Economics (经济引擎查询) ────────────────────────────────────────

    /** GET /economics/accounts — all accounts with balance, reputation, risk_score, potential. */
    economicsAccounts() {
        return this.get<{
            success: boolean;
            data: {
                account_count: number;
                accounts: Array<{
                    id: string;
                    balance: number;
                    reputation_score: number;
                    risk_score: number;
                    staked_amount: number;
                }>;
                circulation: number;
                total_supply: number;
            };
        }>("/economics/accounts");
    }

    /** GET /a2a/economics/gas-market — gas pricing state and parameters. */
    economicsGasMarket() {
        return this.get("/a2a/economics/gas-market");
    }

    // ── 任务自动认领 (Auto-Claim) ────────────────────────────────────────

    /** Register auto-claim preferences for an agent. */
    autoClaimRegister(
        agentId: string,
        capabilities: string[],
        opts?: { minReward?: number; maxReward?: number; enabled?: boolean },
    ) {
        return this.post("/a2a/auto-claim/register", {
            agent_id: agentId,
            capabilities,
            min_reward: opts?.minReward,
            max_reward: opts?.maxReward,
            enabled: opts?.enabled ?? true,
        });
    }

    /** List all auto-claim preferences. */
    autoClaimList() {
        return this.get<{ preferences: unknown[]; count: number }>("/a2a/auto-claim/list");
    }

    /** Remove auto-claim preferences for an agent. */
    autoClaimDelete(agentId: string) {
        return this.del(`/a2a/auto-claim/${agentId}`);
    }

    // ── System Agents (星星之火: always available on any node) ───────────

    /** Well-known system agents bootstrapped on every CivitasOS node. */
    static readonly SYSTEM_AGENTS: Record<string, string> = {
        "@guardian": "Constitutional Guardian — axiom validation, violation adjudication",
        "@reputation": "Reputation Oracle — trust queries, trust proofs, reputation history",
        "@marketplace": "Task Marketplace — post tasks, discover tasks, auto-matching",
        "@settler": "Settlement Coordinator — cross-chain settlement, chain negotiation",
        "@governor": "Governance Coordinator — proposals, voting, parameter changes",
        "@auditor": "System Auditor — audit trails, anomaly detection, compliance",
        "@oracle": "Data Oracle — chain state, timestamps, external data feeds",
    };

    /** Check if an agent ID is a system agent. */
    static isSystemAgent(agentId: string): boolean {
        return agentId in CivitasOS.SYSTEM_AGENTS;
    }

    /** List all system agents available on this node. */
    listSystemAgents(): Record<string, string> {
        return { ...CivitasOS.SYSTEM_AGENTS };
    }

    /** Validate an action against safety axioms via @guardian. */
    askGuardian(action: string) {
        return this.post("/a2a/delegate", {
            to_agent: "@guardian",
            capability_id: "axiom-validate",
            input: { action },
        });
    }

    /** Query an agent's reputation via @reputation. */
    queryReputation(agentId: string) {
        return this.post("/a2a/delegate", {
            to_agent: "@reputation",
            capability_id: "reputation-query",
            input: { agent_id: agentId },
        });
    }

    /** Post a task to @marketplace for auto-matching. */
    postToMarketplace(capability: string, minReputation = 0.3) {
        return this.post("/a2a/delegate", {
            to_agent: "@marketplace",
            capability_id: "task-post",
            input: { capability, min_reputation: minReputation },
        });
    }

    /** Ask @marketplace to find the best agent for a capability. */
    findBestAgent(capability: string) {
        return this.post("/a2a/delegate", {
            to_agent: "@marketplace",
            capability_id: "task-match",
            input: { capability },
        });
    }

    /** Negotiate settlement chain between two agents via @settler. */
    negotiateChain(agentA: string, agentB: string) {
        return this.post("/a2a/delegate", {
            to_agent: "@settler",
            capability_id: "chain-negotiate",
            input: { agent_a: agentA, agent_b: agentB },
        });
    }

    // ── R2R: Relation-aware Runtime Protocol ────────────────────────────

    /** Propose a new R2R relation between two agents. */
    r2rProposeRelation(
        from: string,
        to: string,
        relationType: "cooperative" | "competitive" | "supervisory" | "adversarial" | "delegated" = "cooperative",
    ) {
        return this.post("/r2r/relations", { from, to, relation_type: relationType });
    }

    /** Terminate an existing R2R relation. */
    r2rTerminateRelation(from: string, to: string, reason = "requested") {
        return this.post("/r2r/relations/terminate", { from, to, reason });
    }

    /** Revive a dormant R2R relation. */
    r2rReviveRelation(agentA: string, agentB: string) {
        return this.put("/r2r/relations/revive", { agent_a: agentA, agent_b: agentB });
    }

    /** Send an R2R signal through relation routing. */
    r2rSendSignal(
        from: string,
        to: string,
        intent = "heartbeat",
        payload: Record<string, unknown> = {},
        correlationId?: string,
    ) {
        const body: Record<string, unknown> = { from, to, intent, payload };
        if (correlationId) body.correlation_id = correlationId;
        return this.post("/r2r/signals", body);
    }

    /** Dispatch a task via R2R relation routing. */
    r2rSendTask(
        from: string,
        to: string,
        capabilityId: string,
        input: Record<string, unknown> = {},
        deadlineSecs?: number,
    ) {
        const body: Record<string, unknown> = {
            from, to, capability_id: capabilityId, input,
        };
        if (deadlineSecs !== undefined) body.deadline_secs = deadlineSecs;
        return this.post("/r2r/tasks", body);
    }

    /** Report task completion to update aspect metrics. */
    r2rReportCompletion(taskId: string, success = true) {
        return this.post("/r2r/tasks/complete", { task_id: taskId, success });
    }

    /** Submit a peer rating. */
    r2rRatePeer(
        rater: string,
        rated: string,
        dimension: "reliability" | "quality" | "responsiveness" | "honesty" = "quality",
        score = 0.8,
    ) {
        return this.post("/r2r/rate", { rater, rated, dimension, score });
    }

    /** Get agent's social graph (relations, essence, aspect, stats). */
    r2rSocialGraph(agentId: string) {
        return this.get(`/r2r/social-graph/${agentId}`);
    }

    /** Get aspect gap report (self-view vs social-view divergence). */
    r2rAspectGap(agentId: string) {
        return this.get(`/r2r/aspect-gap/${agentId}`);
    }

    /** Detect adversarial behavior for an agent. */
    r2rDetectAdversarial(agentId: string) {
        return this.get(`/r2r/adversarial/${agentId}`);
    }

    /** Run R2R maintenance cycle. */
    r2rMaintenance() {
        return this.post("/r2r/maintenance");
    }

    /** Get R2R runtime statistics. */
    r2rStats() {
        return this.get("/r2r/stats");
    }

    // ── P3: Trust Transitivity Engine ────────────────────────────────

    /** Discover agents reachable via transitive trust paths. */
    r2rDiscoverByTrust(agentId: string, maxHops = 3, capability?: string) {
        let qs = `?max_hops=${maxHops}`;
        if (capability) qs += `&capability=${encodeURIComponent(capability)}`;
        return this.get(`/r2r/discover/${agentId}${qs}`);
    }

    // ── P5: Adversarial Immune Response ──────────────────────────────

    /** Trigger immune system response for an agent (quarantine/cool-down). */
    r2rImmuneResponse(agentId: string) {
        return this.post(`/r2r/immune-response/${agentId}`);
    }

    // ── P4: Constitutional Guardian Multi-sig ────────────────────────

    /** Submit a steward signature to ratify a pending constitutional amendment. */
    ratifyAmendment(proposalId: string, stewardId: string, signatureHex: string) {
        return this.post("/constitution/ratify", {
            proposal_id: proposalId,
            steward_id: stewardId,
            signature_hex: signatureHex,
        });
    }

    /** Reject a pending constitutional amendment. */
    rejectAmendment(proposalId: string, stewardId: string) {
        return this.post("/constitution/reject", {
            proposal_id: proposalId,
            steward_id: stewardId,
        });
    }

    /** List pending constitutional amendments awaiting ratification. */
    getPendingAmendments() {
        return this.get("/constitution/pending");
    }

    /** List constitutional stewards and ratification config. */
    getStewards() {
        return this.get("/constitution/stewards");
    }

    /** Add a new constitutional steward. */
    addSteward(id: string, publicKey: string) {
        return this.post("/constitution/stewards", { id, public_key: publicKey });
    }

    // ── MCP Tool Marketplace ─────────────────────────────────────────

    /** Publish a tool to the MCP marketplace. */
    mcpPublish(name: string, description: string, inputSchema: Record<string, unknown>, endpoint: string, transport: string = "http") {
        return this.post("/mcp/publish", { name, description, input_schema: inputSchema, endpoint, transport });
    }

    /** Search for tools in the MCP marketplace. */
    mcpSearch(query: string = "", capability: string = "") {
        return this.post("/mcp/search", { query, capability });
    }

    /** Install a tool from the MCP marketplace. */
    mcpInstall(toolId: string, agentId: string = "") {
        return this.post("/mcp/install", { tool_id: toolId, agent_id: agentId });
    }

    /** Uninstall a previously installed MCP tool. */
    mcpUninstall(toolId: string) {
        return this.post(`/mcp/uninstall/${toolId}`);
    }

    /** Invoke an installed MCP tool. */
    mcpInvoke(toolId: string, input: Record<string, unknown>) {
        return this.post("/mcp/invoke", { tool_id: toolId, input });
    }

    /** Get MCP marketplace statistics. */
    mcpStats() {
        return this.get("/mcp/stats");
    }
}
