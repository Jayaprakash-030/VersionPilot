from __future__ import annotations

import json

from app.agents.state import VersionPilotState
from app.agents.llm_client import LLMClient

_SYSTEM_PROMPT = """\
You are a dependency health report critic. Your job is to validate that the analysis
results are internally consistent and not suspicious. Return JSON only — no explanation.

Output format:
{
  "passed": true or false,
  "feedback": "short explanation of any issues found, or empty string if passed"
}

Check for these red flags:
- High health score (>80) but one or more data collection steps failed — the score is
  based on incomplete data and should not be trusted.
- Zero dependencies parsed but dependency_score is 100 — parser likely failed.
- Low risk level but critical or high severity vulnerabilities present.
- Any combination where a metric looks perfect but the underlying data is missing.

If no red flags are found, return {"passed": true, "feedback": ""}.
"""


def _deterministic_check(state: VersionPilotState) -> tuple[bool, str]:
    """Applies simple rule-based checks when LLM is unavailable."""
    failed_steps = state.get("failed_steps", [])
    health_score = state.get("health_score", 0.0)
    breakdown = state.get("breakdown", {})
    security_metrics = state.get("security_metrics", {})

    if failed_steps and health_score > 80:
        return False, f"High score ({health_score:.1f}) with failed data collection steps: {failed_steps}"

    dep_score = breakdown.get("dependency_score", None)
    dep_metrics = state.get("dependency_metrics", {})
    total_deps = dep_metrics.get("total_dependencies", None)
    if total_deps == 0 and dep_score is not None and dep_score >= 100:
        return False, "Zero dependencies parsed but dependency_score is 100 — parser likely failed"

    critical_vulns = security_metrics.get("critical", 0)
    high_vulns = security_metrics.get("high", 0)
    risk_level = state.get("risk_level", "")
    if (critical_vulns > 0 or high_vulns > 0) and risk_level in ("low", "healthy"):
        return False, f"Low risk level '{risk_level}' despite {critical_vulns} critical and {high_vulns} high vulnerabilities"

    return True, ""


def critic_node(state: VersionPilotState) -> dict:
    """LLM node: validates analysis consistency. Falls back to deterministic checks."""
    trace = list(state.get("agent_trace", []))

    passed = True
    feedback = ""

    if LLMClient.is_available():
        try:
            llm = LLMClient()
            user_prompt = (
                f"health_score: {state.get('health_score', 0.0)}\n"
                f"risk_level: {state.get('risk_level', '')}\n"
                f"breakdown: {json.dumps(state.get('breakdown', {}))}\n"
                f"failed_steps: {json.dumps(state.get('failed_steps', []))}\n"
                f"dependency_metrics: {json.dumps(state.get('dependency_metrics', {}))}\n"
                f"security_metrics: {json.dumps(state.get('security_metrics', {}))}\n"
                f"data_completeness: {state.get('data_completeness', 1.0)}\n"
                f"confidence_score: {state.get('confidence_score', 1.0)}"
            )
            raw = llm.call(_SYSTEM_PROMPT, user_prompt, max_tokens=256)
            result = json.loads(raw)
            passed = bool(result.get("passed", True))
            feedback = result.get("feedback", "")
        except Exception:
            passed, feedback = _deterministic_check(state)
            trace.append({"node": "critic", "status": "fallback", "reason": "llm_error"})
    else:
        passed, feedback = _deterministic_check(state)
        trace.append({"node": "critic", "status": "fallback", "reason": "llm_unavailable"})

    if LLMClient.is_available() and not any(
        e.get("node") == "critic" and e.get("status") == "fallback" for e in trace
    ):
        trace.append({"node": "critic", "status": "complete", "passed": passed})

    return {
        "critic_passed": passed,
        "critic_feedback": feedback,
        "agent_trace": trace,
    }
