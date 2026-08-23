"""Append cleaned reviews to the shared CSV, skipping ones already saved."""

from __future__ import annotations

import csv
from pathlib import Path

FIELDNAMES = ["reviewer", "rating", "review_text", "date", "source_url"]


def _dedup_key(review: dict) -> tuple:
    # CSV round-trips missing values as "" (never None), so normalize here
    # too or every review missing a date/reviewer would look "new" every run.
    return (review.get("reviewer") or "", review.get("date") or "", review.get("review_text") or "")


def _existing_keys(csv_path: Path) -> set[tuple]:
    if not csv_path.exists():
        return set()
    with csv_path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return {_dedup_key(row) for row in reader}


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
            key = _dedup_key(review)
            if key in existing:
                continue
            existing.add(key)
            writer.writerow({field: review.get(field, "") for field in FIELDNAMES})
            written += 1

    return written
