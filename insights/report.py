"""Renders the requirements list as a human-readable Markdown report."""

from __future__ import annotations

from datetime import datetime, timezone

from insights.synthesis import HIGH_PRIORITY_PCT, MEDIUM_PRIORITY_PCT

PRIORITY_ORDER = ["High", "Medium", "Low"]


def render_markdown(requirements: list[dict], reviews_analyzed: int, source_csv: str) -> str:
    lines = [
        "# User Requirements from Review Analysis",
        "",
        f"Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} from "
        f"`{source_csv}` ({reviews_analyzed} reviews analyzed).",
        "",
        f"Priority reflects the share of reviews raising the issue: "
        f"**High** ≥{HIGH_PRIORITY_PCT:g}%, **Medium** ≥{MEDIUM_PRIORITY_PCT:g}%, **Low** below that.",
        "",
    ]

    if not requirements:
        lines.append("No recurring complaints were found in the analyzed reviews.")
        return "\n".join(lines) + "\n"

    for priority in PRIORITY_ORDER:
        group = [r for r in requirements if r["priority"] == priority]
        if not group:
            continue
        lines.append(f"## {priority} priority")
        lines.append("")
        for req in group:
            lines.append(f"### {req['id']}: {req['theme']}")
            lines.append("")
            lines.append(f"**Requirement:** {req['requirement']}")
            lines.append("")
            lines.append(f"Mentioned in {req['mention_count']} of {reviews_analyzed} reviews ({req['mention_pct']}%).")
            lines.append("")
            if req["example_quotes"]:
                lines.append("Example feedback:")
                lines.append("")
                for quote in req["example_quotes"]:
                    lines.append(f"> {quote}")
                lines.append("")

    return "\n".join(lines) + "\n"
