import argparse
from pathlib import Path

from dotenv import load_dotenv

from scraper.config import PROVIDERS
from scraper.pipeline import run, run_from_file

DEFAULT_CSV = Path("data/reviews.csv")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape app reviews from a URL, filter/extract them with an LLM, and append to a CSV."
    )
    parser.add_argument(
        "url", nargs="?", default=None, help="Apple App Store app URL, or a review website URL. Omit when using --from-file."
    )
    parser.add_argument(
        "--from-file",
        type=Path,
        default=None,
        help=(
            "Path to a text file of manually pasted review text (reviews separated by a line "
            "containing only '---'), for sites that block scraping outright (e.g. G2). Runs "
            "through the same LLM filter + CSV pipeline as scraping. Takes precedence over url."
        ),
    )
    parser.add_argument(
        "--source-url",
        default=None,
        help="Original review page URL to record in the CSV's source_url column when using --from-file.",
    )
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
    args = parser.parse_args()
    if not args.from_file and not args.url:
        parser.error("url is required unless --from-file is given")
    return args


def main() -> None:
    load_dotenv()
    args = parse_args()

    if args.from_file:
        run_from_file(
            path=args.from_file,
            csv_path=args.output,
            source_url=args.source_url,
            provider=args.provider,
            model=args.model,
        )
        return

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
