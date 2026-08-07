from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any
from unittest.mock import patch

from app.agents.report_node import report_node
from app.agents.state import create_initial_state


def _norm(text: str) -> str:
    """Normalize text for loose groundedness matching."""
    return re.sub(r"\s+", " ", str(text or "").casefold()).strip()


def build_grounding_index(state: dict[str, Any]) -> dict[str, Any]:
    """Collect provenance-backed signals that report claims may cite."""
    deprecated = state.get("deprecated_findings") or []
    migration_plan = state.get("migration_plan") or {}
    steps = migration_plan.get("steps") or []
    breaking = state.get("breaking_change_analysis") or {}
    breaking_findings = breaking.get("findings") or []

    symbols: set[str] = set()
    packages: set[str] = set()
    verified_actions: set[str] = set()
    hint_actions: set[str] = set()
    verified_packages: set[str] = set()
    hint_packages: set[str] = set()

    for finding in deprecated:
        symbol = str(finding.get("symbol") or "").strip()
        package = str(finding.get("package") or "").strip()
        if symbol:
            symbols.add(_norm(symbol))
        if package:
            packages.add(_norm(package))

    for step in steps:
        action = _norm(step.get("action") or "")
        package = _norm(step.get("package") or "")
        step_type = str(step.get("type") or "")
        confidence = str(step.get("confidence") or "")
        if step_type == "deprecated_api_replacement" or confidence == "ast_scan":
            if action:
                verified_actions.add(action)
            if package:
                verified_packages.add(package)
            symbol = _norm(step.get("symbol") or "")
            if symbol:
                symbols.add(symbol)
        else:
            if action:
                hint_actions.add(action)
            if package:
                hint_packages.add(package)

    for finding in breaking_findings:
        text = _norm(finding.get("text") or "")
        package = _norm(finding.get("package") or "")
        if text:
            hint_actions.add(text)
        if package:
            hint_packages.add(package)

    return {
        "symbols": symbols,
        "packages": packages,
        "verified_actions": verified_actions,
        "hint_actions": hint_actions,
        "verified_packages": verified_packages,
        "hint_packages": hint_packages,
        "health_score": state.get("health_score"),
        "risk_level": _norm(state.get("risk_level") or ""),
    }


def _action_matches(candidate: str, allowed: set[str]) -> bool:
    """Return True if candidate equals or is contained in an allowed grounded action."""
    cand = _norm(candidate)
    if not cand:
        return False
    if cand in allowed:
        return True
    for action in allowed:
        if cand in action or action in cand:
            return True
    return False


def _key_finding_grounded(item: dict[str, Any], index: dict[str, Any]) -> bool:
    """A key finding is grounded if it cites a known deprecated symbol/package."""
    finding = _norm(item.get("finding") or "")
    evidence = _norm(item.get("evidence") or "")
    blob = f"{finding} {evidence}"
    if not finding:
        return False
    for symbol in index["symbols"]:
        if symbol and symbol in blob:
            return True
    for package in index["packages"]:
        if package and f"package={package}" in evidence:
            return True
    return False


def _recommendation_grounded(item: dict[str, Any], index: dict[str, Any]) -> bool:
    """Verified recommendations must match AST-backed migration plan steps."""
    action = item.get("action") or ""
    reason = _norm(item.get("reason") or "")
    if not _action_matches(action, index["verified_actions"]):
        return False
    # Reason should admit verified confidence/type.
    if "ast_scan" in reason or "deprecated_api_replacement" in reason:
        return True
    # Allow package cite if action already matched a verified step.
    for package in index["verified_packages"]:
        if package and package in reason:
            return True
    return bool(index["verified_actions"])


def _hint_grounded(item: dict[str, Any], index: dict[str, Any]) -> bool:
    """Upstream hints must match release-note-derived breaking-change steps."""
    action = item.get("action") or ""
    reason = _norm(item.get("reason") or "")
    if not _action_matches(action, index["hint_actions"]):
        return False
    if "regex_heuristic" in reason or "breaking_change_review" in reason:
        return True
    for package in index["hint_packages"]:
        if package and package in reason:
            return True
    return bool(index["hint_actions"])


