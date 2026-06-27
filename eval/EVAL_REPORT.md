# VersionPilot Evaluation Report

## Status

This is the current evaluation snapshot for VersionPilot. It records completed
baseline results and keeps unfinished evaluations explicit rather than implying
the project is fully evaluated.

## Summary

| Evaluation | Status | Result |
|---|---|---:|
| Deprecated API scanner fixtures | Complete baseline | 29 / 30 fixtures passed |
| Rules extraction fixtures | Complete single-run baseline | 16 / 16 fixtures passed |
| Scoring behavior checks | Complete baseline | 15 / 15 checks passed |
| Controlled migration cases | Pending | Not yet implemented |
| Reliability scenarios | Pending | Not yet implemented |

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
| `wildcard_import_usage` | Scanner does not currently resolve deprecated symbols introduced through wildcard imports. |

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
Runs per fixture: 1
```

Result:

| Metric | Value |
|---|---:|
| Fixtures | 16 |
| Runs | 16 |
| Passed fixtures | 16 |
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

## Pending Evaluations

The following work is still required before calling the evaluation complete:

1. Run rules extraction with multiple live attempts per fixture and record
   consistency.
2. Decide whether to fix or explicitly document wildcard-import scanner
   behavior.
3. Build controlled migration cases that connect release notes, extracted
   rules, source-code findings, recommendations, and post-migration tests.
4. Implement reliability scenarios for GitHub, dependency parsing, OSV, clone,
   LLM, and critic failures.
5. Run real-repository smoke tests and record completion status, risk level,
   data completeness, findings, recommendations, and runtime.

## Current Limitations

- Rules extraction has only a single-run live baseline so far. Multi-run
  consistency is not yet measured.
- Scanner accuracy is measured with manually verified rules, which isolates the
  scanner but does not by itself prove end-to-end migration quality.
- The deprecated API scanner does not currently handle wildcard imports.
- Controlled migration and reliability evaluations are still pending.
