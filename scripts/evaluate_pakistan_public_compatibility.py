"""Audit a public multi-merchant order archive without saving its raw bytes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.product_demand.pakistan_public_compatibility import (
    PublicSourceError,
    audit_archive,
    fetch_archive,
    render_summary,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Stream and audit the fixed Pakistan public ZIP URL; never run a forecast."
    )
    parser.add_argument(
        "--private-output",
        type=Path,
        default=Path("data/public/external/pakistan_compatibility.json"),
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=Path("docs/evaluation/pakistan_public_compatibility.md"),
    )
    args = parser.parse_args()
    if not _is_external_local_path(args.private_output):
        parser.error("Detailed output must remain under data/public/external.")
    try:
        audit = audit_archive(fetch_archive())
    except PublicSourceError as exc:
        parser.error(str(exc))
    args.private_output.parent.mkdir(parents=True, exist_ok=True)
    args.private_output.write_text(
        json.dumps(audit.private_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    args.summary_output.parent.mkdir(parents=True, exist_ok=True)
    args.summary_output.write_text(render_summary(audit), encoding="utf-8")
    print("Pakistan public compatibility audit complete: forecast withheld.")


def _is_external_local_path(path: Path) -> bool:
    parts = path.resolve().parts
    required = ("data", "public", "external")
    return any(
        parts[index : index + len(required)] == required
        for index in range(len(parts) - len(required) + 1)
    )


if __name__ == "__main__":
    main()
