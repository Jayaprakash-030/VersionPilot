from __future__ import annotations

import json

from app.agents.state import VersionPilotState
from app.agents.llm_client import LLMClient, merge_llm_usage

_SYSTEM_PROMPT = """\
You are a dependency health report writer. Generate a structured report based ONLY on
the evidence provided. Never invent findings. Every recommendation must reference a
specific signal from the data.

Return JSON only — no explanation.

Output format:
{
  "summary": "2-3 sentence overall assessment",
  "health_score": <number from state>,
  "risk_level": "<string from state>",
  "key_findings": [
    {"finding": "...", "evidence": "...", "severity": "high|medium|low"}
  ],
  "migration_recommendations": [
    {"action": "...", "priority": "high|medium|low", "reason": "..."}
  ],
  "upstream_breaking_change_hints": [
    {"action": "...", "priority": "high|medium|low", "reason": "..."}
  ],
  "data_quality": {
    "completeness": <float>,
    "confidence": <float>,
    "failed_steps": [...],
    "migration_analysis_completeness": <float>,
    "migration_analysis_failed_steps": [...]
  }
}

Rules:
- key_findings must cite specific values from the data (scores, counts, package names).
- migration_recommendations must include only verified, code-grounded migration steps.
- upstream_breaking_change_hints may include unverified release-note-derived review items.
- If there are no findings, key_findings must be [].
- If there are no migration steps, migration_recommendations must be [].
- If there are no unverified release-note hints, upstream_breaking_change_hints must be [].
- health_score and risk_level must be passed through exactly as given.
"""


def _deprecated_api_rules_source(state: VersionPilotState) -> str:
    """Return the provenance rules_source used for the deprecated API scan."""
    for entry in reversed(state.get("provenance") or []):
        if entry.get("source") == "deprecated_api_scan":
            return entry.get("rules_source", "unknown")
    return "unknown"


def _rules_source_notice(state: VersionPilotState) -> str:
    """Optional notice when no dynamic deprecation rules were extracted."""
    if _deprecated_api_rules_source(state) != "no_rules_extracted":
        return ""
    return (
        " No deprecated-API rules were extracted from release notes;"
        " deprecated API scan found nothing from dynamic analysis."
    )


def _deduped_key_findings(deprecated_findings: list[dict]) -> list[dict]:
    """Collapse repeated AST hits into one finding per package/symbol."""
    groups: dict[tuple[str, str], dict] = {}
    order: list[tuple[str, str]] = []
    for finding in deprecated_findings:
        package = str(finding.get("package") or "unknown")
        symbol = str(finding.get("symbol") or "unknown")
        key = (package, symbol)
        file_path = finding.get("file_path", "unknown")
        line = finding.get("line", "?")
        if key not in groups:
            groups[key] = {
                "package": package,
                "symbol": symbol,
                "severity": finding.get("severity", "medium"),
                "count": 0,
                "sample": f"{file_path}:{line}",
            }
            order.append(key)
        groups[key]["count"] += 1

    findings: list[dict] = []
    for key in order:
        group = groups[key]
        count = group["count"]
        if count == 1:
            finding_text = (
                f"Deprecated API usage: {group['symbol']} at {group['sample']}"
            )
        else:
            finding_text = (
                f"Deprecated API usage: {group['symbol']} "
                f"({count} occurrences; e.g. {group['sample']})"
            )
        findings.append(
            {
                "finding": finding_text,
                "evidence": f"package={group['package']}, occurrences={count}",
                "severity": group["severity"],
            }
        )
    return findings


def _split_migration_outputs(steps: list[dict]) -> tuple[list[dict], list[dict]]:
    """Map migration-plan steps into verified recommendations vs upstream hints."""
    migration_recommendations: list[dict] = []
    upstream_breaking_change_hints: list[dict] = []
    for step in steps:
        package = step.get("package", "unknown")
        confidence = step.get("confidence", "unknown")
        version_span = step.get("version_span")
        reason = (
            f"type={step.get('type', 'unknown')}, package={package}, "
            f"confidence={confidence}"
        )
        if version_span:
            reason = f"{reason}, span={version_span}"
        occurrence_count = step.get("occurrence_count")
        if isinstance(occurrence_count, int) and occurrence_count > 1:
            reason = f"{reason}, occurrences={occurrence_count}"
        item = {
            "action": step.get("action", "Review migration step"),
            "priority": "high" if step.get("severity") == "high" else "medium",
            "reason": reason,
        }
        if step.get("type") == "deprecated_api_replacement" or confidence == "ast_scan":
            migration_recommendations.append(item)
        else:
            upstream_breaking_change_hints.append(item)
    return migration_recommendations, upstream_breaking_change_hints


