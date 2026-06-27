# VersionPilot — Session Context

Full architecture and build plan is in `Plan.md`. Read it before starting any feature work.

---

## What This Project Is

AI-driven dependency health and migration assistant. Goes beyond "you are outdated" to answer:
**"what will break in your code, where, and here is the exact migration path."**

Portfolio project + production system. The differentiator: agentic AI orchestration with real evaluation metrics and MLOps practices.

---

## What Is Already Built

### Package Structure (current)
```
app/
├── core/           — V1 pipeline foundations
│   ├── pipeline.py          GitHub → dependency → freshness → OSV → score
│   ├── risk_scoring.py      weighted scoring from config/scoring_v1.yaml
│   ├── models.py            frozen dataclasses (RepoMetrics, DependencyMetrics, SecurityMetrics, HealthReport)
│   ├── github_client.py     GitHub API calls + repo URL parsing
│   ├── dependency_parser.py parse requirements.txt / pyproject.toml
│   ├── dependency_freshness.py check how outdated deps are
│   ├── vulnerability_scanner.py OSV vulnerability lookup
│   └── retry.py             exponential backoff with jitter
├── analysis/       — Phase 2 differentiator tools
│   ├── deprecated_api_scanner.py  AST scanner; accepts dynamic rules dict
│   ├── changelog_analyzer.py      regex parser for breaking changes
│   ├── release_notes_fetcher.py   fetch GitHub latest release or PyPI description
│   └── migration_planner.py       ordered migration steps from findings
├── agents/         — Phase 3 LangGraph nodes
│   ├── graph.py             StateGraph + conditional edges + run_graph()
│   ├── state.py             VersionPilotState TypedDict + create_initial_state
│   ├── planner_node.py      LLM: analysis strategy decision
│   ├── evidence_node.py     deterministic: all tools, auto-clone, provenance
│   ├── scoring_node.py      deterministic: health score computation
│   ├── critic_node.py       LLM: consistency validation
│   ├── recovery_node.py     deterministic: confidence degradation + retry
│   ├── report_node.py       LLM: grounded final report synthesis
│   └── llm_client.py        AnthropicVertex + Gemini fallback
├── tools/          — LangGraph tool wrappers
│   ├── tool_registry.py     wraps all modules as callable tools; clone_repo
│   └── rules_extractor.py   LLM extracts deprecation rules from release notes
└── main.py         — CLI entry point (--mode basic|agent)
```

### V1 — Deterministic Pipeline (done)
- `app/main.py` — CLI (`--mode basic|agent`, `--config`, `--output`, `--force`, `--json`)
- `app/core/pipeline.py` — GitHub → dependency → freshness → OSV → score
- `app/core/risk_scoring.py` — weighted scoring from `config/scoring_v1.yaml` (activity 30% / dependency 40% / security 30%)
- `app/core/retry.py` — exponential backoff with jitter
- `app/core/models.py` — frozen dataclasses (RepoMetrics, DependencyMetrics, SecurityMetrics, HealthReport)
- `eval/run_eval.py` — batch evaluation runner

### Phase 2 — Differentiator Tools (done)
- `app/analysis/deprecated_api_scanner.py` — AST-based Python scanner against `data/deprecation_rules.json`
- `app/analysis/changelog_analyzer.py` — regex parser for breaking changes and deprecations in release notes
- `app/analysis/release_notes_fetcher.py` — fetches GitHub latest release or PyPI description
- `app/analysis/migration_planner.py` — generates ordered migration steps from findings

### Phase 3 — LangGraph Multi-Agent System (done)
- `app/agents/state.py` — `VersionPilotState` TypedDict + `create_initial_state`
- `app/agents/graph.py` — `StateGraph` with all nodes and conditional edges
- `app/tools/tool_registry.py` — all existing modules wrapped as callable tools; `clone_repo` auto-clones when `repo_path` not provided
- `app/agents/llm_client.py` — `AnthropicVertex` wrapper with retry + token tracking + Gemini fallback
- `app/tools/rules_extractor.py` — LLM extracts deprecation rules from release notes
- `app/analysis/deprecated_api_scanner.py` — updated to accept dynamic `rules` dict (backward-compatible)
- `app/agents/evidence_node.py` — deterministic: runs V1 pipeline, auto-clones repo if needed, fetches per-dependency release notes, extracts LLM rules, scans deprecated APIs, analyzes changelogs, generates migration plan, tracks provenance
- `app/agents/scoring_node.py` — deterministic: reconstructs dataclasses from state dicts, calls existing scoring functions
- `app/agents/planner_node.py` — LLM: decides analysis strategy (full vs lightweight), deterministic fallback
- `app/agents/critic_node.py` — LLM: validates consistency (high score + failed steps, zero deps + perfect dep score, low risk + critical vulns), deterministic fallback
- `app/agents/recovery_node.py` — deterministic: increments retry_count, degrades confidence_score (-0.2) and data_completeness (-0.15)
- `app/agents/report_node.py` — LLM: synthesizes grounded final report from all state signals; template fallback when LLM unavailable
- `app/main.py` — `--mode agent` calls `run_graph`, extracts `final_report`, falls back to basic pipeline on any exception
- GCP project `versionpilot` created, Vertex AI enabled, `.env` wired up
- Gemini fallback working via `langchain-google-genai` (`gemini-3-flash-preview`)
- Codex Sonnet 4.6 quota pending approval on Vertex AI (1-2 business days)
- 176 tests passing

