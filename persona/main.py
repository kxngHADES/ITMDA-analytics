"""
main.py

Runs synthetic persona simulations against an LLM provider (OpenCode Zen,
Groq, or Ollama -- anything speaking the OpenAI-compatible chat-completions
API) and stores each result as a JSON file in res/, plus one combined
res/all_results.json.

Directory layout expected:

    persona/
    |-- main.py
    |-- personas.json      # list of {id, label, profile}
    |-- scenarios.json     # list of {id, label, prompt}
    |-- res/                # output directory (created automatically)

Setup:
    pip install -r requirements.txt

    Put your provider's key in a .env file next to main.py, e.g.:
        LLM_PROVIDER=opencode_zen
        OPENCODE_ZEN_API_KEY=your-key-here
        # OPENCODE_ZEN_MODEL=nemotron-3.5-lightning-free

    (Alternatively export the same variables as real environment variables.)

Usage:
    python main.py                     # run every persona x every scenario
    python main.py --persona P2_elderly_patient
    python main.py --scenario join_queue
    python main.py --provider groq --model llama-3.3-70b-versatile
    python main.py --list              # list available persona and scenario ids
"""

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

# Optional: load a .env file if python-dotenv is installed. This is not
# required -- if it's missing, we just rely on real environment variables.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI
except ImportError:
    print(
        "The 'openai' package is not installed.\n"
        "Install dependencies first:\n"
        "    pip install -r requirements.txt",
        file=sys.stderr,
    )
    sys.exit(1)


BASE_DIR = Path(__file__).resolve().parent
RES_DIR = BASE_DIR / "res"
PERSONAS_FILE = BASE_DIR / "personas.json"
SCENARIOS_FILE = BASE_DIR / "scenarios.json"

MAX_RETRIES = 4
RETRY_BACKOFF_SECONDS = 5  # doubled on each retry
RETRYABLE_STATUS_CODES = {408, 409, 429, 500, 502, 503, 504}


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    base_url: str
    api_key_env: str | None  # env var to read the key from; None if no key is needed
    default_model: str
    requires_key: bool = True


PROVIDERS: dict[str, ProviderConfig] = {
    "opencode_zen": ProviderConfig(
        name="opencode_zen",
        base_url="https://opencode.ai/zen/v1",
        api_key_env="OPENCODE_ZEN_API_KEY",
        default_model="nemotron-3.5-lightning-free",
    ),
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
}


def resolve_provider(name: str | None = None) -> tuple[ProviderConfig, str, str]:
    """Look up a provider by name and return (config, model, api_key).

    The model defaults to the provider's default but can be overridden with
    `<PROVIDER>_MODEL` (e.g. `OPENCODE_ZEN_MODEL`) in the environment. Reads
    `LLM_PROVIDER` from the environment lazily so it reflects a .env file
    loaded after this module was first imported.
    """
    default_provider = os.environ.get("LLM_PROVIDER", "opencode_zen")
    key = (name or default_provider).strip().lower()
    if key not in PROVIDERS:
        valid = ", ".join(PROVIDERS)
        print(f"Unknown LLM provider '{key}'. Valid options: {valid}", file=sys.stderr)
        sys.exit(1)

    provider = PROVIDERS[key]
    model = os.environ.get(f"{key.upper()}_MODEL", provider.default_model)

    api_key = None
    if provider.api_key_env:
        api_key = os.environ.get(provider.api_key_env)
        if provider.requires_key and not api_key:
            print(
                f"Missing {provider.api_key_env} in the environment.\n"
                f"Set it in your .env file to use the '{key}' provider.",
                file=sys.stderr,
            )
            sys.exit(1)

    return provider, model, api_key or "not-needed"


def get_client(provider_name: str | None, model_override: str | None) -> tuple["OpenAI", str, str]:
    provider, model, api_key = resolve_provider(provider_name)
    if model_override:
        model = model_override
    client = OpenAI(base_url=provider.base_url, api_key=api_key)
    return client, model, provider.name


def load_json_list(path: Path, what: str) -> list:
    if not path.exists():
        print(f"Could not find {what} file at: {path}", file=sys.stderr)
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def safe_filename(*parts: str) -> str:
    name = "__".join(parts)
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in name)


