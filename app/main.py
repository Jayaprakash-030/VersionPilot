from __future__ import annotations

import argparse
import json
from pathlib import Path

from .agent_orchestrator import AgentOrchestrator
from .pipeline import build_run_id, run_pipeline
from .risk_scoring import load_scoring_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Deterministic AI Health Inspector (Step 1 scaffold)")
    parser.add_argument("repo_url", help="GitHub repository URL")
    parser.add_argument(
        "--mode",
        choices=["basic", "agent"],
        default="basic",
        help="Execution mode: deterministic basic pipeline or agentic orchestrator",
    )
    parser.add_argument(
        "--config",
        default="config/scoring_v1.yaml",
        help="Path to scoring config file",
    )
    parser.add_argument(
        "--repo-path",
        default="",
        help="Local repository path for code-level scans in agent mode",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Output file path. Defaults to artifacts/<run_id>.json",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Recompute and overwrite output even if artifact already exists",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print report JSON to stdout",
    )
    return parser.parse_args()


def resolve_output_path(run_id: str, output_arg: str, mode: str = "basic") -> Path:
    if output_arg:
        output_path = Path(output_arg)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        return output_path

    artifacts_dir = Path("artifacts")
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    suffix = "-agent" if mode == "agent" else ""
    return artifacts_dir / f"{run_id}{suffix}.json"


def main() -> None:
    args = parse_args()
    config = load_scoring_config(args.config)
    run_id = build_run_id(repo_url=args.repo_url, config_version=config.version)
    output_path = resolve_output_path(run_id, args.output, mode=args.mode)

    if output_path.exists() and not args.force:
        existing = json.loads(output_path.read_text(encoding="utf-8"))
        if args.json:
            print(json.dumps(existing, indent=2))
        else:
            print(f"Health Score: {existing.get('health_score')}")
            print(f"Risk Level: {existing.get('risk_level')}")
            print(f"Using existing report: {output_path}")
        return

    if args.mode == "agent":
        orchestrator = AgentOrchestrator()
        payload = orchestrator.analyze_repository(
            repo_url=args.repo_url,
            config_path=args.config,
            repo_path=args.repo_path or None,
        )
        report_view = payload.get("report", {})
        health_score = report_view.get("health_score")
        risk_level = report_view.get("risk_level")
    else:
        report = run_pipeline(repo_url=args.repo_url, config_path=args.config)
        payload = report.to_dict()
        health_score = report.health_score
        risk_level = report.risk_level

    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"Health Score: {health_score}")
        print(f"Risk Level: {risk_level}")
        print(f"Saved report: {output_path}")


if __name__ == "__main__":
    main()
