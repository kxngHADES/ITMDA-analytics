"""Fallback for sites that block automated access outright (e.g. G2).

Rather than trying to defeat bot-detection (fingerprint spoofing, CAPTCHA
solving, proxies — out of scope, and likely against the target site's
Terms of Service), a teammate can manually copy the visible review text out
of their own browser into a text file and run it through the same LLM
filter/extract + CSV pipeline as a normal scrape.
"""

from __future__ import annotations

import re
from pathlib import Path

from scraper.web import MIN_TEXT_LEN

BLOCK_SEPARATOR_RE = re.compile(r"^\s*---\s*$", re.MULTILINE)


def load_candidates(path: Path) -> list[dict]:
    """Split a pasted-reviews text file into candidate blocks.

    Reviews are separated by a line containing only `---` (blank-line
    splitting isn't safe since a single pasted review can itself contain
    paragraph breaks).
    """
    text = path.read_text(encoding="utf-8")
    blocks = [b.strip() for b in BLOCK_SEPARATOR_RE.split(text)]
    return [{"review_text": block} for block in blocks if len(block) >= MIN_TEXT_LEN]
