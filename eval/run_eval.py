from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from app.pipeline import run_pipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run benchmark evaluation across repository URLs")
    parser.add_argument(
        "--repos-file",
        default="data/benchmark_repos.txt",
        help="Path to text file containing one repo URL per line",
    )
    parser.add_argument(
        "--config",
        default="config/scoring_v1.yaml",
        help="Path to scoring config file",
    )
    parser.add_argument(
        "--output",
        default="eval/eval_report.json",
        help="Path to output evaluation report JSON",
    )
    return parser.parse_args()


def load_repo_urls(path: str) -> list[str]:
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    repos: list[str] = []
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        repos.append(line)
    return repos


def summarize(results: list[dict]) -> dict:
    if not results:
        return {
            "total_repos": 0,
            "avg_health_score": 0.0,
            "avg_data_completeness": 0.0,
            "avg_confidence_score": 0.0,
            "risk_distribution": {"Low": 0, "Medium": 0, "High": 0},
            "runs_with_failures": 0,
            "failed_step_distribution": {},
        }

    total = len(results)
    avg_score = round(sum(float(r["health_score"]) for r in results) / total, 2)
    avg_data_completeness = round(
        sum(float(r.get("data_completeness", 0.0)) for r in results) / total,
        2,
    )
    avg_confidence_score = round(
        sum(float(r.get("confidence_score", 0.0)) for r in results) / total,
        2,
    )

    risk_distribution = {"Low": 0, "Medium": 0, "High": 0}
    runs_with_failures = 0
    failed_step_distribution: dict[str, int] = {}

    for r in results:
        risk = r.get("risk_level", "Medium")
        if risk not in risk_distribution:
            risk = "Medium"
        risk_distribution[risk] += 1

        failed_steps = r.get("failed_steps", [])
        if failed_steps:
            runs_with_failures += 1
            for step in failed_steps:
                failed_step_distribution[step] = failed_step_distribution.get(step, 0) + 1

    return {
        "total_repos": total,
        "avg_health_score": avg_score,
        "avg_data_completeness": avg_data_completeness,
        "avg_confidence_score": avg_confidence_score,
        "risk_distribution": risk_distribution,
        "runs_with_failures": runs_with_failures,
        "failed_step_distribution": failed_step_distribution,
    }


def main() -> None:
    args = parse_args()
    repo_urls = load_repo_urls(args.repos_file)

    results: list[dict] = []
    for repo_url in repo_urls:
        try:
            report = run_pipeline(repo_url=repo_url, config_path=args.config)
            payload = report.to_dict()
            payload["run_status"] = "ok"
        except Exception as exc:  # noqa: BLE001
            payload = {
                "repo_url": repo_url,
                "run_status": "error",
                "error": str(exc),
                "health_score": 0.0,
                "risk_level": "High",
                "failed_steps": ["pipeline"],
            }
        results.append(payload)

    report_data = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "config_path": args.config,
        "repos_file": args.repos_file,
        "summary": summarize(results),
        "results": results,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report_data, indent=2), encoding="utf-8")

    print(f"Evaluated repos: {len(results)}")
    print(f"Saved evaluation report: {output_path}")


if __name__ == "__main__":
    main()
