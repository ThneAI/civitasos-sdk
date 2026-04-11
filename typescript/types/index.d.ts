/**
 * @civitasos/types — shared type definitions for CivitasOS SDKs and integrations.
 */

// ── Agent Card ───────────────────────────────────────────────────────

export interface AgentCard {
    id: string;
    name: string;
    description?: string;
    endpoint?: string;
    capabilities: Capability[];
    reputation?: ReputationScore;
    stake: number;
    status: AgentStatus;
    created_at?: number;
}

export type AgentStatus = "active" | "suspended" | "quarantined" | "offline";

export interface Capability {
    id: string;
    name: string;
    description?: string;
    input_schema?: Record<string, unknown>;
    output_schema?: Record<string, unknown>;
    price?: number;
    sla_ms?: number;
}

// ── Reputation ───────────────────────────────────────────────────────

export interface ReputationScore {
    composite: number;
    depth: number;
    accuracy: number;
    cooperation: number;
    responsiveness: number;
    trust: number;
    total_interactions: number;
}

// ── A2A Protocol ─────────────────────────────────────────────────────

export interface A2ATask {
    id: string;
    from_agent: string;
    to_agent: string;
    capability_id: string;
    input: Record<string, unknown>;
    output?: Record<string, unknown>;
    status: A2ATaskStatus;
    created_at: number;
    completed_at?: number;
    deadline_secs?: number;
    session_id?: string;
}

export type A2ATaskStatus =
    | "pending"
    | "claimed"
    | "running"
    | "completed"
    | "failed"
    | "cancelled"
    | "expired";

export interface A2ATaskResult {
    task_id: string;
    status: A2ATaskStatus;
    output?: Record<string, unknown>;
    error?: string;
}

export interface A2ADiscoveryRequest {
    capability_id?: string;
    min_reputation?: number;
}

// ── Governance ───────────────────────────────────────────────────────

export interface Proposal {
    id: string;
    title: string;
    description: string;
    proposal_type: ProposalType;
    creator: string;
    status: ProposalStatus;
    created_at: number;
    deadline: number;
    votes: Record<string, Vote>;
    total_voted_stake: number;
    threshold: number;
}

export type ProposalType =
    | "ParameterChange"
    | "ConstitutionalAmendment"
    | "ValidatorManagement"
    | "EmergencyAction";

export type ProposalStatus = "Active" | "Approved" | "Rejected" | "Expired";

export interface Vote {
    voter_id: string;
    vote_type: "Yes" | "No" | "Abstain";
    stake: number;
    delegated?: boolean;
}

// ── Economics ─────────────────────────────────────────────────────────

export interface GasMarket {
    base_price: number;
    current_price: number;
    utilization: number;
    epoch: number;
}

export interface Account {
    id: string;
    balance: number;
    staked: number;
    nonce: number;
}

// ── Settlement ───────────────────────────────────────────────────────

export interface SettlementLock {
    lock_id: string;
    from: string;
    to: string;
    amount: number;
    hash_lock: string;
    timeout_secs: number;
    status: "locked" | "released" | "refunded";
}

export interface SettlementProof {
    proof_id: string;
    lock_id: string;
    preimage: string;
    verifier: string;
    verified_at: number;
}

// ── MCP Tools ────────────────────────────────────────────────────────

export interface McpToolListing {
    id: string;
    name: string;
    description: string;
    input_schema: Record<string, unknown>;
    endpoint: string;
    transport: McpTransport;
    publisher: string;
    version?: string;
    installed_count?: number;
}

export type McpTransport = "http" | "stdio" | "ws";

export interface McpInvokeResult {
    tool_id: string;
    output: Record<string, unknown>;
    duration_ms: number;
}

// ── ZK Proofs ────────────────────────────────────────────────────────

export interface ZkProof {
    proof_type: "membership" | "range" | "computation";
    proof_bytes: string;
    public_inputs: number[];
    verified?: boolean;
}

export interface ZkStats {
    proofs_generated: number;
    proofs_verified: number;
    verification_failures: number;
}

// ── DAG Orchestration ────────────────────────────────────────────────

export interface DagTask {
    id: string;
    description?: string;
    steps: DagStep[];
    status: "pending" | "running" | "completed" | "failed";
    created_at: number;
}

export interface DagStep {
    id: string;
    name: string;
    dependencies: string[];
    agent_id?: string;
    capability_id?: string;
    input?: Record<string, unknown>;
    output?: Record<string, unknown>;
    status: "pending" | "running" | "completed" | "failed";
}

// ── R2R Relations ────────────────────────────────────────────────────

export interface Relation {
    from: string;
    to: string;
    relation_type: string;
    status: "proposed" | "active" | "terminated" | "cooling_down";
    created_at: number;
}

export interface Signal {
    from: string;
    to: string;
    intent: string;
    payload?: Record<string, unknown>;
    correlation_id?: string;
}

// ── System Status ────────────────────────────────────────────────────

export interface NodeStatus {
    node_id: string;
    version: string;
    uptime_secs: number;
    agents_count: number;
    connected_nodes: number;
    tps: number;
    p2p_enabled: boolean;
    tls_enabled: boolean;
}

// ── Marketplace ──────────────────────────────────────────────────────

export interface MarketListing {
    id: string;
    agent_id: string;
    capability: string;
    price: number;
    description?: string;
    min_reputation?: number;
}

// ── Webhook ──────────────────────────────────────────────────────────

export interface WebhookRegistration {
    id: string;
    url: string;
    events: string[];
    secret?: string;
    active: boolean;
}

// ── Multi-Tenant ─────────────────────────────────────────────────────

export interface Tenant {
    id: string;
    name: string;
    admin_id: string;
    status: "active" | "suspended";
    quotas: TenantQuotas;
    created_at: number;
}

export interface TenantQuotas {
    max_agents: number;
    max_proposals: number;
    max_stake: number;
}

// ── API Response Wrapper ─────────────────────────────────────────────

export interface ApiResponse<T = unknown> {
    status: "ok" | "error";
    data?: T;
    error?: string;
    timestamp?: number;
}
