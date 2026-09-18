# ADR 0004: The few-shot pool never contains the test split

Status: accepted · 2026-09-18

## Context

Prompt v3 puts the most similar labelled receipts, with their golden output, in front of the
document to extract. Retrieval is by cosine distance between OCR-text embeddings (fastembed,
`BAAI/bge-small-en-v1.5`, on the CPU, stored in a pgvector column). If the pool included the test
split, a test receipt could retrieve itself or a near-duplicate with its answer attached, and the
eval would measure memorisation.

## Decision

The exclusion is in the query (`Document.split NOT IN ('test')` or `split IS NULL`), not in the
caller's discipline, and the document being extracted is always excluded by id. Uploaded documents
with a reviewer's correction are eligible: they are exactly the examples a team accumulates in
production. An integration test asserts that a test document's identical twin in the test split is
never returned while its near-identical validation neighbour is.

## Consequences

- The eval set is 100 receipts; the example pool is the 100 validation receipts (plus train if
  imported, plus corrections). Retrieval quality is bounded by that pool.
- Few-shot examples are text only (OCR text + JSON). Sending example images would triple the image
  tokens per request for a gain the eval can measure later if wanted.
- The cassette key includes the example ids, so a change in the pool re-records rather than replays.
