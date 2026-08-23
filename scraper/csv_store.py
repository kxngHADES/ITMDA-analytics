"""Append cleaned reviews to the shared CSV, skipping ones already saved."""

from __future__ import annotations

import csv
from pathlib import Path

FIELDNAMES = ["reviewer", "rating", "review_text", "date", "source_url"]


def _existing_keys(csv_path: Path) -> set[tuple]:
    if not csv_path.exists():
        return set()
    with csv_path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return {(row.get("reviewer"), row.get("date"), row.get("review_text")) for row in reader}


def append_reviews(reviews: list[dict], csv_path: Path) -> int:
    """Append `reviews` to `csv_path`, creating it with a header if needed.

    Returns the number of rows actually written (duplicates of existing
    reviewer+date+review_text rows are skipped so re-running the scraper on
    the same URL doesn't create duplicate CSV rows).
    """
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    existing = _existing_keys(csv_path)
    write_header = not csv_path.exists() or csv_path.stat().st_size == 0

    written = 0
    with csv_path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if write_header:
            writer.writeheader()

        for review in reviews:
            key = (review.get("reviewer"), review.get("date"), review.get("review_text"))
            if key in existing:
                continue
            existing.add(key)
            writer.writerow({field: review.get(field, "") for field in FIELDNAMES})
            written += 1

    return written
