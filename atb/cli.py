"""Small command-line entrypoint for the first benchmark release."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shlex
from typing import Any

from .adapters import CommandAgent
from .agents import FAULTS, ScriptedAgent
from .core import run
from .scenarios import all_scenarios, build_scenario


def _emit(data: dict[str, Any], output: str | None) -> None:
    rendered = json.dumps(data, ensure_ascii=False, indent=2)
    if output:
        destination = Path(output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(rendered + "\n", encoding="utf-8")
        print(f"wrote {destination}")
    else:
        print(rendered)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AgentTrustBench deterministic MVP")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="list the 36 synthetic scenarios")
    validate = sub.add_parser("validate", help="run reference and fault-injection agents")
    validate.add_argument("--json", dest="output")
    compare = sub.add_parser("compare", help="compare fault agents with and without ATB feedback")
    compare.add_argument("--json", dest="output")
    single = sub.add_parser("run", help="run one scenario")
    single.add_argument("template", help="01 to 12")
    single.add_argument("variant", type=int, choices=(1, 2, 3))
    single.add_argument("--fault", action="store_true")
    single.add_argument("--assisted", action="store_true")
    single.add_argument("--agent-command", help="command implementing the stdin/stdout JSON agent protocol")
    single.add_argument("--json", dest="output")
    args = parser.parse_args(argv)

    if args.command == "list":
        _emit({"scenarios": [{"id": s.id, "family": s.family, "title": s.title, "request": s.request} for s in all_scenarios()]}, None)
        return 0
    if args.command == "run":
        scenario = build_scenario(args.template, args.variant)
        if args.agent_command and args.fault:
            parser.error("--fault is only for the built-in scripted agent")
        agent = CommandAgent(shlex.split(args.agent_command)) if args.agent_command else ScriptedAgent(scenario, fault=args.fault)
        _emit(run(scenario, agent, assisted=args.assisted), args.output)
        return 0
    if args.command == "validate":
        references = [run(s, ScriptedAgent(s)) for s in all_scenarios()]
        assisted_references = [run(s, ScriptedAgent(s), assisted=True) for s in all_scenarios()]
        faults = [run(s, ScriptedAgent(s, fault=True)) for s in all_scenarios() if s.id[1:3] in FAULTS]
        data = {
            "reference": {"passed": sum(r["evaluation"]["passed"] for r in references), "total": len(references)},
            "assisted_reference": {
                "passed": sum(r["evaluation"]["passed"] for r in assisted_references),
                "total": len(assisted_references),
                "feedback_events": sum(r["feedback_count"] for r in assisted_references),
            },
            "fault_injection": {"detected": sum(not r["evaluation"]["passed"] for r in faults), "total": len(faults)},
            "reference_failures": [{"id": r["scenario_id"], "checks": r["evaluation"]["checks"]} for r in references if not r["evaluation"]["passed"]],
            "assisted_reference_failures": [{"id": r["scenario_id"], "checks": r["evaluation"]["checks"]} for r in assisted_references if not r["evaluation"]["passed"]],
            "undetected_faults": [{"id": r["scenario_id"], "fault": FAULTS[r["scenario_id"][1:3]]} for r in faults if r["evaluation"]["passed"]],
        }
        _emit(data, args.output)
        return 0 if (
            data["reference"]["passed"] == 36
            and data["assisted_reference"]["passed"] == 36
            and data["assisted_reference"]["feedback_events"] == 0
            and data["fault_injection"]["detected"] == len(faults)
        ) else 1
    scenarios = [s for s in all_scenarios() if s.id[1:3] in FAULTS]
    rows = []
    for scenario in scenarios:
        baseline = run(scenario, ScriptedAgent(scenario, fault=True), assisted=False)
        assisted = run(scenario, ScriptedAgent(scenario, fault=True), assisted=True)
        rows.append({
            "scenario_id": scenario.id, "fault": FAULTS[scenario.id[1:3]],
            "baseline_passed": baseline["evaluation"]["passed"],
            "assisted_passed": assisted["evaluation"]["passed"],
            "feedback": [event["feedback"] for event in assisted["trajectory"] if event["kind"] == "feedback"],
            "baseline_tool_calls": baseline["tool_calls"], "assisted_tool_calls": assisted["tool_calls"],
            "baseline_elapsed_ms": baseline["elapsed_ms"], "assisted_elapsed_ms": assisted["elapsed_ms"],
        })
    data = {
        "note": "Scripted fault agents demonstrate the protocol only; these are not measured model results.",
        "summary": {
            "scenarios": len(rows),
            "baseline_reliable_success": sum(row["baseline_passed"] for row in rows),
            "assisted_reliable_success": sum(row["assisted_passed"] for row in rows),
            "feedback_events": sum(len(row["feedback"]) for row in rows),
        },
        "rows": rows,
    }
    _emit(data, args.output)
    return 0
