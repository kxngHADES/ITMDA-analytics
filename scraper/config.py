"""LLM provider configuration.

Groq, Ollama, and OpenCode Zen all expose an OpenAI-compatible
`/chat/completions` endpoint, so a single client class can talk to any
of them just by swapping `base_url` / `api_key` / `model`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from openai import OpenAI


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    base_url: str
    api_key_env: str | None  # env var to read the key from; None if no key is needed
    default_model: str
    requires_key: bool = True


PROVIDERS: dict[str, ProviderConfig] = {
    "groq": ProviderConfig(
        name="groq",
        base_url="https://api.groq.com/openai/v1",
        api_key_env="GROQ_API_KEY",
        default_model="llama-3.3-70b-versatile",
    ),
    "ollama": ProviderConfig(
        name="ollama",
        base_url="http://localhost:11434/v1",
        api_key_env=None,
        default_model="llama3.1",
        requires_key=False,
    ),
    "opencode_zen": ProviderConfig(
        name="opencode_zen",
        base_url="https://opencode.ai/zen/v1",
        api_key_env="OPENCODE_ZEN_API_KEY",
        default_model="nemotron-3.5-lightning-free",
    ),
}

def resolve_provider(name: str | None = None) -> tuple[ProviderConfig, str, str | None]:
    """Look up a provider by name and return (config, model, api_key).

    The model defaults to the provider's default but can be overridden with
    `<PROVIDER>_MODEL` (e.g. `GROQ_MODEL`) in the environment.

    Reads `LLM_PROVIDER` from the environment lazily (not at import time) so
    that it reflects `.env` even though it's loaded after this module is
    first imported.
    """
    default_provider = os.environ.get("LLM_PROVIDER", "groq")
    key = (name or default_provider).strip().lower()
    if key not in PROVIDERS:
        valid = ", ".join(PROVIDERS)
        raise ValueError(f"Unknown LLM provider '{key}'. Valid options: {valid}")

    provider = PROVIDERS[key]
    model = os.environ.get(f"{key.upper()}_MODEL", provider.default_model)

    api_key = None
    if provider.api_key_env:
        api_key = os.environ.get(provider.api_key_env)
        if provider.requires_key and not api_key:
            raise ValueError(
                f"Missing {provider.api_key_env} in the environment. "
                f"Set it in your .env file to use the '{key}' provider."
            )
    if api_key is None:
        # Ollama doesn't check the key, but the OpenAI SDK requires a non-empty string.
        api_key = "not-needed"

    return provider, model, api_key


def build_client(provider_name: str | None = None, model: str | None = None) -> tuple[OpenAI, str]:
    """Resolve a provider and return a ready-to-use OpenAI-compatible client + model name."""
    provider, resolved_model, api_key = resolve_provider(provider_name)
    if model:
        resolved_model = model
    client = OpenAI(base_url=provider.base_url, api_key=api_key)
    return client, resolved_model
