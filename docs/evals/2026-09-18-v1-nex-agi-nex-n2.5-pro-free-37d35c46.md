# Eval 37d35c46 — v1 / nex-agi/nex-n2.5-pro:free

prompt **v1** · model `nex-agi/nex-n2.5-pro:free` · effort low · few-shot k=0 · OCR text off · provider openrouter · split test · 20 docs x 1 rep(s) · mode sync

Run at 2026-09-18 13:58 UTC · v1 baseline, free model, reasoning effort low

## Summary

| Metric | Value |
| --- | ---: |
| Field accuracy (strict, every leaf) | 83.4% |
| Value accuracy (leaves with a golden value) | 85.1% |
| Field accuracy (lenient: fuzzy text counts) | 84.5% |
| Documents fully correct | 31.6% |
| Extractions succeeded / truncated / failed | 19 / 1 / 0 |
| Cost total / per document | $0.0000 / $0.0000 |
| Latency p50 / p95 | 29585 ms / 124146 ms |

## Per field

| Field | Matcher | n | Accuracy | 95% CI | Value acc. (n) | wrong | missing | spurious |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `tax` | money | 19 | 84.2% | 62-94 | 62.5% (8) | 3 | 0 | 0 |
| `total` | money | 19 | 73.7% | 51-88 | 72.2% (18) | 4 | 1 | 0 |
| `change` | money | 19 | 100.0% | 83-100 | 100.0% (11) | 0 | 0 | 0 |
| `discount` | money | 19 | 89.5% | 69-97 | 66.7% (3) | 1 | 0 | 1 |
| `subtotal` | money | 19 | 78.9% | 57-91 | 76.9% (13) | 3 | 0 | 1 |
| `card_paid` | money | 19 | 94.7% | 75-99 | 75.0% (4) | 1 | 0 | 0 |
| `cash_paid` | money | 19 | 84.2% | 62-94 | 78.6% (14) | 3 | 0 | 0 |
| `item_count` | integer | 19 | 100.0% | 83-100 | 100.0% (4) | 0 | 0 | 0 |
| `line_items[].name` | text | 46 | 73.9% | 60-84 | 85.0% (40) | 2 | 0 | 6 |
| `line_items[].quantity` | integer | 46 | 87.0% | 74-94 | 100.0% (40) | 0 | 0 | 6 |
| `line_items[].line_total` | money | 46 | 69.6% | 55-81 | 84.2% (38) | 6 | 0 | 8 |
| `line_items[].unit_price` | money | 46 | 80.4% | 67-89 | 75.0% (8) | 2 | 0 | 7 |
| `service_charge` | money | 19 | 100.0% | 83-100 | 100.0% (1) | 0 | 0 | 0 |

## Lists

| List | Docs | Exact match | 95% CI | Item precision | Item recall | Items (golden / predicted) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `line_items` | 19 | 36.8% | 19-59 | 60.9% | 70.0% | 40 / 46 |

## Not scored (infrastructure or output failures)

- `cord-v2/test/0002` — truncated: stop_reason=max_tokens
