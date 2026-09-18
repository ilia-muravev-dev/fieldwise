# ADR 0001: Build the eval harness before the UI

Status: accepted · 2026-09-18

## Context

An extraction product lives or dies by accuracy, and accuracy is only real when it is measured the
same way every time. On a previous pipeline the numbers that mattered — field accuracy on a fixed
golden set, cost per document, latency — came from a script that ran after every prompt or schema
change; the review UI mattered for the humans, the eval mattered for the engineering.

## Decision

The order of work is: schema + golden labels → OCR → extraction → **eval runner and report** →
prompt iterations (each measured) → API/worker → web UI. The README's tables are copied from the
reports the runner writes into `docs/evals/`, never typed by hand. CI replays recorded responses
(cassettes) for a 20-document subset and fails when a field regresses by more than two points.

## Consequences

- Prompt versions v1 → v4 are separate pull requests with their measured deltas in the description.
- The UI shows the same numbers the CLI computes (both read `eval_runs`), so there is one truth.
- Recorded cassettes make the CI gate free, at the cost of a re-record whenever the prompt changes.
