"""LLM-backed review validation + field extraction.

Works with any of the providers in config.py (Groq / Ollama / OpenCode Zen)
since they all speak the OpenAI chat-completions API. The model is given a
batch of raw scraped snippets and asked to decide, per snippet, whether it
is really a review of the app and to pull out the four fields we store.
"""

from __future__ import annotations

import json
import re
from typing import Any

from openai import OpenAI

from scraper.config import resolve_provider

BATCH_SIZE = 8

SYSTEM_PROMPT = """You are a data-cleaning assistant for a research team analysing \
user reviews of digital queue-management mobile apps (apps that let \
businesses manage customer queues/appointments).

You will be given a JSON array of raw review candidates scraped from the \
web or the Apple App Store. For EACH item, decide whether it is a genuine, \
English-language review written by an end user about the app. Reject items \
that are ads, navigation text, unrelated content, non-English text, or \
duplicates/boilerplate with no real opinion.

Respond with ONLY a JSON array (same length and order as the input) where \
each element is either:
  - null, if the item should be rejected, or
  - an object with exactly these keys: "reviewer", "rating", "review_text", "date"

Rules for the object:
- "reviewer": the display name of the reviewer as a string. Use "Anonymous" if unknown.
- "rating": a number 1-5 if a star rating is present or can be inferred, otherwise null.
- "review_text": the cleaned review text (strip HTML, extra whitespace), in English.
- "date": the review date as a string in YYYY-MM-DD format if available, otherwise null.

Return raw JSON only. No markdown fences, no commentary."""


def _client(provider_name: str | None, model: str | None) -> tuple[OpenAI, str]:
    provider, resolved_model, api_key = resolve_provider(provider_name)
    if model:
        resolved_model = model
    client = OpenAI(base_url=provider.base_url, api_key=api_key)
    return client, resolved_model


def _chunk(items: list[Any], size: int) -> list[list[Any]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _extract_json_array(text: str) -> list[Any]:
    """Best-effort extraction of a JSON array from an LLM response.

    Some providers ignore "no markdown fences" and wrap the answer in
    ```json ... ``` anyway, so strip that before parsing.
    """
    text = text.strip()
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        text = match.group(0)
    return json.loads(text)


def filter_and_extract(
    raw_items: list[dict],
    provider_name: str | None = None,
    model: str | None = None,
) -> list[dict]:
    """Send raw scraped review candidates to the LLM and return cleaned reviews.

    `raw_items` elements just need to be JSON-serialisable dicts describing
    whatever was scraped (e.g. {"review_text": "..."} or a richer dict with
    reviewer/rating/date already known). Items the model rejects are dropped.
    """
    if not raw_items:
        return []

    client, resolved_model = _client(provider_name, model)
    results: list[dict] = []

    for batch in _chunk(raw_items, BATCH_SIZE):
        response = client.chat.completions.create(
            model=resolved_model,
            temperature=0,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(batch, ensure_ascii=False)},
            ],
        )
        content = response.choices[0].message.content or "[]"
        try:
            parsed = _extract_json_array(content)
        except (json.JSONDecodeError, AttributeError):
            print(f"  [llm] warning: could not parse model output, skipping batch:\n{content[:300]}")
            continue

        for entry in parsed:
            if not entry:
                continue
            if not isinstance(entry, dict) or not entry.get("review_text"):
                continue
            results.append(
                {
                    "reviewer": entry.get("reviewer") or "Anonymous",
                    "rating": entry.get("rating"),
                    "review_text": str(entry["review_text"]).strip(),
                    "date": entry.get("date"),
                }
            )

    return results
