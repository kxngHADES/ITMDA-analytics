"""Best-effort generic scraper for review websites (non-App Store).

Review page markup varies a lot from site to site, so instead of hardcoding
CSS selectors per site, this pulls out every element that *looks* like a
review container (via common class/attribute naming, or schema.org Review
markup) and hands the raw text to the LLM to decide what's actually a
review and to extract the structured fields.
"""

from __future__ import annotations

import re

import requests
from bs4 import BeautifulSoup

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
REQUEST_TIMEOUT = 20
MIN_TEXT_LEN = 20
MAX_TEXT_LEN = 3000
MAX_CANDIDATES = 200

REVIEW_HINT_RE = re.compile(r"review|comment|feedback|rating", re.IGNORECASE)


def fetch_html(url: str) -> str:
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.text


def _looks_like_review_container(tag) -> bool:
    attrs = " ".join(
        [
            tag.get("class") and " ".join(tag.get("class")) or "",
            tag.get("id") or "",
            tag.get("itemprop") or "",
            tag.get("itemtype") or "",
            tag.get("data-testid") or "",
        ]
    )
    return bool(REVIEW_HINT_RE.search(attrs))


def _leaf_candidates(soup: BeautifulSoup) -> list:
    """Find review-hinted elements, keeping only the innermost matches so we
    don't grab a whole review list and each individual review as separate,
    overlapping candidates."""
    matches = [tag for tag in soup.find_all(True) if _looks_like_review_container(tag)]
    leafy = []
    for tag in matches:
        if not any(child in matches for child in tag.find_all(True)):
            leafy.append(tag)
    return leafy


def extract_candidates(html: str) -> list[str]:
    """Return a list of raw text blocks that might be reviews."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    candidates = _leaf_candidates(soup)
    texts: list[str] = []
    seen: set[str] = set()

    for tag in candidates:
        text = " ".join(tag.get_text(separator=" ", strip=True).split())
        if MIN_TEXT_LEN <= len(text) <= MAX_TEXT_LEN and text not in seen:
            seen.add(text)
            texts.append(text)

    if not texts:
        # Fallback: no review-hinted markup found — try paragraph-sized blocks
        # of body text and let the LLM sort the wheat from the chaff.
        for tag in soup.find_all(["p", "li", "article", "div"]):
            text = " ".join(tag.get_text(separator=" ", strip=True).split())
            if MIN_TEXT_LEN <= len(text) <= MAX_TEXT_LEN and text not in seen:
                seen.add(text)
                texts.append(text)

    return texts[:MAX_CANDIDATES]


def scrape_reviews(url: str) -> list[dict]:
    """Fetch `url` and return raw candidate text blocks for the LLM step."""
    html = fetch_html(url)
    texts = extract_candidates(html)
    return [{"review_text": text, "source_url": url} for text in texts]
