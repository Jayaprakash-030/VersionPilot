# VersionPilot Model Card

## System Overview

VersionPilot is an AI-assisted dependency health and migration analysis system
for Python repositories. It combines deterministic repository analysis with LLM
orchestration to answer:

```text
What will break in this repository, where is the affected code, and what is the
migration path?
```

The current approved baseline is recorded in
`config/model_registry.json` as `phase4_baseline`.

## Approved Baseline

| Field | Value |
|---|---|
| System version | `phase4_baseline` |
| Status | `approved` |
| Promoted at | `2026-06-28` |
| Scoring config | `config/scoring_v1.yaml` |
| LLM provider | OpenAI |
| Default model | `gpt-5.4-nano` |
| Evaluation report | `eval/EVAL_REPORT.md` |

Promotion is checked with:

```bash
vpilot/bin/python -m pipelines.promote_model
```

## Intended Use

VersionPilot is intended for developer-facing dependency maintenance workflows:

- summarize repository dependency health
- identify actively used deprecated Python APIs
- connect release-note changes to affected source lines
- produce migration steps that can be reviewed and tested by a developer
- flag incomplete evidence and degraded confidence when external systems fail

It is a decision-support tool. It should assist code review and migration
planning, not automatically upgrade production applications without human
review.

## Inputs

VersionPilot may use:

- GitHub repository metadata
- Python dependency manifests, currently nested `requirements.txt` and
  `pyproject.toml`
- dependency freshness data
- OSV vulnerability data
- repository source code for AST scanning
- release notes from GitHub releases or PyPI metadata
- dynamic deprecation rules extracted from release notes by the LLM
- versioned scoring configuration from `config/scoring_v1.yaml`

## Outputs

The system produces a health report containing:

- health score
- risk level
- component score breakdown
- key findings
- deprecated API findings with file and line evidence
- migration recommendations
- data completeness
- confidence score
- failed evidence steps
- final natural-language report in agent mode

## System Components

### Deterministic Components

These parts are expected to be reproducible for the same input data and config:

- GitHub metadata collection
- dependency manifest discovery and parsing
- dependency freshness checks
- OSV vulnerability lookup
- deprecated API AST scanning
- changelog regex analysis
- migration step construction from findings
- health scoring from `config/scoring_v1.yaml`
- confidence and completeness degradation on known failures
- promotion-gate validation

### LLM Components

These parts use the configured OpenAI model:

- planner node: chooses analysis strategy
- rules extractor: converts release notes into structured deprecation rules
- critic node: checks report consistency and trustworthiness
- report node: synthesizes the final grounded report

LLM outputs are constrained by schema checks, deterministic fallbacks, and
reliability tests. LLM-generated claims should remain grounded in evidence
collected by deterministic tools.

## Evaluation Summary

The approved baseline is supported by `eval/EVAL_REPORT.md`.

| Evaluation | Result |
|---|---:|
| Deprecated API scanner fixtures | 29 / 30 fixtures passed |
| Rules extraction fixtures | 48 / 48 live runs passed |
| Scoring behavior checks | 15 / 15 checks passed |
| Controlled migration cases | 3 / 3 cases passed |
| Post-migration tests | 3 / 3 tests passed |
| Reliability scenarios | 10 / 10 scenarios passed |
| Basic real-repository smoke runs | 5 / 5 runs completed |
| Agent-mode smoke runs | 1 / 1 run completed |

Key measured properties:

- Scanner precision: `1.0000`
- Scanner recall: `0.9667`
- Scanner F1: `0.9831`
- Scanner exact line-location accuracy: `1.0000`
- Rules extractor symbol F1: `1.0000`
- Rules extractor valid schema rate: `1.0000`
- Misleading successful migration results under reliability tests: `0`
- Misleading verified-Low results under reliability tests: `0`

## Promotion Policy

A baseline is considered promotable only when:

- the registry points to the approved scoring config and LLM baseline
- rules extraction report meets the current fixture/run baseline
- controlled migration report meets the current pass baseline
- reliability report has no misleading success or verified-Low failures
- focused evaluation unit tests pass

The current promotion gate is implemented in `pipelines/promote_model.py`.

## Known Limitations

- The project is currently Python-focused.
- Dependency discovery searches nested `requirements.txt` and `pyproject.toml`
  files, but does not parse `setup.py`, `setup.cfg`, `Pipfile`, lockfiles, or
  non-Python manifests.
- Release notes are fetched for the latest available package version, not the
  full release-note range between the pinned version and latest version.
- Deprecated API scanning does not resolve symbols introduced only through
  wildcard imports such as `from package import *`.
- Scanner accuracy uses manually verified rules, so it measures scanner behavior
  separately from live rules extraction.
- Controlled migration coverage currently contains three representative cases.
- Real-repository smoke runs are completion checks, not labeled accuracy
  benchmarks.
- LLM behavior may vary across providers, model versions, prompts, and API
  availability.

## Not Intended For

VersionPilot should not be used as:

- an automatic production upgrade system without developer review
- a security compliance certification tool
- a full substitute for package maintainers' migration guides
- a complete vulnerability management platform
- a multi-language dependency migration system in its current form

## Reliability And Fallback Behavior

When critical evidence is missing, VersionPilot should avoid publishing
overconfident healthy results. Reliability scenarios currently verify that:

- rules-extraction failures do not appear as successful migrations
- invalid report-LLM output falls back to a deterministic report template
- critic rejection produces `Unverified`
- critical evidence failures produce `Unknown`, not verified `Low`
- repository clone failure is recorded as failed evidence

## Maintenance Notes

Future changes to scoring weights, prompts, LLM model choice, scanner behavior,
or migration logic should be evaluated before promotion. If the change is
intended to become the new approved baseline:

1. regenerate the relevant evaluation artifacts
2. update `eval/EVAL_REPORT.md`
3. update `config/model_registry.json`
4. run `vpilot/bin/python -m pipelines.promote_model`
5. update this model card if the baseline, metrics, or limitations changed
