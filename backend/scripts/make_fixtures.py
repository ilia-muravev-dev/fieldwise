"""Copies a few CORD v2 validation receipts into tests/fixtures/cord (downscaled) so unit tests
can exercise OCR, prompts and matchers on real receipts without the dataset.

Usage: uv run python scripts/make_fixtures.py
"""

import json
from pathlib import Path

from fieldwise.documents.cord_import import download_split, iter_rows
from fieldwise.documents.render import downscale_jpeg

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "cord"
WANTED = 3
MAX_EDGE = 900


def main() -> None:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    picked = 0
    for row in iter_rows("validation", download_split("validation")):
        menu = row.gt_parse.get("menu")
        items = menu if isinstance(menu, list) else [menu] if menu else []
        # Prefer receipts with a few line items and a total, so the fixture is representative.
        if len(items) < 2 or not row.gt_parse.get("total", {}).get("total_price"):
            continue
        stem = row.external_id.replace("/", "_")
        (FIXTURE_DIR / f"{stem}.jpg").write_bytes(downscale_jpeg(row.image, MAX_EDGE, quality=80))
        (FIXTURE_DIR / f"{stem}.json").write_text(
            json.dumps(row.gt_parse, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        picked += 1
        if picked == WANTED:
            break
    print(f"wrote {picked} fixtures to {FIXTURE_DIR}")


if __name__ == "__main__":
    main()
