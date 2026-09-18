# Eval 894681a4 — v2 / nex-agi/nex-n2.5-pro:free

prompt **v2** · model `nex-agi/nex-n2.5-pro:free` · effort low · few-shot k=0 · OCR text on · provider openrouter · split test · 20 docs x 1 rep(s) · mode sync

Run at 2026-09-18 14:25 UTC · v2: OCR text + normalisation rules

## Summary

| Metric | Value |
| --- | ---: |
| Field accuracy (strict, every leaf) | 91.1% |
| Value accuracy (leaves with a golden value) | 95.1% |
| Field accuracy (lenient: fuzzy text counts) | 91.7% |
| Documents fully correct | 50.0% |
| Extractions succeeded / truncated / failed | 18 / 0 / 2 |
| Cost total / per document | $0.0000 / $0.0000 |
| Latency p50 / p95 | 23214 ms / 80562 ms |

## Per field

| Field | Matcher | n | Accuracy | 95% CI | Value acc. (n) | wrong | missing | spurious |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `tax` | money | 18 | 100.0% | 82-100 | 100.0% (8) | 0 | 0 | 0 |
| `total` | money | 18 | 94.4% | 74-99 | 94.1% (17) | 0 | 1 | 0 |
| `change` | money | 18 | 94.4% | 74-99 | 90.9% (11) | 1 | 0 | 0 |
| `discount` | money | 18 | 94.4% | 74-99 | 100.0% (2) | 0 | 0 | 1 |
| `subtotal` | money | 18 | 88.9% | 67-97 | 91.7% (12) | 1 | 0 | 1 |
| `card_paid` | money | 18 | 100.0% | 82-100 | 100.0% (3) | 0 | 0 | 0 |
| `cash_paid` | money | 18 | 100.0% | 82-100 | 100.0% (14) | 0 | 0 | 0 |
| `item_count` | integer | 18 | 100.0% | 82-100 | 100.0% (4) | 0 | 0 | 0 |
| `line_items[].name` | text | 38 | 81.6% | 67-91 | 91.2% (34) | 1 | 0 | 4 |
| `line_items[].quantity` | integer | 38 | 89.5% | 76-96 | 100.0% (34) | 0 | 0 | 4 |
| `line_items[].line_total` | money | 38 | 84.2% | 70-93 | 94.1% (34) | 2 | 0 | 4 |
| `line_items[].unit_price` | money | 38 | 84.2% | 70-93 | 87.5% (8) | 1 | 0 | 5 |
| `service_charge` | money | 18 | 100.0% | 82-100 | 100.0% (1) | 0 | 0 | 0 |

## Lists

| List | Docs | Exact match | 95% CI | Item precision | Item recall | Items (golden / predicted) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `line_items` | 18 | 66.7% | 44-84 | 76.3% | 85.3% | 34 / 38 |

## Not scored (infrastructure or output failures)

- `cord-v2/test/0002` — failed: rate_limit: Error code: 429 - {'error': {'message': 'Rate limit exceeded: free-models-per-day. Add 10 credits to unlock 1000 free model requests per day', 'code': 429, 'metadata': {'headers': {'X-Rate
- `cord-v2/test/0017` — failed: rate_limit: Error code: 429 - {'error': {'message': 'Rate limit exceeded: free-models-per-day. Add 10 credits to unlock 1000 free model requests per day', 'code': 429, 'metadata': {'headers': {'X-Rate
