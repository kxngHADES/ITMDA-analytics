"""Shared chat-completion call with retries for transient errors.

Free-tier LLM endpoints (Groq, OpenCode Zen free models, Ollama under load)
are flaky by nature — 429/500/502/503 responses and timeouts are routine,
not exceptional. Without a retry, a single blip crashes an entire batch job.
"""

from __future__ import annotations

import time

from openai import APIConnectionError, APIStatusError, APITimeoutError

MAX_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 5
RETRYABLE_STATUS_CODES = {408, 409, 429, 500, 502, 503, 504}


def chat_completion(client, model: str, messages: list[dict], temperature: float = 0) -> str:
    """Call chat.completions.create, retrying transient errors with backoff.
    Returns the response content string (empty string if the model returned none)."""
    last_exc: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = client.chat.completions.create(model=model, temperature=temperature, messages=messages)
            return response.choices[0].message.content or ""
        except APIStatusError as exc:
            if exc.status_code not in RETRYABLE_STATUS_CODES or attempt == MAX_ATTEMPTS:
                raise
            last_exc = exc
        except (APITimeoutError, APIConnectionError) as exc:
            if attempt == MAX_ATTEMPTS:
                raise
            last_exc = exc

        wait = RETRY_BACKOFF_SECONDS * attempt
        print(f"  [llm] transient error ({last_exc}), retrying in {wait}s (attempt {attempt}/{MAX_ATTEMPTS})...")
        time.sleep(wait)

    raise last_exc  # unreachable, satisfies type checkers
