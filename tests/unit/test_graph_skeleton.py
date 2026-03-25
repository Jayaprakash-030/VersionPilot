from app.agents.graph import run_graph


def test_all_nodes_logged_to_trace():
    result = run_graph("https://github.com/psf/requests")
    nodes = [entry["node"] for entry in result["agent_trace"]]
    assert "planner" in nodes
    assert "evidence" in nodes
    assert "scoring" in nodes
    assert "critic" in nodes
    assert "report" in nodes


def test_critic_passed_is_true():
    result = run_graph("https://github.com/psf/requests")
    assert result["critic_passed"] is True


def test_final_report_is_not_none():
    result = run_graph("https://github.com/psf/requests")
    assert result["final_report"] is not None


def test_no_recovery_in_happy_path():
    result = run_graph("https://github.com/psf/requests")
    nodes = [entry["node"] for entry in result["agent_trace"]]
    assert "recovery" not in nodes


def test_run_id_preserved_in_output():
    result = run_graph("https://github.com/psf/requests")
    assert isinstance(result["run_id"], str) and len(result["run_id"]) > 0
