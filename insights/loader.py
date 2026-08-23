"""Loads the scraped reviews CSV for analysis."""

from __future__ import annotations

import csv
from pathlib import Path


def load_reviews(csv_path: Path) -> list[dict]:
    with csv_path.open("r", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return [row for row in rows if row.get("review_text", "").strip()]
