# ADR 0003: How extractions are graded

Status: accepted · 2026-09-18

## Context

Field-level accuracy on receipts is easy to inflate and easy to misread. Most schema fields are
absent on most receipts (no service charge, no card payment), so "predicted null, golden null"
agreements dominate a naive per-field number. Infrastructure failures — a rate-limited provider, a
response cut off at `max_tokens`, output that fails schema validation — look like wrong answers if
they land in the same column as model mistakes. And exact string comparison punishes harmless
differences ("NASI GORENG" vs "Nasi Goreng", "45,500" vs 45500).

## Decision

- Every leaf gets one of six outcomes: `correct`, `null_match` (both null), `fuzzy` (text ≥ 90
  similarity after normalisation), `wrong`, `missing` (golden has a value, prediction is null),
  `spurious` (the reverse). Lists are aligned by position; an item counts as matched only when all
  its fields are correct; lists report an exact-match rate and item precision/recall.
- Two headline numbers are always shown side by side: **strict field accuracy** (`correct` +
  `null_match` over every graded leaf — comparable across prompt versions) and **value accuracy**
  (`correct` over leaves whose golden has a value — what the null baseline cannot inflate).
  Document exact-match rate is the third.
- Money values are compared as decimals after the same normalisation the importer applied to the
  ground truth; text is case-folded and whitespace/punctuation-normalised; fuzzy matches are counted
  as wrong in the strict number and reported separately.
- `failed` and `truncated` extractions are listed in an error sidecar with their cause and are never
  part of an accuracy denominator. Cost is summed from the usage each response reported; latency is
  the final request's, sync mode only.
- The grader is checked by construction: an oracle run (golden echoed back) must score 100%, a null
  baseline must score 0% value accuracy, and a plausible-but-wrong receipt must fail.

## Consequences

- Reports can say "value accuracy 71%" next to "strict 86%" without either being a lie.
- A prompt change that only improves null handling moves the strict number, not the value number,
  and the per-field `spurious`/`missing` counts show which.
- Provider outages show up as a smaller `n`, not as a worse model.
