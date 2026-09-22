"""Blind research holdout on DataCo's published real-world supply-chain data."""

from __future__ import annotations

import argparse
import hashlib
import json
from io import BytesIO
from pathlib import Path

import httpx
import pandas as pd

from src.product_demand.dataco_public_evaluation import (
    HOLDOUT_DAYS,
    SOURCE_COLUMNS,
    prepare_dataco_public_holdout,
)
from src.product_demand.locked_evaluation import (
    LockedOutcomeStatus,
    evaluate_locked_holdout,
    locked_evaluation_to_dict,
)

SOURCE_URL = (
    "https://huggingface.co/datasets/Primebiswa/SupplyChainDataset/resolve/"
    "a097d5fb41bafa4f7882d0778ecc5c5d8bd602ed/DataCoSupplyChainDataset1.csv"
)
PUBLISHER_URL = "https://data.mendeley.com/datasets/8gx2fvg2k6/4"
EXPECTED_SHA256 = "4f539ba0a001c084c57a0ec13dd53d60676ed8f7a78e582a53c42181f20d6b30"
MAX_SOURCE_BYTES = 90 * 1024 * 1024


def load_source() -> tuple[pd.DataFrame, str]:
    """Keep direct identifiers and all raw bytes in memory only."""
    payload = bytearray()
    digest = hashlib.sha256()
    timeout = httpx.Timeout(120.0, connect=20.0)
    with httpx.Client(follow_redirects=True, timeout=timeout) as client:
        with client.stream("GET", SOURCE_URL) as response:
            response.raise_for_status()
            for chunk in response.iter_bytes():
                if len(payload) + len(chunk) > MAX_SOURCE_BYTES:
                    raise ValueError("Public source exceeds the 90 MiB transfer cap")
                payload.extend(chunk)
                digest.update(chunk)
    actual_sha256 = digest.hexdigest()
    if actual_sha256 != EXPECTED_SHA256:
        raise ValueError("Public source hash changed; refuse to score an unreviewed version")
    return (
        pd.read_csv(
            BytesIO(payload),
            usecols=list(SOURCE_COLUMNS),
            dtype=str,
            keep_default_na=False,
        ),
        actual_sha256,
    )


def build_report(source: pd.DataFrame, source_sha256: str) -> dict[str, object]:
    prepared = prepare_dataco_public_holdout(source)
    result = evaluate_locked_holdout(prepared, ())
    shown = tuple(
        outcome
        for outcome in result.outcomes
        if outcome.status is LockedOutcomeStatus.PREVIEW_SHOWN
    )
    abstained = tuple(
        outcome for outcome in result.outcomes if outcome.status is LockedOutcomeStatus.ABSTAINED
    )
    skipped_keys = {item.product_key for item in result.skipped_products}
    skipped_actual_units = sum(
        point.target_units
        for series in prepared.series
        if series.product_key in skipped_keys
        for point in series.points[-HOLDOUT_DAYS:]
        if point.target_units is not None
    )
    return {
        "scope": "Research-only unseen-future holdout; no business forecast approval.",
        "source": {
            "publisher_url": PUBLISHER_URL,
            "mirror_url": SOURCE_URL,
            "sha256": source_sha256,
            "mirror_matches_publisher_bytes": "unverified",
        },
        "target": "Units on rows marked COMPLETE, not total latent customer demand.",
        "source_profile": dict(prepared.evidence_counts),
        "assumptions": list(prepared.assumptions),
        "limitations": list(prepared.limitations),
        "holdout": locked_evaluation_to_dict(result),
        "outcome_audit": {
            "shown_positive_actual_weeks": sum(item.actual_total_units > 0 for item in shown),
            "abstained_positive_actual_weeks": sum(
                item.actual_total_units > 0 for item in abstained
            ),
            "shown_actual_units": str(sum(item.actual_total_units for item in shown)),
            "abstained_actual_units": str(sum(item.actual_total_units for item in abstained)),
            "skipped_actual_units": str(skipped_actual_units),
            "shown_nonzero_prediction_weeks": sum(
                item.predicted_total_units is not None and item.predicted_total_units > 0
                for item in shown
            ),
        },
    }


