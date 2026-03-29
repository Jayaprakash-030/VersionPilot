from __future__ import annotations

import json

from app.agents.state import VersionPilotState
from app.llm_client import LLMClient

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
  "data_quality": {
    "completeness": <float>,
    "confidence": <float>,
    "failed_steps": [...]
  }
}

Rules:
- key_findings must cite specific values from the data (scores, counts, package names).
- migration_recommendations must reference a finding or migration step from the data.
- If there are no findings, key_findings must be [].
- If there are no migration steps, migration_recommendations must be [].
- health_score and risk_level must be passed through exactly as given.
"""


def _template_report(state: VersionPilotState) -> dict:
    """Template-based fallback when LLM is unavailable."""
    migration_plan = state.get("migration_plan") or {}
    steps = migration_plan.get("steps", [])
    deprecated_findings = state.get("deprecated_findings") or []
    failed_steps = state.get("failed_steps") or []

    key_findings = []
    for f in deprecated_findings:
        key_findings.append({
            "finding": f"Deprecated API usage: {f.get('symbol', 'unknown')} in {f.get('file_path', 'unknown')}",
            "evidence": f"package={f.get('package', 'unknown')}, line={f.get('line', '?')}",
            "severity": f.get("severity", "medium"),
        })

    migration_recommendations = []
    for step in steps:
        migration_recommendations.append({
            "action": step.get("action", "Review migration step"),
            "priority": "high" if step.get("severity") == "high" else "medium",
            "reason": f"type={step.get('type', 'unknown')}, package={step.get('package', 'unknown')}",
        })

    return {
        "summary": (
            f"Health score: {state.get('health_score', 0.0):.1f} ({state.get('risk_level', 'unknown')} risk). "
            f"{len(deprecated_findings)} deprecated API finding(s), "
            f"{len(steps)} migration step(s). "
            f"Data completeness: {state.get('data_completeness', 0.0):.0%}."
        ),
        "health_score": state.get("health_score", 0.0),
        "risk_level": state.get("risk_level", "unknown"),
        "key_findings": key_findings,
        "migration_recommendations": migration_recommendations,
        "data_quality": {
            "completeness": state.get("data_completeness", 0.0),
            "confidence": state.get("confidence_score", 0.0),
            "failed_steps": failed_steps,
        },
    }


def report_node(state: VersionPilotState) -> dict:
    """LLM node: synthesizes grounded final report. Falls back to template when LLM unavailable."""
    trace = list(state.get("agent_trace", []))
    final_report = None

    if LLMClient.is_available():
        try:
            llm = LLMClient()
            migration_plan = state.get("migration_plan") or {}
            user_prompt = (
                f"repo_url: {state.get('repo_url', '')}\n"
                f"health_score: {state.get('health_score', 0.0)}\n"
                f"risk_level: {state.get('risk_level', '')}\n"
                f"breakdown: {json.dumps(state.get('breakdown', {}))}\n"
                f"deprecated_findings: {json.dumps(state.get('deprecated_findings', []))}\n"
                f"breaking_change_analysis: {json.dumps(state.get('breaking_change_analysis', {}))}\n"
                f"migration_steps: {json.dumps(migration_plan.get('steps', []))}\n"
                f"security_metrics: {json.dumps(state.get('security_metrics', {}))}\n"
                f"failed_steps: {json.dumps(state.get('failed_steps', []))}\n"
                f"data_completeness: {state.get('data_completeness', 0.0)}\n"
                f"confidence_score: {state.get('confidence_score', 0.0)}\n"
                f"critic_feedback: {state.get('critic_feedback', '')}"
            )
            raw = llm.call(_SYSTEM_PROMPT, user_prompt, max_tokens=1024)
            final_report = json.loads(raw)
            trace.append({"node": "report", "status": "complete"})
        except Exception:
            final_report = None

    if final_report is None:
        final_report = _template_report(state)
        trace.append({"node": "report", "status": "fallback", "reason": "llm_unavailable_or_error"})

    return {"final_report": final_report, "agent_trace": trace}
