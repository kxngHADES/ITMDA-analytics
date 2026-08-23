"""Apple App Store review scraping via headless browser rendering.

Apple used to publish an official public RSS/JSON feed for app reviews, but
as of 2026 that endpoint (itunes.apple.com/.../rss/customerreviews/...) is
dead — it returns an empty feed for every app (throttled/discontinued). The
App Store web page also doesn't embed review data in the raw HTML anymore;
it's rendered client-side. So we render the page with Playwright instead and
read the reviews out of the DOM, same as a person would see them.

Important limitation to know about: Apple's "see all reviews" page is
server-rendered with a fixed set of ~10 reviews per (app, country storefront)
and no further pagination or infinite scroll — there is currently no free,
public way to pull more than that per storefront. To get a larger sample,
this module can aggregate reviews across several country storefronts (each
storefront surfaces a different ~10 reviews, in whatever language is
dominant there — hence the LLM language filter downstream).
"""

from __future__ import annotations

import re

from playwright.sync_api import sync_playwright

APP_ID_RE = re.compile(r"/id(\d+)")
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
PAGE_LOAD_TIMEOUT_MS = 30_000
DEFAULT_COUNTRIES = ["us", "gb", "ca", "au"]

REVIEWS_JS = """
() => {
  const cards = document.querySelectorAll('li > div.container[aria-labelledby]');
  return Array.from(cards).map(card => {
    const author = card.querySelector('span.author');
    const time = card.querySelector('time.date');
    const title = card.querySelector('h3.title');
    const stars = card.querySelector('ol.stars');
    const body = card.querySelector('p[data-testid="truncate-text"]') || card.querySelector('.content p');
    return {
      reviewer: author ? author.textContent.trim() : null,
      date: time ? time.getAttribute('datetime') : null,
      title: title ? title.textContent.trim() : null,
      rating_label: stars ? stars.getAttribute('aria-label') : null,
      review_text: body ? body.textContent.trim() : null,
    };
  });
}
"""


def is_appstore_url(url: str) -> bool:
    return "apps.apple.com" in url or "itunes.apple.com" in url


def extract_app_id(url: str) -> str:
    match = APP_ID_RE.search(url)
    if not match:
        raise ValueError(f"Could not find an app id (e.g. /id123456789) in URL: {url}")
    return match.group(1)


def _parse_rating(rating_label: str | None) -> int | None:
    if not rating_label:
        return None
    match = re.search(r"\d+", rating_label)
    return int(match.group(0)) if match else None


def _fetch_storefront_reviews(app_id: str, country: str) -> list[dict]:
    url = f"https://apps.apple.com/{country}/app/{app_id}?see-all=reviews&platform=iphone"
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(user_agent=USER_AGENT)
            page.goto(url, wait_until="networkidle", timeout=PAGE_LOAD_TIMEOUT_MS)
            page.wait_for_timeout(1000)
            raw_cards = page.evaluate(REVIEWS_JS)
        finally:
            browser.close()

    reviews = []
    for card in raw_cards:
        if not card.get("review_text"):
            continue
        title = card.get("title")
        body = card["review_text"]
        reviews.append(
            {
                "reviewer": card.get("reviewer") or "Anonymous",
                "rating": _parse_rating(card.get("rating_label")),
                "review_text": f"{title}. {body}" if title else body,
                "date": card["date"].split("T")[0] if card.get("date") else None,
            }
        )
    return reviews


def fetch_reviews(url: str, countries: list[str] | None = None) -> list[dict]:
    """Fetch reviews for the app in `url` by rendering the App Store review
    page for each storefront in `countries` (default: a handful of
    English-speaking storefronts) and reading the review cards out of the
    DOM. Each storefront surfaces up to ~10 reviews; there's no further
    pagination available publicly, so more storefronts = more data."""
    app_id = extract_app_id(url)
    countries = countries or DEFAULT_COUNTRIES

    raw_items: list[dict] = []
    for country in countries:
        try:
            raw_items.extend(_fetch_storefront_reviews(app_id, country))
        except Exception as exc:  # noqa: BLE001 - keep scraping other storefronts
            print(f"  [appstore] warning: failed to fetch '{country}' storefront: {exc}")

    return raw_items
