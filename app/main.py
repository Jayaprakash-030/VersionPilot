from __future__ import annotations

import argparse
import json
from pathlib import Path

from .pipeline import run_pipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Deterministic AI Health Inspector (Step 1 scaffold)")
    parser.add_argument("repo_url", help="GitHub repository URL")
    parser.add_argument(
        "--config",
        default="config/scoring_v1.yaml",
        help="Path to scoring config file",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    # breakpoint()  # Debugging breakpoint; remove or comment out in production
    report = run_pipeline(repo_url=args.repo_url, config_path=args.config)

    artifacts_dir = Path("artifacts")
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    output_path = artifacts_dir / f"{report.run_id}.json"
    output_path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")

    print(f"Health Score: {report.health_score}")
    print(f"Risk Level: {report.risk_level}")
    print(f"Saved report: {output_path}")


if __name__ == "__main__":
    main()
