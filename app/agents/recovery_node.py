from __future__ import annotations

from app.agents.state import VersionPilotState


def recovery_node(state: VersionPilotState) -> dict:
    """Deterministic node: adjusts confidence after critic failure, increments retry count."""
    retry_count = state.get("retry_count", 0) + 1
    confidence_penalty = round(state.get("confidence_penalty", 0.0) + 0.2, 2)

    trace = list(state.get("agent_trace", []))
    trace.append({
        "node": "recovery",
        "action": f"retry {retry_count}: confidence_penalty → {confidence_penalty:.2f}",
        "critic_feedback": state.get("critic_feedback", ""),
    })

    return {
        "retry_count": retry_count,
        "confidence_penalty": confidence_penalty,
        "agent_trace": trace,
    }
