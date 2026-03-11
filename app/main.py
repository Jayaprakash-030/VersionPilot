from __future__ import annotations

import argparse
import json
from pathlib import Path

from .pipeline import build_run_id, run_pipeline
from .risk_scoring import load_scoring_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Deterministic AI Health Inspector (Step 1 scaffold)")
    parser.add_argument("repo_url", help="GitHub repository URL")
    parser.add_argument(
        "--config",
        default="config/scoring_v1.yaml",
        help="Path to scoring config file",
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
    return parser.parse_args()


def resolve_output_path(run_id: str, output_arg: str) -> Path:
    if output_arg:
        output_path = Path(output_arg)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        return output_path

    artifacts_dir = Path("artifacts")
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    return artifacts_dir / f"{run_id}.json"


def main() -> None:
    args = parse_args()
    config = load_scoring_config(args.config)
    run_id = build_run_id(repo_url=args.repo_url, config_version=config.version)
    output_path = resolve_output_path(run_id, args.output)

    if output_path.exists() and not args.force:
        existing = json.loads(output_path.read_text(encoding="utf-8"))
        print(f"Health Score: {existing.get('health_score')}")
        print(f"Risk Level: {existing.get('risk_level')}")
        print(f"Using existing report: {output_path}")
        return

    report = run_pipeline(repo_url=args.repo_url, config_path=args.config)
    output_path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")

    print(f"Health Score: {report.health_score}")
    print(f"Risk Level: {report.risk_level}")
    print(f"Saved report: {output_path}")


if __name__ == "__main__":
    main()
