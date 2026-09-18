# ADR 0005: Recorded model responses make the CI gate free and deterministic

Status: accepted · 2026-09-18

## Context

Every change to a prompt, the schema compiler, a matcher or the importer can move accuracy, and the
only trustworthy check is to re-score. Calling a model from CI would cost money on every push,
depend on a secret, and vary between runs.

## Decision

The cassette provider records each model response under a key made of what the request was built
from — document id, prompt version, schema version, model, effort, OCR-text flag, few-shot example
ids, and a hash of the rendered system prompt and output schema — not of the request bytes. CI
loads a committed bundle of 20 labelled test receipts (downscaled images, OCR spans, golden labels),
replays the recordings for one configuration, re-scores them and fails when any field's accuracy,
the value accuracy, the document exact-match rate or a list's exact rate drops more than two points
below `evals/baseline.json`. `fieldwise gate run --write` refreshes the baseline deliberately.

## Consequences

- A prompt or schema change misses the cassettes (the system-prompt hash changed) and the gate
  reports "nothing was scored" — the change must be recorded and the baseline rewritten in the same
  pull request, which is the point: numbers travel with the change.
- Grader and importer changes replay for free: the v1 re-score after the parser fix cost nothing.
- Truncated answers are never recorded, so a re-run retries them instead of replaying a failure.
