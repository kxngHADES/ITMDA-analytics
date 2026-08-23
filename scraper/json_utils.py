"""Shared parsing of JSON arrays out of LLM chat responses."""

from __future__ import annotations

import json
import re
from typing import Any

from json_repair import repair_json


def extract_json_array(text: str) -> list[Any]:
    """Best-effort extraction of a JSON array from an LLM response.

    Some providers ignore "no markdown fences" instructions and wrap the
    answer in ```json ... ``` anyway, so strip that before parsing. Models
    also sometimes echo review text verbatim with unescaped quotes inside a
    JSON string (e.g. `"...use "continue" button"`), which breaks strict
    `json.loads` — fall back to `json_repair` for that case rather than
    silently dropping the whole batch.
    """
    text = text.strip()
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        text = match.group(0)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return json.loads(repair_json(text))
