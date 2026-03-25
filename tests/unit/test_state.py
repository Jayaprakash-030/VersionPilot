from app.agents.state import create_initial_state


def test_create_initial_state_defaults():
    state = create_initial_state("https://github.com/psf/requests")
    assert state["repo_url"] == "https://github.com/psf/requests"
    assert state["repo_path"] == ""
    assert state["config_version"] == "config/scoring_v1.yaml"
    assert isinstance(state["run_id"], str) and len(state["run_id"]) > 0


def test_create_initial_state_empty_collections():
    state = create_initial_state("https://github.com/psf/requests")
    assert state["repo_metrics"] == {}
    assert state["dependency_metrics"] == {}
    assert state["security_metrics"] == {}
    assert state["deprecated_findings"] == []
    assert state["agent_trace"] == []
    assert state["failed_steps"] == []
    assert state["provenance"] == []


def test_create_initial_state_numeric_defaults():
    state = create_initial_state("https://github.com/psf/requests")
    assert state["health_score"] == 0.0
    assert state["data_completeness"] == 0.0
    assert state["confidence_score"] == 0.0
    assert state["retry_count"] == 0
    assert state["critic_passed"] is False


def test_create_initial_state_custom_args():
    state = create_initial_state(
        repo_url="https://github.com/pallets/flask",
        repo_path="/tmp/flask",
        config_version="config/scoring_v2.yaml",
    )
    assert state["repo_path"] == "/tmp/flask"
    assert state["config_version"] == "config/scoring_v2.yaml"


def test_run_id_is_unique():
    s1 = create_initial_state("https://github.com/psf/requests")
    s2 = create_initial_state("https://github.com/psf/requests")
    assert s1["run_id"] != s2["run_id"]
