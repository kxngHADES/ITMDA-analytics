"""Turns raw reviews into a prioritized list of user requirements.

Two-stage LLM pass, since a single free-tier model call can't reliably
digest an unbounded number of reviews at once:
  1. Extract — per batch of reviews, pull out recurring complaint themes
     with a mention count and example quotes.
  2. Merge — consolidate near-duplicate themes across all batches into one
     final list, and phrase each as a requirement statement.

Priority is computed in code from the merged mention count (not left to the
LLM), so it's deterministic and reproducible from the same input data.
"""

from __future__ import annotations

import json
from typing import Any

from scraper.config import build_client
from scraper.json_utils import extract_json_array
from scraper.llm_call import chat_completion

BATCH_SIZE = 25
HIGH_PRIORITY_PCT = 15.0
MEDIUM_PRIORITY_PCT = 5.0

EXTRACT_SYSTEM_PROMPT = """You are a product analyst for a team building a digital \
queue-management mobile app (an app businesses use to manage customer queues, \
waitlists, and appointments). You'll be given a JSON array of user reviews for a \
comparable app in this space.

Identify recurring COMPLAINTS, pain points, bugs, or missing features mentioned in \
these reviews — the kind of feedback that implies a product requirement. Ignore \
purely positive praise with no actionable complaint.

Group similar complaints from different reviews into a single theme entry. Respond \
with ONLY a JSON array where each element is an object with exactly these keys:
- "theme": a short (3-6 word) name for this complaint/pain point
- "description": one sentence describing the underlying problem
- "mention_count": integer, how many reviews in this batch raise this issue
- "example_quotes": array of up to 3 short verbatim quotes from these reviews illustrating it

If no reviews in this batch raise a complaint, return an empty JSON array [].
Escape any double-quote characters that appear inside a string value (e.g. \\") so \
the output is valid JSON. Return raw JSON only. No markdown fences, no commentary."""

MERGE_SYSTEM_PROMPT = """You are consolidating complaint themes extracted from multiple \
batches of app reviews (for a digital queue-management app) into one final list, to seed \
a user requirements document.

You will be given a JSON array of theme objects — the same underlying complaint may \
appear multiple times across batches with different wording. Merge semantically similar \
or duplicate themes into ONE entry each. When merging, SUM their "mention_count" values, \
and combine their "example_quotes" (keep at most 4 total, dedupe near-identical quotes).

For each final merged theme, write a formal product requirement statement in the form \
"The app should ..." or "Users need the ability to ..." that would address the complaint.

Respond with ONLY a JSON array where each element is an object with exactly these keys:
- "theme": short theme name
- "requirement": the requirement statement
- "mention_count": integer (summed across merged entries)
- "example_quotes": array of up to 4 strings

Escape any double-quote characters that appear inside a string value (e.g. \\") so \
the output is valid JSON. Return raw JSON only. No markdown fences, no commentary."""


def _chunk(items: list[Any], size: int) -> list[list[Any]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _call(client, model: str, system_prompt: str, payload: Any) -> list[dict]:
    content = chat_completion(
        client,
        model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
    ) or "[]"
    try:
        items = extract_json_array(content)
    except (json.JSONDecodeError, AttributeError):
        print(f"  [insights] warning: could not parse model output, skipping:\n{content[:300]}")
        return []
    return [item for item in items if isinstance(item, dict)]


def _priority_for(pct: float) -> str:
    if pct >= HIGH_PRIORITY_PCT:
        return "High"
    if pct >= MEDIUM_PRIORITY_PCT:
        return "Medium"
    return "Low"


def synthesize_requirements(
    reviews: list[dict],
    provider_name: str | None = None,
    model: str | None = None,
) -> list[dict]:
    """Analyze `reviews` (each needs a "review_text" key) and return a
    prioritized list of requirement dicts, ranked by mention count."""
    if not reviews:
        return []

    client, resolved_model = build_client(provider_name, model)

    raw_themes: list[dict] = []
    for batch in _chunk(reviews, BATCH_SIZE):
        print(f"  [insights] extracting complaint themes from {len(batch)} review(s)...")
        payload = [{"review_text": r["review_text"], "rating": r.get("rating")} for r in batch]
        raw_themes.extend(item for item in _call(client, resolved_model, EXTRACT_SYSTEM_PROMPT, payload) if item.get("theme"))

    if not raw_themes:
        return []

    print(f"  [insights] merging {len(raw_themes)} raw theme mention(s) into final requirements...")
    merged = _call(client, resolved_model, MERGE_SYSTEM_PROMPT, raw_themes)

    total = len(reviews)
    requirements = []
    for item in merged:
        if not item.get("requirement"):
            continue
        mention_count = int(item.get("mention_count") or 0)
        pct = round((mention_count / total * 100) if total else 0, 1)
        requirements.append(
            {
                "theme": str(item.get("theme", "")).strip(),
                "requirement": str(item["requirement"]).strip(),
                "mention_count": mention_count,
                "mention_pct": pct,
                "priority": _priority_for(pct),
                "example_quotes": [str(q).strip() for q in item.get("example_quotes", []) if q][:4],
            }
        )

    requirements.sort(key=lambda r: r["mention_count"], reverse=True)
    for i, req in enumerate(requirements, start=1):
        req["id"] = f"REQ-{i}"

    return requirements
