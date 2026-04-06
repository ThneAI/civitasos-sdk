"""CivitasOS Python Agent SDK — Example Usage

Demonstrates: register, propose, vote, evolve, monitor.
Start the backend first:
    cd civitasos-backend && cargo run
"""

from civitasos_sdk import CivitasAgent, CivitasError


def main():
    # Connect to local node
    agent = CivitasAgent("http://localhost:8099")

    # Wait for backend to be ready
    if not agent.wait_ready(timeout=10):
        print("❌ Backend not reachable")
        return

    print("✓ Connected to CivitasOS")

    # ── 1. Register ──────────────────────────────────────────────────
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

    # ── 2. List agents ───────────────────────────────────────────────
    agents = agent.get_agents()
    print(f"✓ Active agents: {len(agents)}")
    for a in agents[:5]:
        print(f"  - {a.id}: {a.capabilities} (stake={a.stake})")

    # ── 3. Create proposal ───────────────────────────────────────────
    proposal_id = agent.create_proposal(
        title="SDK Test Proposal",
        description="Testing governance from Python SDK",
        proposal_type="ParameterChange",
    )
    print(f"✓ Proposal created: {proposal_id}")

    # ── 4. Vote ──────────────────────────────────────────────────────
    result = agent.vote(proposal_id, "approve", stake=200)
    print(f"✓ Vote cast: {result}")

    # ── 5. Evolve ────────────────────────────────────────────────────
    try:
        evolve_result = agent.evolve(capabilities=["compute", "inference", "storage"], stake=800)
        print(f"✓ Evolved: {evolve_result}")
    except CivitasError as e:
        print(f"  Evolution note: {e}")

    # ── 6. Reputation ────────────────────────────────────────────────
    try:
        rep = agent.get_reputation()
        print(f"✓ Reputation: composite={rep.get('composite', 'N/A')}")
    except CivitasError as e:
        print(f"  Reputation note: {e}")

    # ── 7. Cluster state ─────────────────────────────────────────────
    state = agent.get_state_hash()
    print(f"✓ State hash: {state.get('hash', '')[:16]}...")

    peers = agent.get_peers()
    print(f"✓ Cluster peers: {len(peers)}")

    suspects = agent.get_byzantine_suspects()
    print(f"✓ Byzantine suspects: {len(suspects)}")

    # ── 8. SLO Dashboard ─────────────────────────────────────────────
    slo = agent.get_slo_dashboard()
    print(f"✓ SLO: all_pass={slo.all_slo_pass}, p99={slo.p99_ms}ms, agents={slo.agents_count}")

    # ── 9. Audit ─────────────────────────────────────────────────────
    events = agent.get_audit_events()
    print(f"✓ Audit events: {len(events)}")

    print("\n🎯 SDK Demo Complete")


if __name__ == "__main__":
    main()
