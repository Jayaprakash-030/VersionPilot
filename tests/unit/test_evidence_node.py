"""Tests for app/agents/evidence_node.py"""
from __future__ import annotations

from unittest.mock import patch

from app.agents.evidence_node import evidence_node
from app.agents.state import create_initial_state


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _base_state(**kwargs):
    state = create_initial_state(
        repo_url="https://github.com/example/repo",
        repo_path="",
        config_version="config/scoring_v1.yaml",
    )
    state.update(kwargs)
    return state


_PIPELINE_OK = {
    "status": "ok",
    "repo_metrics": {"stars": 100, "forks": 10, "last_commit_days": 5,
                     "last_release_days": 30, "open_issues": 3, "closed_issues": 20},
    "dependency_metrics": {"total_dependencies": 5, "outdated_dependencies": 1},
    "security_metrics": {"critical": 0, "high": 0, "medium": 1, "low": 2},
    "breakdown": {"activity_score": 80.0, "dependency_score": 80.0, "security_score": 90.0},
    "health_score": 83.0,
    "risk_level": "low",
    "failed_steps": [],
    "data_completeness": 1.0,
    "confidence_score": 0.9,
}

_DEP_NAMES_OK = {"status": "ok", "names": ["requests", "flask"]}

_NOTES_OK = {"status": "ok", "notes_text": "Deprecated old_func. Use new_func instead.", "latest_version": "2.0.0"}
_NOTES_EMPTY = {"status": "ok", "notes_text": "", "latest_version": "1.0.0"}

_CHANGELOG_OK = {"status": "ok", "breaking_changes": [], "deprecations": ["old_func"]}

_SCAN_OK = {"status": "ok", "finding_count": 1, "findings": [{"symbol": "old_func", "file": "app.py", "line": 5}]}

_MIGRATION_OK = {"status": "ok", "steps": [{"action": "Replace old_func with new_func"}]}


# ---------------------------------------------------------------------------
# Core state population
# ---------------------------------------------------------------------------

def test_state_populated_from_pipeline():
    """Evidence node writes repo/dependency/security metrics from V1 pipeline."""
    with patch("app.agents.evidence_node.ToolRegistry") as MockRegistry, \
         patch("app.agents.evidence_node.RulesExtractor") as MockExtractor:
        registry = MockRegistry.return_value
        registry.run_v1_pipeline.return_value = _PIPELINE_OK
        registry.fetch_dependency_names.return_value = _DEP_NAMES_OK
        registry.fetch_dependency_release_notes.return_value = _NOTES_EMPTY
        registry.generate_migration_plan.return_value = _MIGRATION_OK

        MockExtractor.return_value.build_rules_dict.return_value = {}

        result = evidence_node(_base_state())

    assert result["repo_metrics"] == _PIPELINE_OK["repo_metrics"]
    assert result["dependency_metrics"] == _PIPELINE_OK["dependency_metrics"]
    assert result["security_metrics"] == _PIPELINE_OK["security_metrics"]


# ---------------------------------------------------------------------------
# Provenance tracking
# ---------------------------------------------------------------------------

def test_provenance_tracked_per_tool():
    """Every tool call appends an entry to provenance."""
    with patch("app.agents.evidence_node.ToolRegistry") as MockRegistry, \
         patch("app.agents.evidence_node.RulesExtractor") as MockExtractor:
        registry = MockRegistry.return_value
        registry.run_v1_pipeline.return_value = _PIPELINE_OK
        registry.fetch_dependency_names.return_value = _DEP_NAMES_OK
        registry.fetch_dependency_release_notes.return_value = _NOTES_OK
        registry.analyze_changelog.return_value = _CHANGELOG_OK
        registry.generate_migration_plan.return_value = _MIGRATION_OK

        MockExtractor.return_value.build_rules_dict.return_value = {}

        result = evidence_node(_base_state())

    sources = [p["source"] for p in result["provenance"]]
    assert "v1_pipeline" in sources
    assert "fetch_dependency_names" in sources
    # One entry per dependency for release notes
    assert "release_notes:requests" in sources
    assert "release_notes:flask" in sources
    assert "migration_planner" in sources
    # All entries have a timestamp and status
    for entry in result["provenance"]:
        assert "timestamp" in entry
        assert "status" in entry