def render_summary(report: dict[str, object]) -> str:
    """Commit only aggregates; product IDs and row-level evidence remain local."""
    source = report["source"]
    profile = report["source_profile"]
    holdout = report["holdout"]
    audit = report["outcome_audit"]
    if not isinstance(source, dict):
        raise TypeError("Invalid DataCo report structure")
    if not isinstance(profile, dict):
        raise TypeError("Invalid DataCo report structure")
    if not isinstance(holdout, dict):
        raise TypeError("Invalid DataCo report structure")
    if not isinstance(audit, dict):
        raise TypeError("Invalid DataCo report structure")
    overall = holdout["overall"]
    gate = holdout["within_source_gate"]
    cohort = holdout["cohort"]
    if not isinstance(overall, dict):
        raise TypeError("Invalid DataCo holdout structure")
    if not isinstance(gate, dict):
        raise TypeError("Invalid DataCo holdout structure")
    if not isinstance(cohort, dict):
        raise TypeError("Invalid DataCo holdout structure")
    metrics = overall["metrics_on_shown_previews"]
    if not isinstance(metrics, dict):
        metrics = {}
    wape = metrics.get("wape")
    skill = metrics.get("skill_vs_zero")
    if wape is None:
        wape = "not defined (no positive actual units in shown weeks)"
    if skill is None:
        skill = "not defined (zero benchmark also made no error in shown weeks)"
    empty_shown_warning = (
        "No shown week had positive actual units. Exact zero matches do not demonstrate "
        "predictive skill; nonzero predictions are overforecasts. Positive "
        "completed-label units fell in abstained or skipped scopes. "
        if audit["shown_actual_units"] == "0"
        else ""
    )
    lines = [
        "# DataCo public-data blind holdout",
        "",
        "**Research-only.** This is a real-world supply-chain source, not a permissioned "
        "small online retailer or an approved forecast for operational use.",
        "",
        f"- Publisher: {source['publisher_url']}",
        f"- Pinned public mirror: {source['mirror_url']}",
        f"- Download SHA-256: `{source['sha256']}`",
        "- Publisher/mirror byte identity: unverified.",
        "- Target: units on rows labelled `COMPLETE`; other order statuses are not guessed.",
        "- All later 13 weeks were hidden when selecting each product's method; each next "
        "week was predicted before its actual values were revealed.",
        "",
        "## Source and holdout counts",
        "",
        f"- Source rows: {profile['all_source_rows']}",
        f"- `COMPLETE` rows: {profile['completed_label_rows']}",
        f"- Other-status rows: {profile['other_status_rows']}",
        f"- Products considered: {cohort['locked_product_count']}",
        f"- Products skipped for insufficient or unsafe holdout: {len(cohort['skipped_products'])}",
        f"- Weekly opportunities: {overall['forecast_opportunities']}",
        f"- Previews shown: {overall['previews_shown']}",
        f"- Honest abstentions: {overall['abstentions']}",
        f"- Shown weeks with positive actual units: {audit['shown_positive_actual_weeks']}",
        f"- Abstained weeks with positive actual units: {audit['abstained_positive_actual_weeks']}",
        f"- Actual units in shown weeks: {audit['shown_actual_units']}",
        f"- Actual units in abstained weeks: {audit['abstained_actual_units']}",
        f"- Actual units in skipped products: {audit['skipped_actual_units']}",
        "",
        "## Accuracy on shown research forecasts",
        "",
        f"- WAPE: {wape}",
        f"- Skill versus predicting zero: {skill}",
        f"- Over-forecast units: {metrics.get('overforecast_units')}",
        f"- Under-forecast units: {metrics.get('underforecast_units')}",
        f"- Within-source research gate: {gate['status']}",
        "",
        "## Interpretation",
        "",
        empty_shown_warning
        + "Absent product-days are treated as zero **only for this research view**. "
        "The source does not establish open-day completeness, stockout tracking, or the "
        "business meaning of other final-looking statuses. Therefore the live product's "
        "strict trust rules would withhold a decision-ready demand forecast, regardless "
        "of this score. The independent-small-retailer checkpoint remains pending.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--private-output",
        type=Path,
        default=Path("data/public/external/dataco_public_holdout.json"),
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=Path("docs/evaluation/dataco_public_holdout.md"),
    )
    args = parser.parse_args()
    if tuple(args.private_output.parts[:3]) != ("data", "public", "external"):
        parser.error("Private details must stay under data/public/external")
    source, source_sha256 = load_source()
    report = build_report(source, source_sha256)
    args.private_output.parent.mkdir(parents=True, exist_ok=True)
    args.private_output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    args.summary_output.parent.mkdir(parents=True, exist_ok=True)
    args.summary_output.write_text(render_summary(report))
    print("DataCo public-data holdout complete; research-only summary written.")


if __name__ == "__main__":
    main()
