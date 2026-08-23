import argparse
import json
from pathlib import Path

from dotenv import load_dotenv

from insights.loader import load_reviews
from insights.report import render_markdown
from insights.synthesis import synthesize_requirements
from scraper.config import PROVIDERS

DEFAULT_INPUT = Path(__file__).resolve().parent.parent / "data" / "reviews.csv"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "output"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze scraped reviews and synthesize a prioritized user requirements report."
    )
    parser.add_argument(
        "--input", type=Path, default=DEFAULT_INPUT, help=f"Reviews CSV to analyze (default: {DEFAULT_INPUT})"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Directory to write requirements.json / requirements_report.md into (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--provider",
        choices=list(PROVIDERS),
        default=None,
        help="LLM provider to use (default: $LLM_PROVIDER env var)",
    )
    parser.add_argument("--model", default=None, help="Override the provider's default model")
    return parser.parse_args()


def main() -> None:
    load_dotenv()
    args = parse_args()

    reviews = load_reviews(args.input)
    print(f"Loaded {len(reviews)} review(s) from {args.input}.")
    if not reviews:
        print("Nothing to analyze.")
        return

    requirements = synthesize_requirements(reviews, provider_name=args.provider, model=args.model)
    print(f"Identified {len(requirements)} distinct requirement(s).")

    args.output_dir.mkdir(parents=True, exist_ok=True)

    json_path = args.output_dir / "requirements.json"
    json_path.write_text(
        json.dumps(
            {"source_csv": str(args.input), "reviews_analyzed": len(reviews), "requirements": requirements},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    md_path = args.output_dir / "requirements_report.md"
    md_path.write_text(render_markdown(requirements, len(reviews), str(args.input)), encoding="utf-8")

    print(f"Wrote {json_path} and {md_path}.")


if __name__ == "__main__":
    main()