# ---------------------------------------------------------------------------
# Failed steps recording
# ---------------------------------------------------------------------------

def test_failed_tool_recorded_in_failed_steps():
    """When a tool returns status=error, it's added to failed_steps."""
    with patch("app.agents.evidence_node.ToolRegistry") as MockRegistry, \
         patch("app.agents.evidence_node.RulesExtractor") as MockExtractor:
        registry = MockRegistry.return_value
        registry.run_v1_pipeline.return_value = {"status": "error", "error": "network timeout"}
        registry.fetch_dependency_names.return_value = _DEP_NAMES_OK
        registry.fetch_dependency_release_notes.return_value = _NOTES_EMPTY
        registry.generate_migration_plan.return_value = _MIGRATION_OK

        MockExtractor.return_value.build_rules_dict.return_value = {}

        result = evidence_node(_base_state())

    assert "v1_pipeline" in result["failed_steps"]


def test_v1_pipeline_failed_steps_merged():
    """failed_steps reported by V1 pipeline are merged into the node's failed_steps."""
    pipeline_with_failures = {**_PIPELINE_OK, "failed_steps": ["github_data_collector"]}
    with patch("app.agents.evidence_node.ToolRegistry") as MockRegistry, \
         patch("app.agents.evidence_node.RulesExtractor") as MockExtractor:
        registry = MockRegistry.return_value
        registry.run_v1_pipeline.return_value = pipeline_with_failures
        registry.fetch_dependency_names.return_value = _DEP_NAMES_OK
        registry.fetch_dependency_release_notes.return_value = _NOTES_EMPTY
        registry.generate_migration_plan.return_value = _MIGRATION_OK

        MockExtractor.return_value.build_rules_dict.return_value = {}

        result = evidence_node(_base_state())

    assert "github_data_collector" in result["failed_steps"]


# ---------------------------------------------------------------------------
# Deprecated API scan gating on repo_path
# ---------------------------------------------------------------------------

def test_deprecated_scan_skipped_when_no_repo_path():
    """scan_deprecated_apis must not be called when repo_path is empty."""
    with patch("app.agents.evidence_node.ToolRegistry") as MockRegistry, \
         patch("app.agents.evidence_node.RulesExtractor") as MockExtractor:
        registry = MockRegistry.return_value
        registry.run_v1_pipeline.return_value = _PIPELINE_OK
        registry.fetch_dependency_names.return_value = _DEP_NAMES_OK
        registry.fetch_dependency_release_notes.return_value = _NOTES_EMPTY
        registry.generate_migration_plan.return_value = _MIGRATION_OK

        MockExtractor.return_value.build_rules_dict.return_value = {}

        result = evidence_node(_base_state(repo_path=""))

    registry.scan_deprecated_apis.assert_not_called()
    assert result["deprecated_findings"] == []


def test_deprecated_scan_runs_when_repo_path_provided():
    """scan_deprecated_apis is called when repo_path is set."""
    with patch("app.agents.evidence_node.ToolRegistry") as MockRegistry, \
         patch("app.agents.evidence_node.RulesExtractor") as MockExtractor:
        registry = MockRegistry.return_value
        registry.run_v1_pipeline.return_value = _PIPELINE_OK
        registry.fetch_dependency_names.return_value = _DEP_NAMES_OK
        registry.fetch_dependency_release_notes.return_value = _NOTES_EMPTY
        registry.scan_deprecated_apis.return_value = _SCAN_OK
        registry.generate_migration_plan.return_value = _MIGRATION_OK

        MockExtractor.return_value.build_rules_dict.return_value = {}

        result = evidence_node(_base_state(repo_path="/tmp/repo"))

    registry.scan_deprecated_apis.assert_called_once()
    assert len(result["deprecated_findings"]) == 1