def call_llm(client: "OpenAI", model: str, system_prompt: str, user_prompt: str) -> dict:
    """Calls the chat completion API with retry/backoff on transient failures."""
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            completion = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.7,
            )
            choice = completion.choices[0]
            return {
                "success": True,
                "response_text": choice.message.content,
                "finish_reason": choice.finish_reason,
                "usage": getattr(completion, "usage", None)
                and completion.usage.model_dump(),
            }
        except APIStatusError as exc:
            last_error = str(exc)
            if exc.status_code not in RETRYABLE_STATUS_CODES or attempt == MAX_RETRIES:
                return {"success": False, "error": last_error}
        except (APITimeoutError, APIConnectionError) as exc:
            last_error = str(exc)
            if attempt == MAX_RETRIES:
                return {"success": False, "error": last_error}
        except Exception as exc:  # anything else unexpected
            last_error = str(exc)
            if attempt == MAX_RETRIES:
                return {"success": False, "error": last_error}

        wait = RETRY_BACKOFF_SECONDS * (2 ** (attempt - 1))
        print(
            f"    attempt {attempt} failed ({last_error}); retrying in {wait}s...",
            file=sys.stderr,
        )
        time.sleep(wait)

    return {"success": False, "error": last_error}


def load_existing_results(combined_path: Path) -> dict[tuple[str, str], dict]:
    """Load res/all_results.json (if present) keyed by (persona_id, scenario_id)
    so a new run can update/append into it instead of discarding prior results."""
    if not combined_path.exists():
        return {}
    with open(combined_path, "r", encoding="utf-8") as f:
        existing = json.load(f)
    return {(r["persona_id"], r["scenario_id"]): r for r in existing}


def run(personas: list, scenarios: list, client: "OpenAI", model: str, provider_name: str) -> list:
    RES_DIR.mkdir(parents=True, exist_ok=True)

    combined_path = RES_DIR / "all_results.json"
    all_results_by_key = load_existing_results(combined_path)
    total = len(personas) * len(scenarios)
    count = 0

    for persona in personas:
        for scenario in scenarios:
            count += 1
            print(f"[{count}/{total}] {persona['id']} x {scenario['id']} ...")

            result = call_llm(
                client=client,
                model=model,
                system_prompt=persona["profile"],
                user_prompt=scenario["prompt"],
            )

            record = {
                "persona_id": persona["id"],
                "persona_label": persona.get("label", ""),
                "scenario_id": scenario["id"],
                "scenario_label": scenario.get("label", ""),
                "provider": provider_name,
                "model": model,
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                **result,
            }

            out_name = safe_filename(persona["id"], scenario["id"]) + ".json"
            out_path = RES_DIR / out_name
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(record, f, indent=2, ensure_ascii=False)

            status = "ok" if result.get("success") else "FAILED"
            print(f"    -> {status}: saved to res/{out_name}")

            all_results_by_key[(persona["id"], scenario["id"])] = record

    all_results = list(all_results_by_key.values())
    with open(combined_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(
        f"\nSaved {count} new/updated result(s). Combined file now has "
        f"{len(all_results)} total: res/all_results.json"
    )

    return all_results


def main():
    parser = argparse.ArgumentParser(
        description="Run synthetic persona simulations against an LLM provider."
    )
    parser.add_argument(
        "--persona",
        help="Only run this persona id (see --list for available ids).",
    )
    parser.add_argument(
        "--scenario",
        help="Only run this scenario id (see --list for available ids).",
    )
    parser.add_argument(
        "--provider",
        choices=list(PROVIDERS),
        default=None,
        help="LLM provider to use (default: $LLM_PROVIDER env var, or 'opencode_zen').",
    )
    parser.add_argument("--model", default=None, help="Override the provider's default model")
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available persona and scenario ids, then exit.",
    )
    args = parser.parse_args()

    personas = load_json_list(PERSONAS_FILE, "personas")
    scenarios = load_json_list(SCENARIOS_FILE, "scenarios")

    if args.list:
        print("Personas:")
        for p in personas:
            print(f"  - {p['id']}: {p.get('label', '')}")
        print("\nScenarios:")
        for s in scenarios:
            print(f"  - {s['id']}: {s.get('label', '')}")
        return

    if args.persona:
        personas = [p for p in personas if p["id"] == args.persona]
        if not personas:
            print(f"No persona found with id '{args.persona}'.", file=sys.stderr)
            sys.exit(1)

    if args.scenario:
        scenarios = [s for s in scenarios if s["id"] == args.scenario]
        if not scenarios:
            print(f"No scenario found with id '{args.scenario}'.", file=sys.stderr)
            sys.exit(1)

    client, model, provider_name = get_client(args.provider, args.model)
    print(f"Using provider '{provider_name}' with model '{model}'.")

    run(personas, scenarios, client, model, provider_name)


if __name__ == "__main__":
    main()
