# VersionPilot

AI-driven dependency health and migration assistant. Goes beyond "you are outdated" to answer:
**"what will break in your code, where, and here is the exact migration path."**

Portfolio project demonstrating agentic AI orchestration with real evaluation metrics and MLOps practices.

---

## What It Does

Most tools tell you *that* you are outdated. VersionPilot tells you:

- What is the health score of this repository's dependencies?
- Which deprecated APIs are you actively calling, and on which line?
- What breaking changes are in the release notes of your dependencies?
- What are the exact migration steps to upgrade safely?

---

## Architecture

### Two modes

```bash
# Deterministic V1 pipeline — fast, no LLM
python -m app.main https://github.com/owner/repo --mode basic --json

# LangGraph multi-agent system — full analysis with LLM synthesis
python -m app.main https://github.com/owner/repo --mode agent --json
```

### LangGraph graph (agent mode)

```
START → planner_node → evidence_node → scoring_node → critic_node
                                            ↑               ↓
                                       recovery_node   [pass/fail]
                                                            ↓
                                                       report_node → END
```

| Node | Type | Responsibility |
|------|------|---------------|
| `planner_node` | LLM | Decides analysis strategy (full vs lightweight) |
| `evidence_node` | Deterministic | Runs all tools, auto-clones repo, tracks provenance |
| `scoring_node` | Deterministic | Computes health score from collected signals |
| `critic_node` | LLM | Validates consistency, flags suspicious results |
| `recovery_node` | Deterministic | Degrades confidence, increments retry count |
| `report_node` | LLM | Synthesizes grounded final report (no hallucination) |

---

## Project Structure

```
app/
├── core/               V1 pipeline foundations
│   ├── pipeline.py         orchestrates GitHub → deps → freshness → OSV → score
│   ├── risk_scoring.py     weighted scoring (activity 30% / deps 40% / security 30%)
│   ├── models.py           frozen dataclasses (RepoMetrics, DependencyMetrics, etc.)
│   ├── github_client.py    GitHub API calls
│   ├── dependency_parser.py  requirements.txt / pyproject.toml parser
│   ├── dependency_freshness.py  version-aware outdated detection
│   ├── vulnerability_scanner.py  OSV batch security scan
│   └── retry.py            exponential backoff with jitter
├── analysis/           Phase 2 differentiator tools
│   ├── deprecated_api_scanner.py  AST scanner for deprecated symbols
│   ├── changelog_analyzer.py      regex parser for breaking changes
│   ├── release_notes_fetcher.py   fetch GitHub releases or PyPI descriptions
│   └── migration_planner.py       ordered migration steps from findings
├── agents/             LangGraph multi-agent system
│   ├── graph.py             StateGraph + conditional edges + run_graph()
│   ├── state.py             VersionPilotState TypedDict
│   ├── planner_node.py
│   ├── evidence_node.py
│   ├── scoring_node.py
│   ├── critic_node.py
│   ├── recovery_node.py
│   ├── report_node.py
│   └── llm_client.py        Claude (Vertex AI) + Gemini fallback
├── tools/              LangGraph tool wrappers
│   ├── tool_registry.py     wraps all modules as callable tools + clone_repo
│   └── rules_extractor.py   LLM extracts deprecation rules from release notes
└── main.py             CLI entry point

config/
  scoring_v1.yaml       scoring weights and thresholds

data/
  deprecation_rules.json  static fallback deprecation rules
  benchmark_repos.txt

eval/
  run_eval.py           batch evaluation runner

tests/
  unit/                 26 test files
  integration/
```

---

## How To Run

### Setup

```bash
python -m venv vpilot
source vpilot/bin/activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in:

```
GITHUB_TOKEN=...             # required for all modes
GOOGLE_CLOUD_PROJECT=...     # required for agent mode (Vertex AI)
CLOUD_ML_REGION=us-east5
GOOGLE_API_KEY=...           # Gemini fallback
```

For Vertex AI auth: `gcloud auth application-default login`

### Basic mode (no LLM required)

```bash
python -m app.main https://github.com/psf/requests --mode basic --json
```

### Agent mode (LangGraph + LLM)

```bash
# Auto-clones the repo for deprecated API scanning
python -m app.main https://github.com/psf/requests --mode agent --json

# Or provide a local path to skip the clone
python -m app.main https://github.com/psf/requests --mode agent --repo-path /path/to/requests --json
```

### Other options

```bash
--config config/scoring_v1.yaml   # scoring config (default)
--output report.json              # save to file (default: artifacts/<run_id>.json)
--force                           # recompute even if artifact exists
--json                            # print JSON to stdout
```

### Batch evaluation

```bash
python -m eval.run_eval --repos-file data/benchmark_repos.txt --output eval/eval_report.json
```

---

## Testing

```bash
vpilot/bin/python -m pytest tests/ -v        # all 176 tests
vpilot/bin/python -m pytest tests/unit/ -v   # unit only
```

---

## LLM Configuration

Claude is accessed via **Google Cloud Vertex AI**. Gemini is used as a fallback when Claude quota is exceeded.

Call order in `app/agents/llm_client.py`:
1. Claude Sonnet 4.6 via `anthropic.AnthropicVertex`
2. Gemini Flash via `langchain-google-genai` (fallback on quota/rate-limit errors)

All LLM nodes have deterministic fallbacks — agent mode degrades gracefully when credentials are unavailable.

---

## Health Report Output

```json
{
  "summary": "...",
  "health_score": 78.4,
  "risk_level": "medium",
  "key_findings": [
    {"finding": "...", "evidence": "...", "severity": "high"}
  ],
  "migration_recommendations": [
    {"action": "...", "priority": "high", "reason": "..."}
  ],
  "data_quality": {
    "completeness": 0.95,
    "confidence": 0.88,
    "failed_steps": []
  }
}
```

---

## Known Limitations

- `dependency_parser` only handles `requirements.txt` and `pyproject.toml`. Repos using `setup.py`/`setup.cfg` will have 0 dependencies parsed.
- Release notes are fetched for the **latest PyPI version**, not the version pinned in requirements. Deprecation findings may include symbols not relevant until the user actually upgrades.
- Auto-clone uses `--depth=1` (sufficient for AST scanning, no full git history).
- npm / non-Python ecosystems not yet supported.
