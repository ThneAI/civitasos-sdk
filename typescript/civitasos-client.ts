/**
 * CivitasOS TypeScript SDK — auto-generated client library.
 *
 * @example
 * ```ts
 * import { CivitasOS } from "./civitasos-client";
 * const client = new CivitasOS("http://127.0.0.1:8099");
 * const status = await client.status();
 * ```
 */

export interface CivitasOSConfig {
    baseUrl: string;
    apiKey?: string;
    /** JWT bearer token for authenticated requests. */
    token?: string;
    timeout?: number;
}

export class CivitasOS {
    private baseUrl: string;
    private apiKey?: string;
    private token?: string;
    private timeout: number;

    constructor(baseUrlOrConfig: string | CivitasOSConfig) {
        if (typeof baseUrlOrConfig === "string") {
            this.baseUrl = baseUrlOrConfig.replace(/\/+$/, "");
            this.timeout = 30_000;
        } else {
            this.baseUrl = baseUrlOrConfig.baseUrl.replace(/\/+$/, "");
            this.apiKey = baseUrlOrConfig.apiKey;
            this.token = baseUrlOrConfig.token;
            this.timeout = baseUrlOrConfig.timeout ?? 30_000;
        }
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
        } finally {
            clearTimeout(timer);
        }
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
}
