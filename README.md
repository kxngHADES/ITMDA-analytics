# App Review Scraper

Scrapes reviews for digital queue-management mobile apps from the **Apple App
Store** (or a generic review website), uses an LLM to filter out
non-genuine/non-English content and pull out clean fields, then appends the
results to a shared CSV (`data/reviews.csv`) for the team's data analysis.

Each saved row has: `reviewer, rating, review_text, date, source_url`.

## 1. One-time setup

You need [uv](https://docs.astral.sh/uv/) installed. Then, from this folder:

```bash
uv sync
uv run playwright install chromium
```

The second command downloads a headless Chromium browser (~150MB) that's
used to render Apple App Store pages. Apple's old review RSS feed is dead as
of 2026, so reading the rendered page is the only free way left to get App
Store review data — this is a one-time download per machine.

Copy the env file and add your LLM API key(s):

```bash
cp .env.example .env
```

Then edit `.env`. You only need to fill in the key for whichever provider
you plan to use:

| Provider | Where to get a free key | Notes |
|---|---|---|
| **Groq Cloud** (default) | https://console.groq.com/keys | Free tier, fast, hosted — easiest for the team to share. |
| **Ollama** | n/a — runs locally | Install [Ollama](https://ollama.com), run `ollama pull llama3.1`, and make sure `ollama serve` is running. No API key needed. |
| **OpenCode Zen** | https://opencode.ai/auth | Free hosted models. |

## 2. Running the scraper

```bash
uv run main.py <url>
```

Examples:

```bash
# Apple App Store — pass the app's App Store page URL
uv run main.py "https://apps.apple.com/us/app/qminder-queue-management/id533847552"

# A generic review website
uv run main.py "https://example.com/reviews/some-queue-app"

# Use a specific provider / model
uv run main.py "<url>" --provider ollama --model llama3.1

# Write to a different CSV
uv run main.py "<url>" --output data/my_reviews.csv
```

Run it again on the same URL any time — already-saved reviews (matched by
reviewer + date + review text) are skipped, so you won't get duplicates in
the CSV.

## 3. How it works

1. **Scrape** — the URL is inspected to decide the source:
   - `apps.apple.com` / `itunes.apple.com` → the **Apple App Store** path
     (`scraper/appstore.py`). It renders the app's "see all reviews" page
     with a headless browser and reads reviewer/rating/text/date straight
     out of the page.
   - Anything else → the **generic web** path (`scraper/web.py`). It fetches
     the page and pulls out chunks of text that look like review blocks
     (via common `review`/`comment`/`rating`-style class names, itemprop
     attributes, etc.), falling back to paragraph-sized blocks if nothing
     obviously review-shaped is found. Because markup varies wildly across
     review sites, this step is deliberately loose — the LLM step below is
     what actually decides what's real.
2. **LLM filter + extract** (`scraper/llm_client.py`) — the raw candidates
   are batched and sent to the configured LLM, which is asked to reject
   anything that isn't a genuine, English-language review of the app (ads,
   nav text, spam, non-English, etc.) and to return the four clean fields
   for whatever's left.
3. **Save** (`scraper/csv_store.py`) — cleaned reviews are appended to the
   CSV, skipping ones already present.

## 4. Known limitation: App Store review volume

Apple doesn't currently offer a free way to pull more than a small, fixed
number of reviews per app. The old public RSS feed
(`itunes.apple.com/.../rss/customerreviews/...`) that used to return up to
500 reviews per app is dead — it returns an empty feed for every app as of
2026. The App Store web page itself only server-renders about **10 reviews
per country storefront**, with no further pagination or infinite scroll.

To work around this, the scraper aggregates reviews across several country
storefronts (`us, gb, ca, au` by default — each one surfaces a different set
of ~10 reviews). You can widen this with `--countries`:

```bash
uv run main.py "<url>" --countries us,gb,ca,au,ie,nz,in,sg
```

Non-English storefronts (e.g. `de`, `fr`, `jp`) will mostly get filtered out
by the LLM's English-only check, but you can still pass them if you want —
worst case they just get dropped in step 2 above.

## 5. Project layout

```
main.py                  # CLI entry point
scraper/
  config.py              # LLM provider config (Groq / Ollama / OpenCode Zen)
  llm_client.py           # sends raw candidates to the LLM, parses results
  appstore.py             # Apple App Store scraping (Playwright)
  web.py                  # generic review website scraping (requests + BeautifulSoup)
  csv_store.py             # dedup + append to CSV
  pipeline.py              # ties the above together
data/
  reviews.csv             # shared output — committed so the team stays in sync
```

## 6. Adding a new site with a known structure

If you know a specific review site's HTML structure and the generic
extractor in `web.py` isn't picking up its reviews well, add a small
site-specific selector list at the top of `extract_candidates()` rather than
touching the fallback logic — that keeps the generic path working for
everything else.
