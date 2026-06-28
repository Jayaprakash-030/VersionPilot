# VersionPilot Evaluation Report

## Status

This is the current evaluation snapshot for VersionPilot. It records completed
baseline results and keeps unfinished evaluations explicit rather than implying
the project is fully evaluated.

## Summary

| Evaluation | Status | Result |
|---|---|---:|
| Deprecated API scanner fixtures | Complete baseline | 29 / 30 fixtures passed |
| Rules extraction fixtures | Complete multi-run baseline | 48 / 48 runs passed |
| Scoring behavior checks | Complete baseline | 15 / 15 checks passed |
| Controlled migration cases | Partial baseline | 3 / 3 cases passed |
| Reliability scenarios | Partial baseline | 10 / 10 scenarios passed |

## Deprecated API Scanner

Command:

```bash
vpilot/bin/python -m eval.evaluate_scanner eval/fixtures/deprecated_api
```

Result:

| Metric | Value |
|---|---:|
| Fixtures | 30 |
| Passed fixtures | 29 |
| True positives | 29 |
| False positives | 0 |
| False negatives | 1 |
| Precision | 1.0000 |
| Recall | 0.9667 |
| F1 | 0.9831 |
| Exact line-location accuracy | 1.0000 |

Known failure:

| Fixture | Issue |
|---|---|
| `wildcard_import_usage` | Scanner does not resolve deprecated symbols introduced only through wildcard imports, such as `from flask import *`. This is documented as a current limitation because wildcard imports obscure symbol provenance and are discouraged in production Python code. |

## Rules Extraction

Command:

```bash
vpilot/bin/python -m eval.evaluate_rules_extractor \
  eval/fixtures/rules_extractor \
  --output eval/rules_extractor_report.json
```

Model configuration:

```text
Provider: OpenAI
Default model: gpt-5.4-nano
Runs per fixture: 3
```

Result:

| Metric | Value |
|---|---:|
| Fixtures | 16 |
| Runs | 48 |
| Passed fixtures | 16 |
| Passed runs | 48 |
| Consistent fixtures | 16 |
| Consistency rate | 1.0000 |
| Valid schema rate | 1.0000 |
| Correct empty-result rate | 1.0000 |
| Symbol precision | 1.0000 |
| Symbol recall | 1.0000 |
| Symbol F1 | 1.0000 |
| Replacement accuracy | 1.0000 |
| Severity accuracy | 1.0000 |

Notes:

- The initial OpenAI run exposed one severity mismatch in `long_noisy_notes`.
- The system prompt was updated to distinguish current removals from future
  removals: current removed or breaking APIs are `high`; deprecated APIs that
  warn or will be removed later are `medium`.
- After that prompt update, the full single-run fixture suite passed.
- A later three-run consistency evaluation also passed all 48 runs with no
  inconsistent fixtures.

## Scoring Behavior

Command:

```bash
vpilot/bin/python -m eval.evaluate_scoring
```

Result:

| Metric | Value |
|---|---:|
| Behavioral checks passed | 15 / 15 |
| Misleading verified-Low results under failure | 0 |

The scoring checks cover monotonicity, dominance, determinism, and trust
policies for incomplete or failed evidence collection.

## Controlled Migration Cases

Command:

```bash
vpilot/bin/python -m eval.evaluate_migrations \
  eval/fixtures/migration_cases \
  --output eval/migration_report.json
```

Result:

| Metric | Value |
|---|---:|
| Cases | 3 |
| Passed cases | 3 |
| Issues detected | 3 |
| Correct file/line results | 3 |
| Useful recommendations | 3 |

Case details:

| Case | Issue Detected | Correct File/Line | Useful Recommendation |
|---|---:|---:|---:|
| `flask_removed_escape` | Yes | Yes | Yes |
| `requests_vendored_urllib3` | Yes | Yes | Yes |
| `numpy_deprecated_bool_alias` | Yes | Yes | Yes |

Each case runs release notes through rules extraction, scans a small fixture
project, and checks that the migration planner recommends the expected
replacement.

## Reliability Scenarios

Command:

```bash
vpilot/bin/python -m eval.evaluate_reliability \
  --output eval/reliability_report.json
```

Result:

| Metric | Value |
|---|---:|
| Scenarios | 10 |
| Passed scenarios | 10 |
| Misleading successful migration results | 0 |
| Misleading verified-Low results | 0 |

Covered scenarios:

| Scenario | Report Generated | Marked Successful | Reliability Check |
|---|---:|---:|---:|
| Rules extractor unavailable | Yes | No | Passed |
| Rules extractor malformed JSON | Yes | No | Passed |
| Report LLM invalid JSON | Yes | No | Passed |
| Critic rejected report | Yes | No | Passed |
| GitHub metadata failure | Yes | No | Passed |
| Dependency parser failure | Yes | No | Passed |
| Dependency freshness failure | Yes | No | Passed |
| Vulnerability scanner failure | Yes | No | Passed |
| V1 pipeline failure | Yes | No | Passed |
| Repository clone failure | Yes | No | Passed |

These scenarios verify that rules-extraction failures still produce evaluable
output but do not get reported as successful controlled migrations. They also
verify that invalid report-LLM output falls back to a deterministic template
while preserving factual fields such as risk level, health score, completeness,
and confidence. Critic rejection is published as `Unverified` rather than a
verified risk level. Critical evidence failures are published as `Unknown`
instead of verified `Low`, even when the computed health score is high. Clone
failure is recorded as a failed step and the deprecated API scan is marked
incomplete for migration analysis.

## Pending Evaluations

The following work is still required before calling the evaluation complete:

1. Add additional controlled migration cases and include post-migration test
   execution where practical.
2. Run real-repository smoke tests and record completion status, risk level,
   data completeness, findings, recommendations, and runtime.

## Current Limitations

- Scanner accuracy is measured with manually verified rules, which isolates the
  scanner but does not by itself prove end-to-end migration quality.
- The deprecated API scanner does not currently handle wildcard imports. This
  can miss usages where the deprecated symbol is introduced by `from package
  import *` and then called by bare name.
- Controlled migration coverage currently has three cases.
- Reliability coverage includes rules extraction, report LLM, critic rejection,
  clone failure, and critical deterministic evidence failures.
