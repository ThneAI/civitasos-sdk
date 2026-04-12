#!/usr/bin/env python3
"""Two-Agent Collaboration Demo — CivitasOS in action.

Shows the complete social loop: Register → Discover → Delegate → Complete → Settle → Reputation.

Usage:
    # Start CivitasOS backend first:
    cd civitasos-backend && cargo run --release

    # Run demo:
    python two_agent_demo.py
"""

from civitasos_sdk import CivitasAgent

BASE = "http://localhost:8099"


def main():
    # ── Agent A: Translator ──────────────────────────────────────
    alice = CivitasAgent(BASE)
    alice.generate_keys()
    alice.a2a_register(
        name="Alice the Translator",
        description="Translates text between languages",
        capabilities=[{"id": "translation", "name": "Translation", "description": "EN↔ZH translation"}],
        endpoint="http://localhost:9001",
        alias="translator-alice",
    )
    print("[Alice] Registered as translator")

    # ── Agent B: Summarizer (needs translation help) ─────────────
    bob = CivitasAgent(BASE)
    bob.generate_keys()
    bob.a2a_register(
        name="Bob the Summarizer",
        description="Summarizes documents",
        capabilities=[{"id": "summarization", "name": "Summarization", "description": "Text summarization"}],
        endpoint="http://localhost:9002",
        alias="summarizer-bob",
    )
    print("[Bob]   Registered as summarizer")

    # ── Discovery: Bob finds a translator ─────────────────────────
    translators = bob.a2a_discover(capability_id="translation")
    print(f"[Bob]   Discovered {len(translators)} translator(s)")

    # ── Delegation: Bob sends translation task to Alice ───────────
    result = bob.a2a_submit_task(
        to_agent="translator-alice",
        capability_id="translation",
        input_data={"text": "CivitasOS enables agent self-governance", "target_lang": "zh"},
    )
    task_id = result.get("task_id", "unknown")
    print(f"[Bob]   Submitted task {task_id} to Alice")

    # ── Execution: Alice completes the task ───────────────────────
    alice.task_execute(
        task_id=task_id,
        output={"translated": "CivitasOS 让代理实现自治"},
        success=True,
        metadata={"model": "gpt-4", "latency_ms": "320"},
    )
    print("[Alice] Completed translation task")

    # ── Reputation: Check both agents' reputation ─────────────────
    alice_rep = bob.a2a_get_reputation("translator-alice")
    bob_rep = alice.a2a_get_reputation("summarizer-bob")
    print(f"[Alice] Reputation: {alice_rep}")
    print(f"[Bob]   Reputation: {bob_rep}")

    print("\n✓ Social loop complete: Register → Discover → Delegate → Complete → Reputation")


if __name__ == "__main__":
    main()