def test_deprecated_scan_failure_recorded():
    """scan_deprecated_apis error is recorded in failed_steps."""
    with patch("app.agents.evidence_node.ToolRegistry") as MockRegistry, \
         patch("app.agents.evidence_node.RulesExtractor") as MockExtractor:
        registry = MockRegistry.return_value
        registry.run_v1_pipeline.return_value = _PIPELINE_OK
        registry.fetch_dependency_names.return_value = _DEP_NAMES_OK
        registry.fetch_dependency_release_notes.return_value = _NOTES_EMPTY
        registry.scan_deprecated_apis.return_value = {"status": "error", "error": "parse error"}
        registry.generate_migration_plan.return_value = _MIGRATION_OK

        MockExtractor.return_value.build_rules_dict.return_value = {}

        result = evidence_node(_base_state(repo_path="/tmp/repo"))

    assert "deprecated_api_scan" in result["failed_steps"]


# ---------------------------------------------------------------------------
# LLM-extracted rules passed to scanner
# ---------------------------------------------------------------------------

def test_llm_rules_passed_to_scan_deprecated_apis():
    """When RulesExtractor returns rules, they are passed to scan_deprecated_apis."""
    extracted_rules = {"requests": {"deprecated_symbols": {"requests.compat": {"replacement": "", "severity": "high", "note": "removed"}}}}

    with patch("app.agents.evidence_node.ToolRegistry") as MockRegistry, \
         patch("app.agents.evidence_node.RulesExtractor") as MockExtractor:
        registry = MockRegistry.return_value
        registry.run_v1_pipeline.return_value = _PIPELINE_OK
        registry.fetch_dependency_names.return_value = {"status": "ok", "names": ["requests"]}
        registry.fetch_dependency_release_notes.return_value = _NOTES_OK
        registry.analyze_changelog.return_value = _CHANGELOG_OK
        registry.scan_deprecated_apis.return_value = _SCAN_OK
        registry.generate_migration_plan.return_value = _MIGRATION_OK

        extractor = MockExtractor.return_value
        extractor.build_rules_dict.return_value = extracted_rules

        evidence_node(_base_state(repo_path="/tmp/repo"))

    _, kwargs = registry.scan_deprecated_apis.call_args
    assert kwargs.get("rules") == extracted_rules


def test_no_llm_rules_falls_back_to_static_rules():
    """When RulesExtractor returns no rules, scan_deprecated_apis is called with rules=None."""
    with patch("app.agents.evidence_node.ToolRegistry") as MockRegistry, \
         patch("app.agents.evidence_node.RulesExtractor") as MockExtractor:
        registry = MockRegistry.return_value
        registry.run_v1_pipeline.return_value = _PIPELINE_OK
        registry.fetch_dependency_names.return_value = _DEP_NAMES_OK
        registry.fetch_dependency_release_notes.return_value = _NOTES_EMPTY
        registry.scan_deprecated_apis.return_value = _SCAN_OK
        registry.generate_migration_plan.return_value = _MIGRATION_OK

        MockExtractor.return_value.build_rules_dict.return_value = {}

        evidence_node(_base_state(repo_path="/tmp/repo"))

    _, kwargs = registry.scan_deprecated_apis.call_args
    assert kwargs.get("rules") is None


# ---------------------------------------------------------------------------
# Agent trace
# ---------------------------------------------------------------------------

def test_agent_trace_updated():
    """Evidence node appends its completion entry to agent_trace."""
    with patch("app.agents.evidence_node.ToolRegistry") as MockRegistry, \
         patch("app.agents.evidence_node.RulesExtractor") as MockExtractor:
        registry = MockRegistry.return_value
        registry.run_v1_pipeline.return_value = _PIPELINE_OK
        registry.fetch_dependency_names.return_value = _DEP_NAMES_OK
        registry.fetch_dependency_release_notes.return_value = _NOTES_EMPTY
        registry.generate_migration_plan.return_value = _MIGRATION_OK

        MockExtractor.return_value.build_rules_dict.return_value = {}

        result = evidence_node(_base_state())

    evidence_entries = [t for t in result["agent_trace"] if t.get("node") == "evidence"]
    assert len(evidence_entries) == 1
    assert evidence_entries[0]["status"] == "complete"
