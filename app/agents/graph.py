from langgraph.graph import END, START, StateGraph

from app.agents.evidence_node import evidence_node
from app.agents.planner_node import planner_node
from app.agents.scoring_node import scoring_node
from app.agents.state import VersionPilotState, create_initial_state


# ---------------------------------------------------------------------------
# Skeleton nodes (1.3) — each just logs itself and passes through
# ---------------------------------------------------------------------------



def critic_node(state: VersionPilotState) -> dict:
    trace = list(state.get("agent_trace", []))
    trace.append({"node": "critic", "status": "pass-through"})
    return {"agent_trace": trace, "critic_passed": True, "critic_feedback": ""}


def recovery_node(state: VersionPilotState) -> dict:
    trace = list(state.get("agent_trace", []))
    trace.append({"node": "recovery", "status": "pass-through"})
    return {"agent_trace": trace, "retry_count": state.get("retry_count", 0) + 1}


def report_node(state: VersionPilotState) -> dict:
    trace = list(state.get("agent_trace", []))
    trace.append({"node": "report", "status": "pass-through"})
    return {"agent_trace": trace, "final_report": {}}


# ---------------------------------------------------------------------------
# Conditional edge (1.4)
# ---------------------------------------------------------------------------

def should_retry_or_report(state: VersionPilotState) -> str:
    if state.get("critic_passed"):
        return "report"
    if state.get("retry_count", 0) >= 2:
        return "report"
    return "recovery"


# ---------------------------------------------------------------------------
# Graph definition (1.4)
# ---------------------------------------------------------------------------

def build_graph() -> StateGraph:
    graph = StateGraph(VersionPilotState)

    graph.add_node("planner", planner_node)
    graph.add_node("evidence", evidence_node)
    graph.add_node("scoring", scoring_node)
    graph.add_node("critic", critic_node)
    graph.add_node("recovery", recovery_node)
    graph.add_node("report", report_node)

    graph.add_edge(START, "planner")
    graph.add_edge("planner", "evidence")
    graph.add_edge("evidence", "scoring")
    graph.add_edge("scoring", "critic")
    graph.add_conditional_edges("critic", should_retry_or_report, {
        "report": "report",
        "recovery": "recovery",
    })
    graph.add_edge("recovery", "scoring")
    graph.add_edge("report", END)

    return graph.compile()


compiled_graph = build_graph()


def run_graph(repo_url: str, repo_path: str = "", config_version: str = "config/scoring_v1.yaml") -> dict:
    initial_state = create_initial_state(repo_url, repo_path, config_version)
    return compiled_graph.invoke(initial_state)
