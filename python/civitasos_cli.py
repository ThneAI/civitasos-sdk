#!/usr/bin/env python3
"""CivitasOS CLI — Agent-first operations from the terminal.

Usage:
    civitasos status
    civitasos agent list
    civitasos agent register <id> <name> <capabilities> [--stake=100]
    civitasos agent info <id>
    civitasos agent capabilities <id> <caps_json>
    civitasos task submit <agent_id> <capability> [--input='{}']
    civitasos pool post <capability> [--reward=100] [--min-rep=0.0]
    civitasos pool list
    civitasos pool discover <capability> [--min-rep=0.0]
    civitasos pool claim <task_id> <agent_id>
    civitasos pool complete <task_id>
    civitasos pool fail <task_id>
    civitasos govern propose <title> <description> <type> <proposer>
    civitasos govern list
    civitasos govern vote <proposal_id> <approve|reject> [--stake=100]
    civitasos reputation <agent_id>
    civitasos scheduler policy
    civitasos scheduler can-accept <agent_id> <reputation>
    civitasos economics metrics
    civitasos economics parameters
    civitasos economics adapt
    civitasos directory list
    civitasos directory discover <capability>
    civitasos directory publish <agent_id> <name> <endpoint> <capabilities>
    civitasos mesh list
    civitasos health
    civitasos audit

Environment:
    CIVITASOS_URL  Base URL (default: http://localhost:8099)
"""

from __future__ import annotations

import json
import os
import sys

from civitasos_sdk import CivitasAgent, CivitasError


def _sdk() -> CivitasAgent:
    url = os.environ.get("CIVITASOS_URL", "http://localhost:8099")
    return CivitasAgent(url)


def _print_json(data):
    print(json.dumps(data, indent=2, default=str))


def cmd_status():
    _print_json(_sdk().get_status())


def cmd_agent_list():
    agents = _sdk().get_agents()
    _print_json([{"id": a.id, "name": a.name, "capabilities": a.capabilities, "stake": a.stake} for a in agents])


def cmd_agent_register(args):
    agent_id = args[0]
    name = args[1]
    capabilities = args[2].split(",")
    stake = int(_flag(args, "--stake", "100"))
    sdk = _sdk()
    agent = sdk.register(agent_id, name, capabilities, stake)
    _print_json({"registered": agent.id, "name": agent.name})


def cmd_agent_info(args):
    _print_json(_sdk().get_agent(args[0]))


def cmd_agent_capabilities(args):
    agent_id = args[0]
    caps = json.loads(args[1])
    _print_json(_sdk().update_capabilities(caps, agent_id))


def cmd_task_submit(args):
    agent_id = args[0]
    capability = args[1]
    input_data = json.loads(_flag(args, "--input", "{}"))
    sdk = _sdk()
    sdk._agent_id = agent_id
    result = sdk.a2a_submit_task(agent_id, capability, input_data)
    _print_json(result)


def cmd_pool_post(args):
    capability = args[0]
    reward = int(_flag(args, "--reward", "100"))
    min_rep = float(_flag(args, "--min-rep", "0.0"))
    _print_json(_sdk().pool_post(capability, reward=reward, min_reputation=min_rep))


def cmd_pool_list():
    _print_json(_sdk().pool_list())


def cmd_pool_discover(args):
    capability = args[0]
    min_rep = float(_flag(args, "--min-rep", "0.0"))
    _print_json(_sdk().pool_discover(capability, min_rep))


def cmd_pool_claim(args):
    _print_json(_sdk().pool_claim(args[0], args[1]))


def cmd_pool_complete(args):
    _print_json(_sdk().pool_complete(args[0]))


def cmd_pool_fail(args):
    _print_json(_sdk().pool_fail(args[0]))


def cmd_govern_propose(args):
    title, desc, ptype, proposer = args[0], args[1], args[2], args[3]
    sdk = _sdk()
    sdk._agent_id = proposer
    pid = sdk.create_proposal(title, desc, ptype)
    _print_json({"proposal_id": pid})


def cmd_govern_list():
    proposals = _sdk().get_proposals()
    _print_json([{"id": p.id, "title": p.title, "status": p.status} for p in proposals])


def cmd_govern_vote(args):
    proposal_id = args[0]
    decision = args[1]
    stake = int(_flag(args, "--stake", "100"))
    sdk = _sdk()
    sdk.vote(proposal_id, decision, stake)
    _print_json({"voted": decision, "proposal": proposal_id})