def evaluate_report(
    report: dict[str, Any],
    state: dict[str, Any],
) -> dict[str, Any]:
    """Score groundedness of report claims against state signals."""
    index = build_grounding_index(state)
    details: list[dict[str, Any]] = []

    key_findings = report.get("key_findings") or []
    recommendations = report.get("migration_recommendations") or []
    hints = report.get("upstream_breaking_change_hints") or []

    grounded_findings = 0
    for item in key_findings:
        ok = _key_finding_grounded(item, index)
        grounded_findings += int(ok)
        details.append(
            {
                "kind": "key_finding",
                "grounded": ok,
                "text": item.get("finding", ""),
            }
        )

    grounded_recs = 0
    for item in recommendations:
        ok = _recommendation_grounded(item, index)
        grounded_recs += int(ok)
        details.append(
            {
                "kind": "migration_recommendation",
                "grounded": ok,
                "text": item.get("action", ""),
            }
        )

    grounded_hints = 0
    for item in hints:
        ok = _hint_grounded(item, index)
        grounded_hints += int(ok)
        details.append(
            {
                "kind": "upstream_breaking_change_hint",
                "grounded": ok,
                "text": item.get("action", ""),
            }
        )

    total_claims = len(key_findings) + len(recommendations) + len(hints)
    grounded_claims = grounded_findings + grounded_recs + grounded_hints
    ungrounded = total_claims - grounded_claims
    score = 1.0 if total_claims == 0 else grounded_claims / total_claims

    # Health score / risk must match state (factual pass-through).
    score_ok = report.get("health_score") == state.get("health_score")
    expected_risk = state.get("risk_level")
    if not state.get("critic_passed", True):
        expected_risk = "Unverified"
    risk_ok = _norm(report.get("risk_level") or "") == _norm(expected_risk or "")

    passed = ungrounded == 0 and score_ok and risk_ok
    return {
        "passed": passed,
        "groundedness_score": round(score, 4),
        "total_claims": total_claims,
        "grounded_claims": grounded_claims,
        "ungrounded_claims": ungrounded,
        "key_findings_total": len(key_findings),
        "key_findings_grounded": grounded_findings,
        "migration_recommendations_total": len(recommendations),
        "migration_recommendations_grounded": grounded_recs,
        "upstream_hints_total": len(hints),
        "upstream_hints_grounded": grounded_hints,
        "health_score_matches": score_ok,
        "risk_level_matches": risk_ok,
        "details": details,
    }


def evaluate_report_node(state: dict[str, Any]) -> dict[str, Any]:
    """Run report_node (deterministic path) and evaluate groundedness."""
    with patch("app.agents.report_node.LLMClient.is_available", return_value=False):
        result = report_node(state)
    report = result["final_report"]
    evaluation = evaluate_report(report, state)
    evaluation["report"] = {
        "key_findings": report.get("key_findings") or [],
        "migration_recommendations": report.get("migration_recommendations") or [],
        "upstream_breaking_change_hints": report.get("upstream_breaking_change_hints")
        or [],
        "health_score": report.get("health_score"),
        "risk_level": report.get("risk_level"),
    }
    return evaluation


def _load_state_fixture(fixture: Path) -> dict[str, Any]:
    """Load a groundedness fixture state and merge onto a blank agent state."""
    payload = json.loads((fixture / "state.json").read_text(encoding="utf-8"))
    state = create_initial_state(payload.get("repo_url", "https://github.com/example/repo"))
    state.update(payload)
    return state


def evaluate_fixture(fixture_path: str | Path) -> dict[str, Any]:
    """Evaluate one groundedness fixture directory."""
    fixture = Path(fixture_path)
    state = _load_state_fixture(fixture)
    report_path = fixture / "report.json"
    if report_path.exists():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        evaluation = evaluate_report(report, state)
        evaluation["mode"] = "static_report"
    else:
        evaluation = evaluate_report_node(state)
        evaluation["mode"] = "report_node"
    evaluation["fixture"] = fixture.name

    metadata_path = fixture / "metadata.json"
    expect_passed = True
    if metadata_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        expect_passed = bool(metadata.get("expect_passed", True))
    evaluation["expect_passed"] = expect_passed
    evaluation["fixture_check_passed"] = bool(evaluation["passed"]) == expect_passed
    return evaluation


def evaluate_suite(fixtures_path: str | Path) -> dict[str, Any]:
    """Evaluate every groundedness fixture under a directory."""
    root = Path(fixtures_path)
    results = [
        evaluate_fixture(path)
        for path in sorted(root.iterdir())
        if path.is_dir() and (path / "state.json").exists()
    ]
    passed = sum(1 for result in results if result.get("fixture_check_passed"))
    return {
        "fixture_count": len(results),
        "passed_fixture_count": passed,
        "failed_fixtures": [
            result["fixture"]
            for result in results
            if not result.get("fixture_check_passed")
        ],
        "mean_groundedness_score": round(
            (
                sum(float(result.get("groundedness_score", 0.0)) for result in results)
                / len(results)
            )
            if results
            else 1.0,
            4,
        ),
        "results": results,
    }


def main() -> None:
    """CLI entrypoint for groundedness evaluation."""
    parser = argparse.ArgumentParser(
        description="Evaluate report groundedness against provenance-tracked state"
    )
    parser.add_argument(
        "fixtures",
        nargs="?",
        default="eval/fixtures/groundedness",
        help="Fixture directory or suite root",
    )
    parser.add_argument("--output", default="", help="Optional JSON output path")
    args = parser.parse_args()

    target = Path(args.fixtures)
    if (target / "state.json").exists():
        result: dict[str, Any] = evaluate_fixture(target)
    else:
        result = evaluate_suite(target)

    text = json.dumps(result, indent=2)
    print(text)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
