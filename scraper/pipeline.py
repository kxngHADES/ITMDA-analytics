"""Ties scraping, LLM filtering, and CSV storage together."""

from __future__ import annotations

from pathlib import Path

from scraper import appstore, csv_store, web
from scraper.llm_client import filter_and_extract


def run(
    url: str,
    csv_path: Path,
    provider: str | None = None,
    model: str | None = None,
    countries: list[str] | None = None,
) -> int:
    """Scrape `url`, run results through the LLM filter, append to `csv_path`.

    Returns the number of new rows written.
    """
    if appstore.is_appstore_url(url):
        print(f"Detected Apple App Store URL. Fetching reviews for app id {appstore.extract_app_id(url)}...")
        raw_items = appstore.fetch_reviews(url, countries=countries)
    else:
        print(f"Scraping generic review page: {url}")
        raw_items = web.scrape_reviews(url)

    print(f"Found {len(raw_items)} raw candidate(s). Sending to the LLM for filtering/extraction...")
    if not raw_items:
        return 0

    cleaned = filter_and_extract(raw_items, provider_name=provider, model=model)
    print(f"LLM kept {len(cleaned)} of {len(raw_items)} candidate(s) as genuine English reviews.")

    for review in cleaned:
        review.setdefault("source_url", url)

    written = csv_store.append_reviews(cleaned, csv_path)
    print(f"Wrote {written} new row(s) to {csv_path} ({len(cleaned) - written} were already present).")
    return written