def cmd_reputation(args):
    _print_json(_sdk().a2a_get_reputation(args[0]))


def cmd_scheduler_policy():
    _print_json(_sdk().scheduler_policy())


def cmd_scheduler_can_accept(args):
    _print_json(_sdk().scheduler_can_accept(args[0], float(args[1])))


def cmd_economics_metrics():
    _print_json(_sdk().economics_metrics())


def cmd_economics_parameters():
    _print_json(_sdk().economics_parameters())


def cmd_economics_adapt():
    _print_json(_sdk().economics_adapt())


def cmd_directory_list():
    _print_json(_sdk().directory_list())


def cmd_directory_discover(args):
    _print_json(_sdk().directory_discover(args[0]))


def cmd_directory_publish(args):
    agent_id, name, endpoint = args[0], args[1], args[2]
    capabilities = args[3].split(",")
    _print_json(_sdk().directory_publish(agent_id, name, endpoint, capabilities))


def cmd_mesh_list():
    _print_json(_sdk().reputation_mesh_list())


def cmd_health():
    _print_json(_sdk().a2a_health())


def cmd_audit():
    _print_json(_sdk().a2a_audit_log())


def _flag(args, flag, default):
    """Extract --flag=value from args list."""
    for a in args:
        if a.startswith(flag + "="):
            return a.split("=", 1)[1]
    return default


def _usage():
    print(__doc__)
    sys.exit(1)


def main():
    args = sys.argv[1:]
    if len(args) < 1:
        _usage()

    cmd = args[0]

    try:
        if cmd == "status":
            cmd_status()
        elif cmd == "agent":
            if len(args) < 2:
                _usage()
            sub = args[1]
            if sub == "list":
                cmd_agent_list()
            elif sub == "register":
                cmd_agent_register(args[2:])
            elif sub == "info":
                cmd_agent_info(args[2:])
            elif sub == "capabilities":
                cmd_agent_capabilities(args[2:])
            else:
                _usage()
        elif cmd == "task":
            if len(args) < 2 or args[1] != "submit":
                _usage()
            cmd_task_submit(args[2:])
        elif cmd == "pool":
            if len(args) < 2:
                _usage()
            sub = args[1]
            if sub == "list":
                cmd_pool_list()
            elif sub == "post":
                cmd_pool_post(args[2:])
            elif sub == "discover":
                cmd_pool_discover(args[2:])
            elif sub == "claim":
                cmd_pool_claim(args[2:])
            elif sub == "complete":
                cmd_pool_complete(args[2:])
            elif sub == "fail":
                cmd_pool_fail(args[2:])
            else:
                _usage()
        elif cmd == "govern":
            if len(args) < 2:
                _usage()
            sub = args[1]
            if sub == "propose":
                cmd_govern_propose(args[2:])
            elif sub == "list":
                cmd_govern_list()
            elif sub == "vote":
                cmd_govern_vote(args[2:])
            else:
                _usage()
        elif cmd == "reputation":
            cmd_reputation(args[1:])
        elif cmd == "scheduler":
            if len(args) < 2:
                _usage()
            sub = args[1]
            if sub == "policy":
                cmd_scheduler_policy()
            elif sub == "can-accept":
                cmd_scheduler_can_accept(args[2:])
            else:
                _usage()
        elif cmd == "economics":
            if len(args) < 2:
                _usage()
            sub = args[1]
            if sub == "metrics":
                cmd_economics_metrics()
            elif sub == "parameters":
                cmd_economics_parameters()
            elif sub == "adapt":
                cmd_economics_adapt()
            else:
                _usage()
        elif cmd == "directory":
            if len(args) < 2:
                _usage()
            sub = args[1]
            if sub == "list":
                cmd_directory_list()
            elif sub == "discover":
                cmd_directory_discover(args[2:])
            elif sub == "publish":
                cmd_directory_publish(args[2:])
            else:
                _usage()
        elif cmd == "mesh":
            if len(args) < 2 or args[1] != "list":
                _usage()
            cmd_mesh_list()
        elif cmd == "health":
            cmd_health()
        elif cmd == "audit":
            cmd_audit()
        elif cmd in ("--help", "-h", "help"):
            _usage()
        else:
            print(f"Unknown command: {cmd}")
            _usage()
    except CivitasError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except (IndexError, KeyError):
        print("Missing required arguments.", file=sys.stderr)
        _usage()


if __name__ == "__main__":
    main()
