"""Run a local-only independent-business product-demand evaluation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from src.product_demand.independent_evaluation import (
    IndependentEvaluationConfigError,
    load_independent_evaluation_config,
    render_independent_evaluation_markdown,
    run_independent_evaluation,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate the frozen product-demand preview policy against a local, anonymized "
            "business CSV. Raw data and detailed output must remain outside Git."
        )
    )
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--private-output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    args = parser.parse_args()
    if not _is_private_path(args.private_output):
        parser.error("--private-output must be stored under a data/private directory.")

    try:
        config = load_independent_evaluation_config(args.config)
        source = pd.read_csv(args.csv, dtype=str, keep_default_na=False)
        report = run_independent_evaluation(source, config)
    except (IndependentEvaluationConfigError, OSError, pd.errors.ParserError) as exc:
        parser.error(str(exc))

    args.private_output.parent.mkdir(parents=True, exist_ok=True)
    args.private_output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    args.summary_output.parent.mkdir(parents=True, exist_ok=True)
    args.summary_output.write_text(
        render_independent_evaluation_markdown(report),
        encoding="utf-8",
    )
    outcome = report["outcome"]
    if not isinstance(outcome, dict):
        raise AssertionError("Independent evaluation did not produce an outcome.")
    print(
        f"Independent-business evaluation complete: {outcome.get('classification', 'inconclusive')}"
    )


def _is_private_path(path: Path) -> bool:
    parts = path.resolve().parts
    return any(parts[index : index + 2] == ("data", "private") for index in range(len(parts) - 1))


if __name__ == "__main__":
    main()
