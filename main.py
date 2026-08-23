import argparse
from pathlib import Path

from dotenv import load_dotenv

from scraper.config import PROVIDERS
from scraper.pipeline import run

DEFAULT_CSV = Path("data/reviews.csv")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape app reviews from a URL, filter/extract them with an LLM, and append to a CSV."
    )
    parser.add_argument("url", help="Apple App Store app URL, or a review website URL")
    parser.add_argument(
        "--provider",
        choices=list(PROVIDERS),
        default=None,
        help="LLM provider to use (default: $LLM_PROVIDER env var, or 'groq')",
    )
    parser.add_argument("--model", default=None, help="Override the provider's default model")
    parser.add_argument(
        "--output", type=Path, default=DEFAULT_CSV, help=f"CSV file to append to (default: {DEFAULT_CSV})"
    )
    parser.add_argument(
        "--countries",
        default=None,
        help=(
            "Comma-separated App Store storefront country codes to aggregate reviews from "
            "(default: us,gb,ca,au). Each storefront surfaces ~10 reviews; more storefronts "
            "= more data. Ignored for non-App-Store URLs."
        ),
    )
    return parser.parse_args()


def main() -> None:
    load_dotenv()
    args = parse_args()
    countries = args.countries.split(",") if args.countries else None
    run(
        url=args.url,
        csv_path=args.output,
        provider=args.provider,
        model=args.model,
        countries=countries,
    )


if __name__ == "__main__":
    main()
