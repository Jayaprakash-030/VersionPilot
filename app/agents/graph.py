import time
from langgraph.graph import END, START, StateGraph

from app.agents.critic_node import critic_node
from app.agents.evidence_node import evidence_node
from app.agents.planner_node import planner_node
from app.agents.recovery_node import recovery_node
from app.agents.report_node import report_node
from app.agents.scoring_node import scoring_node
from app.agents.state import VersionPilotState, create_initial_state


# ---------------------------------------------------------------------------
# Conditional edge (1.4)
# ---------------------------------------------------------------------------


def should_retry_or_report(state: VersionPilotState) -> str:
    """Route to report on critic pass or retry limit, otherwise to recovery."""
    if state.get("critic_passed"):
        return "report"
    if state.get("retry_count", 0) >= 2:
        return "report"
    return "recovery"


def with_timing(node_name, function):
    """Wrap a graph node to record its wall-clock duration in telemetry."""
    def wrapped(state):
        t0 = time.perf_counter()
        updates = function(state) or {}
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        telemetry = dict(updates.get("telemetry") or state.get("telemetry") or {})
        timings = dict(telemetry.get("node_timings_ms") or {})
        # If a node can run twice (critic→recovery→scoring), accumulate
        timings[node_name] = timings.get(node_name, 0.0) + elapsed_ms
        telemetry["node_timings_ms"] = timings
        updates["telemetry"] = telemetry
        return updates

    return wrapped


# ---------------------------------------------------------------------------
# Graph definition (1.4)
# ---------------------------------------------------------------------------


def build_graph() -> StateGraph:
    """Assemble and compile the VersionPilot LangGraph agent workflow."""
    graph = StateGraph(VersionPilotState)

    graph.add_node("planner", with_timing("planner", planner_node))
    graph.add_node("evidence", with_timing("evidence", evidence_node))
    graph.add_node("scoring", with_timing("scoring", scoring_node))
    graph.add_node("critic", with_timing("critic", critic_node))
    graph.add_node("recovery", with_timing("recovery", recovery_node))
    graph.add_node("report", with_timing("report", report_node))

    graph.add_edge(START, "planner")
    graph.add_edge("planner", "evidence")
    graph.add_edge("evidence", "scoring")
    graph.add_edge("scoring", "critic")
    graph.add_conditional_edges(
        "critic",
        should_retry_or_report,
        {
            "report": "report",
            "recovery": "recovery",
        },
    )
    graph.add_edge("recovery", "scoring")
    graph.add_edge("report", END)

    return graph.compile()


compiled_graph = build_graph()


def run_graph(
    repo_url: str,
    repo_path: str = "",
    config_version: str = "config/scoring_v1.yaml",
    run_id: str = "",
) -> dict:
    """Run the compiled agent graph for a repository and return final state."""
    initial_state = create_initial_state(
        repo_url, repo_path, config_version, run_id=run_id
    )

    t0 = time.perf_counter()
    final_state = compiled_graph.invoke(initial_state)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    telemetry = dict(final_state.get("telemetry") or {})
    telemetry["total_wall_ms"] = elapsed_ms
    final_state["telemetry"] = telemetry
    return final_state
