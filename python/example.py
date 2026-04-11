"""CivitasOS Python Agent SDK — Example Usage

Demonstrates: keys, register, authenticate, governance,
              A2A quickstart, pool worker, R2R, cluster monitoring.

Start the backend first:
    cd civitasos-backend && cargo run
"""

from civitasos import CivitasAgent, CivitasError


def main():
    # ── Connect (multi-node with automatic failover) ─────────────
    agent = CivitasAgent([
        "http://localhost:8099",
        "http://localhost:8100",
        "http://localhost:8101",
    ])

    if not agent.wait_ready(timeout=10):
        print("❌ Backend not reachable")
        return

    print(f"✓ Connected to CivitasOS ({len(agent.nodes)} nodes)")

    # ── 1. Generate keys & register ──────────────────────────────
    agent.generate_keys()
    try:
        info = agent.register(
            agent_id="sdk-demo-1",
            name="SDK Demo Agent",
            capabilities=["compute", "inference"],
            stake=500,
        )
        print(f"✓ Registered: {info.id} (stake={info.stake})")
    except CivitasError as e:
        print(f"  Registration note: {e}")

    # ── 2. Authenticate (JWT) ────────────────────────────────────
    try:
        agent.authenticate()
        print(f"✓ Authenticated (key={agent.public_key_hex[:16]}…)")
    except CivitasError as e:
        print(f"  Auth note: {e}")

    # ── 3. List agents ───────────────────────────────────────────
    agents = agent.get_agents()
    print(f"✓ Active agents: {len(agents)}")
    for a in agents[:5]:
        print(f"  - {a.id}: {a.capabilities} (stake={a.stake})")

    # ── 4. Governance — propose & vote ───────────────────────────
    proposal_id = agent.create_proposal(
        title="SDK Test Proposal",
        description="Testing governance from Python SDK",
        proposal_type="ParameterChange",
    )
    print(f"✓ Proposal created: {proposal_id}")

    result = agent.vote(proposal_id, "approve", stake=200)
    print(f"✓ Vote cast: {result}")

    # ── 5. A2A quick-start ───────────────────────────────────────
    try:
        agent.a2a_quickstart(
            agent_id="sdk-demo-1",
            name="SDK Demo Agent",
            capabilities=["compute", "inference"],
        )
        print("✓ A2A card bootstrapped")
    except CivitasError as e:
        print(f"  A2A note: {e}")

    # ── 6. Pool — post a task ────────────────────────────────────
    try:
        task = agent.pool_post(
            capability_id="compute",
            input_data={"expr": "2+2"},
            reward=10.0,
        )
        print(f"✓ Pool task posted: {task.get('task_id', 'N/A')}")
    except CivitasError as e:
        print(f"  Pool note: {e}")

    # ── 7. R2R — propose relation & rate ─────────────────────────
    try:
        agent.r2r_propose_relation(to_agent="sdk-demo-1", relation_type="self-test")
        agent.r2r_rate_peer(to_agent="sdk-demo-1", aspect="quality", score=0.95)
        print("✓ R2R relation proposed & peer rated")
    except CivitasError as e:
        print(f"  R2R note: {e}")

    # ── 8. Evolve ────────────────────────────────────────────────
    try:
        evolve_result = agent.evolve(
            capabilities=["compute", "inference", "storage"], stake=800,
        )
        print(f"✓ Evolved: {evolve_result}")
    except CivitasError as e:
        print(f"  Evolution note: {e}")

    # ── 9. Cluster health ────────────────────────────────────────
    state = agent.get_state_hash()
    print(f"✓ State hash: {state.get('hash', '')[:16]}...")

    peers = agent.get_peers()
    print(f"✓ Cluster peers: {len(peers)}")

    slo = agent.get_slo_dashboard()
    print(f"✓ SLO: all_pass={slo.all_slo_pass}, p99={slo.p99_ms}ms, agents={slo.agents_count}")

    events = agent.get_audit_events()
    print(f"✓ Audit events: {len(events)}")

    print("\n🎯 SDK Demo Complete")


if __name__ == "__main__":
    main()