### Test Coverage
- 176 tests, all passing: `tests/unit/` (26 files) + `tests/integration/`
- Run with: `vpilot/bin/python -m pytest tests/ -v`

### Verified Working (tested with real repos)
- `python -m app.main --mode basic https://github.com/psf/requests --json`
- `python -m app.main --mode agent https://github.com/psf/requests --json`
- `python -m app.main --mode agent https://github.com/psf/requests --repo-path /path/to/clone --json`
- Requires `GITHUB_TOKEN` env var for GitHub API calls

---

## Phase 3 Complete — Graph Topology

```
START → planner_node → evidence_node → scoring_node → critic_node
                                            ↑               ↓
                                       recovery_node   [pass/fail]
                                                            ↓
                                                       report_node → END
```

All 10 sessions done. Session highlights:
- ✅ Session 1: `state.py` + skeleton `graph.py`
- ✅ Session 2: `tool_registry.py`
- ✅ Session 3: `llm_client.py` + `rules_extractor.py`
- ✅ Session 4: `evidence_node.py`
- ✅ Session 5: `scoring_node.py`
- ✅ Session 6: `planner_node.py`
- ✅ Session 7: `critic_node.py` + conditional edge
- ✅ Session 8: `recovery_node.py` + retry loop
- ✅ Session 9: `report_node.py`
- ✅ Session 10: CLI wired, `clone_repo` auto-clone, `agent_orchestrator.py` deleted

---

## What We Are Building Next

### Phase 4 — Portfolio-Scale Evaluation
### Phase 5 — MLOps Layer

See `Eval.md` for the detailed Phase 4 methodology and `Plan.md` for the
architecture and Phase 5 direction.

Phase 4 focuses on:
- Deprecated API scanner precision, recall, F1, and source-line accuracy
- Scoring behavioral correctness using frozen evidence
- 3-5 controlled migration cases validated with tests
- 8-10 reliability scenarios covering API and LLM failures
- A committed `eval/EVAL_REPORT.md` with measured results and limitations

---

## LLM Configuration

Codex is accessed via **Google Cloud Vertex AI** (not Anthropic API directly).
Gemini is accessed via **Google AI API** (not Vertex AI) as a fallback when Codex quota is exceeded.

`llm_client.py` call order:
1. Codex Sonnet 4.6 via `anthropic.AnthropicVertex` (preferred)
2. Gemini 3 Flash via `langchain-google-genai` (fallback on quota/rate-limit errors)

Required env vars (loaded from `.env` via `python-dotenv`):
```
GOOGLE_CLOUD_PROJECT=versionpilot   # GCP project ID with Vertex AI enabled
CLOUD_ML_REGION=us-east5            # Vertex AI region for Codex
GITHUB_TOKEN=...                    # GitHub API calls
GOOGLE_API_KEY=...                  # Google AI API key for Gemini fallback
```

Auth: run `gcloud auth application-default login` for Vertex AI credentials.

New dependencies installed:
```
anthropic[vertex]>=0.18.0
langgraph>=0.1.0
langchain-core>=0.1.0
langchain-google-genai>=2.0.0
python-dotenv>=1.0.0
```

---

## Core Design Rules (never violate these)

1. **Don't break V1** — `--mode basic` must keep working. All existing tests must keep passing.
2. **Tools = existing code** — do not reimplement. `tool_registry.py` wraps what exists.
3. **LLMs as orchestrators, not workers** — only planner, critic, and report nodes use LLM. Everything else is deterministic.
4. **Fail gracefully** — agent mode falls back to basic mode if LLM unavailable. Codex falls back to Gemini on quota errors.
5. **Every claim is traceable** — provenance tracked per signal. Report node never hallucinates recommendations.
6. **Scoring is versioned and reproducible** — same input + same config version = same score.

---

## Known Issues to Keep in Mind

- When `github_data_collector` or `dependency_parser` fail, all metrics default to zero → falsely perfect score. The critic node flags "high score + failed steps" as suspicious.
- `dependency_parser` only handles `requirements.txt` and `pyproject.toml`. Repos using `setup.py`/`setup.cfg` will have 0 dependencies parsed (e.g. numpy, clint).
- Auto-clone (`clone_repo`) uses `--depth=1` shallow clone. This is sufficient for AST scanning but won't include full git history.
- Release notes are always fetched for the **latest PyPI version**, not the version pinned in `requirements.txt`. Deprecation findings may include things not relevant until the user actually upgrades to latest.
- Codex Sonnet 4.6 quota on Vertex AI is pending approval. Gemini fallback is active in the meantime.
