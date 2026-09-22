"""Evaluate the public French bakery CSV as an unsupported external source."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.product_demand.external_source_compatibility import (
    ExternalSourceFormatError,
    build_local_diagnostic_artifact,
    evaluate_french_bakery_profile,
    parse_french_bakery_source,
    render_french_bakery_compatibility_markdown,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Profile the nested French bakery public CSV and explain why forecasting "
            "must be withheld. This command never runs the forecasting service."
        )
    )
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--private-output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    args = parser.parse_args()

    if not _is_external_local_path(args.private_output):
        parser.error("--private-output must be stored under data/public/external.")

    try:
        profile = parse_french_bakery_source(args.csv)
        evaluation = evaluate_french_bakery_profile(profile)
    except ExternalSourceFormatError as exc:
        parser.error(str(exc))

    args.private_output.parent.mkdir(parents=True, exist_ok=True)
    args.private_output.write_text(
        json.dumps(
            build_local_diagnostic_artifact(profile, evaluation),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    args.summary_output.parent.mkdir(parents=True, exist_ok=True)
    args.summary_output.write_text(
        render_french_bakery_compatibility_markdown(evaluation),
        encoding="utf-8",
    )
    print(
        "French bakery compatibility evaluation complete: "
        f"{evaluation.forecast_eligibility.value}; no forecast produced."
    )


def _is_external_local_path(path: Path) -> bool:
    parts = path.resolve().parts
    required = ("data", "public", "external")
    return any(
        parts[index : index + len(required)] == required
        for index in range(len(parts) - len(required) + 1)
    )


if __name__ == "__main__":
    main()
