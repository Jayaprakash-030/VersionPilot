from __future__ import annotations

from app.agents.state import VersionPilotState


def recovery_node(state: VersionPilotState) -> dict:
    """Deterministic node: adjusts confidence after critic failure, increments retry count."""
    retry_count = state.get("retry_count", 0) + 1
    confidence_score = max(0.0, state.get("confidence_score", 1.0) - 0.2)
    data_completeness = max(0.0, state.get("data_completeness", 1.0) - 0.15)

    trace = list(state.get("agent_trace", []))
    trace.append({
        "node": "recovery",
        "action": f"retry {retry_count}: confidence → {confidence_score:.2f}, completeness → {data_completeness:.2f}",
        "critic_feedback": state.get("critic_feedback", ""),
    })

    return {
        "retry_count": retry_count,
        "confidence_score": confidence_score,
        "data_completeness": data_completeness,
        "agent_trace": trace,
    }