def _template_report(state: VersionPilotState, effective_risk: str | None = None) -> dict:
    """Template-based fallback when LLM is unavailable."""
    published_risk = effective_risk or state.get("risk_level", "unknown")
    migration_plan = state.get("migration_plan") or {}
    steps = migration_plan.get("steps", [])
    deprecated_findings = state.get("deprecated_findings") or []
    failed_steps = state.get("failed_steps") or []

    key_findings = _deduped_key_findings(deprecated_findings)
    migration_recommendations, upstream_breaking_change_hints = _split_migration_outputs(
        steps
    )

    return {
        "summary": (
            f"Health score: {state.get('health_score', 0.0):.1f} ({published_risk} risk). "
            f"{len(deprecated_findings)} deprecated API finding(s), "
            f"{len(migration_recommendations)} verified migration recommendation(s), "
            f"{len(upstream_breaking_change_hints)} upstream review hint(s). "
            f"Data completeness: {state.get('data_completeness', 0.0):.0%}."
            f"{_rules_source_notice(state)}"
        ),
        "health_score": state.get("health_score", 0.0),
        "risk_level": published_risk,
        "key_findings": key_findings,
        "migration_recommendations": migration_recommendations,
        "upstream_breaking_change_hints": upstream_breaking_change_hints,
        "data_quality": {
            "completeness": state.get("data_completeness", 0.0),
            "confidence": state.get("confidence_score", 0.0),
            "failed_steps": failed_steps,
            "migration_analysis_completeness": state.get("migration_analysis_completeness", 0.0),
            "migration_analysis_failed_steps": state.get("migration_analysis_failed_steps") or [],
            "deprecated_api_rules_source": _deprecated_api_rules_source(state),
        },
    }


def report_node(state: VersionPilotState) -> dict:
    """LLM node: synthesizes grounded final report. Falls back to template when LLM unavailable."""
    trace = list(state.get("agent_trace", []))
    telemetry = dict(state.get("telemetry") or {})
    final_report = None
    critic_passed = state.get("critic_passed", True)
    effective_risk = state.get("risk_level", "unknown") if critic_passed else "Unverified"

    if LLMClient.is_available():
        try:
            llm = LLMClient()
            migration_plan = state.get("migration_plan") or {}
            user_prompt = (
                f"repo_url: {state.get('repo_url', '')}\n"
                f"health_score: {state.get('health_score', 0.0)}\n"
                f"risk_level: {effective_risk}\n"
                f"breakdown: {json.dumps(state.get('breakdown', {}))}\n"
                f"deprecated_findings: {json.dumps(state.get('deprecated_findings', []))}\n"
                f"breaking_change_analysis: {json.dumps(state.get('breaking_change_analysis', {}))}\n"
                f"migration_steps: {json.dumps(migration_plan.get('steps', []))}\n"
                f"security_metrics: {json.dumps(state.get('security_metrics', {}))}\n"
                f"failed_steps: {json.dumps(state.get('failed_steps', []))}\n"
                f"data_completeness: {state.get('data_completeness', 0.0)}\n"
                f"confidence_score: {state.get('confidence_score', 0.0)}\n"
                f"migration_analysis_completeness: {state.get('migration_analysis_completeness', 0.0)}\n"
                f"migration_analysis_failed_steps: {json.dumps(state.get('migration_analysis_failed_steps', []))}\n"
                f"deprecated_api_rules_source: {_deprecated_api_rules_source(state)}\n"
                f"critic_feedback: {state.get('critic_feedback', '')}"
            )
            raw = llm.call(_SYSTEM_PROMPT, user_prompt, max_tokens=1024)
            telemetry = merge_llm_usage(telemetry, llm)
            parsed = json.loads(raw)
            if not isinstance(parsed, dict):
                raise ValueError(f"LLM returned non-object JSON: {type(parsed).__name__}")
            if not isinstance(parsed.get("summary"), str):
                raise ValueError("LLM report missing or invalid 'summary'")
            if not isinstance(parsed.get("key_findings"), list):
                raise ValueError("LLM report missing or invalid 'key_findings'")
            if not isinstance(parsed.get("migration_recommendations"), list):
                raise ValueError("LLM report missing or invalid 'migration_recommendations'")
            if not isinstance(parsed.get("upstream_breaking_change_hints", []), list):
                raise ValueError("LLM report missing or invalid 'upstream_breaking_change_hints'")
            parsed.setdefault("upstream_breaking_change_hints", [])
            final_report = parsed
            trace.append({"node": "report", "status": "complete"})
        except Exception:
            final_report = None

    if final_report is None:
        final_report = _template_report(state, effective_risk)
        trace.append({"node": "report", "status": "fallback", "reason": "llm_unavailable_or_error"})

    # Overwrite factual fields from state — LLM must not alter these
    deterministic = _template_report(state, effective_risk)
    final_report["run_id"] = state.get("run_id", "")
    final_report["health_score"] = state.get("health_score", 0.0)
    final_report["key_findings"] = deterministic["key_findings"]
    final_report["migration_recommendations"] = deterministic["migration_recommendations"]
    final_report["upstream_breaking_change_hints"] = deterministic[
        "upstream_breaking_change_hints"
    ]
    final_report["data_quality"] = {
        "completeness": state.get("data_completeness", 0.0),
        "confidence": state.get("confidence_score", 0.0),
        "failed_steps": state.get("failed_steps") or [],
        "migration_analysis_completeness": state.get("migration_analysis_completeness", 0.0),
        "migration_analysis_failed_steps": state.get("migration_analysis_failed_steps") or [],
        "deprecated_api_rules_source": _deprecated_api_rules_source(state),
    }

    # If the critic never passed, mark the result as unverified
    final_report["critic"] = {
        "passed": critic_passed,
        "feedback": state.get("critic_feedback", ""),
        "retry_count": state.get("retry_count", 0),
    }
    final_report["risk_level"] = effective_risk
    if not critic_passed:
        final_report["summary"] = _template_report(state, effective_risk)["summary"]
    elif notice := _rules_source_notice(state):
        if notice.strip() not in final_report["summary"]:
            final_report["summary"] += notice

    final_report["telemetry"] = telemetry

    return {
        "final_report": final_report,
        "agent_trace": trace,
        "telemetry": telemetry,
    }
