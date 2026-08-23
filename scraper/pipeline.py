"""Ties scraping, LLM filtering, and CSV storage together."""

from __future__ import annotations

from pathlib import Path

from scraper import appstore, csv_store, manual, web
from scraper.llm_client import filter_and_extract


def _finish(
    raw_items: list[dict],
    source_url: str,
    csv_path: Path,
    provider: str | None,
    model: str | None,
) -> int:
    print(f"Found {len(raw_items)} raw candidate(s). Sending to the LLM for filtering/extraction...")
    if not raw_items:
        return 0

    cleaned = filter_and_extract(raw_items, provider_name=provider, model=model)
    print(f"LLM kept {len(cleaned)} of {len(raw_items)} candidate(s) as genuine English reviews.")

    for review in cleaned:
        review.setdefault("source_url", source_url)

    written = csv_store.append_reviews(cleaned, csv_path)
    print(f"Wrote {written} new row(s) to {csv_path} ({len(cleaned) - written} were already present).")
    return written


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
        try:
            raw_items = web.scrape_reviews(url)
        except web.BlockedError:
            print(
                f"This site is blocking automated access (even a real headless browser), so we're "
                f"stopping here rather than trying to bypass its bot protection. Copy the review text "
                f"yourself into a .txt file (reviews separated by a line containing only '---') and run:\n"
                f'  uv run main.py --from-file <path-to-file> --source-url "{url}"'
            )
            return 0

    return _finish(raw_items, url, csv_path, provider, model)


def run_from_file(
    path: Path,
    csv_path: Path,
    source_url: str | None = None,
    provider: str | None = None,
    model: str | None = None,
) -> int:
    """Load manually pasted reviews from `path` and run them through the same
    LLM filter + CSV pipeline as a scrape. Returns the number of new rows written.
    """
    print(f"Loading manually pasted reviews from {path}...")
    raw_items = manual.load_candidates(path)
    return _finish(raw_items, source_url or "", csv_path, provider, model)
