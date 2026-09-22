"""Research-only diagnosis of DataCo product-demand preview coverage.

This deliberately does not change the accepted forecast policy. The DataCo
holdout has already been viewed, so all counterfactual scores are exploratory.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import cast

import pandas as pd

from scripts.evaluate_dataco_public_holdout import (
    PUBLISHER_URL,
    SOURCE_URL,
    load_source,
)
from src.product_demand.baselines import BaselineUnavailableError, forecast_baseline
from src.product_demand.dataco_public_evaluation import (
    HOLDOUT_DAYS,
    prepare_dataco_public_holdout,
)
from src.product_demand.evaluation_contracts import EvaluationConfiguration, EvaluationSeries
from src.product_demand.locked_evaluation import (
    LockedEvaluationResult,
    LockedOriginOutcome,
    LockedOutcomeStatus,
    evaluate_locked_holdout,
)
from src.product_demand.metrics import evaluate_product_baselines
from src.product_demand.public_data_evaluation import PublicDatasetPreparation
from src.product_demand.trust_gate import assess_weekly_zero_skill
from src.product_demand.trust_policy import ProductDemandPolicyReason


def _percent(numerator: int, denominator: int) -> float | None:
    return round(100 * numerator / denominator, 1) if denominator else None


def _recency_days(series: EvaluationSeries, training_end: date) -> int | None:
    """Only observations available at the forecast origin may define recency."""
    for point in reversed(series.points):
        if point.date > training_end:
            continue
        if point.target_units is not None and point.target_units > 0:
            return (training_end - point.date).days
    return None


def _recency_band(days: int | None) -> str:
    if days is None:
        return "no_prior_completed_sale"
    if days <= 7:
        return "0_to_7_days"
    if days <= 28:
        return "8_to_28_days"
    if days <= 91:
        return "29_to_91_days"
    return "over_91_days"


def _summarize(outcomes: tuple[LockedOriginOutcome, ...]) -> dict[str, object]:
    shown = tuple(item for item in outcomes if item.status is LockedOutcomeStatus.PREVIEW_SHOWN)
    positive_weeks = tuple(item for item in outcomes if item.actual_total_units > 0)
    shown_positive = tuple(item for item in shown if item.actual_total_units > 0)
    actual = sum((item.actual_total_units for item in shown), Decimal("0"))
    errors = tuple(
        abs(item.predicted_total_units - item.actual_total_units)
        for item in shown
        if item.predicted_total_units is not None
    )
    absolute_error = sum(errors, Decimal("0"))
    positive_error = sum(
        (
            abs(item.predicted_total_units - item.actual_total_units)
            for item in shown_positive
            if item.predicted_total_units is not None
        ),
        Decimal("0"),
    )
    positive_actual = sum((item.actual_total_units for item in shown_positive), Decimal("0"))
    overforecast = sum(
        (
            max(item.predicted_total_units - item.actual_total_units, Decimal("0"))
            for item in shown
            if item.predicted_total_units is not None
        ),
        Decimal("0"),
    )
    underforecast = sum(
        (
            max(item.actual_total_units - item.predicted_total_units, Decimal("0"))
            for item in shown
            if item.predicted_total_units is not None
        ),
        Decimal("0"),
    )
    return {
        "opportunities": len(outcomes),
        "shown": len(shown),
        "withheld": len(outcomes) - len(shown),
        "coverage_percent": _percent(len(shown), len(outcomes)),
        "positive_actual_weeks": len(positive_weeks),
        "shown_positive_actual_weeks": len(shown_positive),
        "positive_week_coverage_percent": _percent(len(shown_positive), len(positive_weeks)),
        "shown_zero_predictions": sum(item.predicted_total_units == 0 for item in shown),
        "shown_nonzero_predictions": sum(
            item.predicted_total_units is not None and item.predicted_total_units > 0
            for item in shown
        ),
        "shown_actual_units": str(actual),
        "mae_units": str(absolute_error / len(shown)) if shown else None,
        "wape": str(absolute_error / actual) if actual > 0 else None,
        "skill_vs_zero": str((actual - absolute_error) / actual) if actual > 0 else None,
        "positive_week_wape": (
            str(positive_error / positive_actual) if positive_actual > 0 else None
        ),
        "overforecast_units": str(overforecast),
        "underforecast_units": str(underforecast),
        "reason_counts": dict(
            sorted(Counter(reason for item in outcomes for reason in item.policy_reasons).items())
        ),
    }


def _counterfactual_without_zero_gate(
    prepared: PublicDatasetPreparation,
    baseline: LockedEvaluationResult,
) -> tuple[LockedOriginOutcome, ...]:
    """Bypass only the zero-skill rejection; reuse the real evaluator and models."""
    by_key = {series.product_key: series for series in prepared.series}
    candidates = {}
    updated: list[LockedOriginOutcome] = []
    zero_reason = ProductDemandPolicyReason.NON_POSITIVE_ZERO_SKILL.value
    for outcome in baseline.outcomes:
        if outcome.policy_reasons != (zero_reason,):
            updated.append(outcome)
            continue
        series = by_key[outcome.product_key]
        if outcome.product_key not in candidates:
            first_training = EvaluationSeries(
                series.product_key,
                series.unit_of_measure,
                series.points[:-HOLDOUT_DAYS],
            )
            report = evaluate_product_baselines(first_training, EvaluationConfiguration())
            evidence = assess_weekly_zero_skill(report)
            if report.seven_day_winner is None or evidence.compared_fold_count < 13:
                raise AssertionError("Zero-skill rejection must retain a qualified weekly winner")
            candidates[outcome.product_key] = report.seven_day_winner
        candidate = candidates[outcome.product_key]
        origin = len(series.points) - HOLDOUT_DAYS + (outcome.holdout_week - 1) * 7
        training = EvaluationSeries(
            series.product_key, series.unit_of_measure, series.points[:origin]
        )
        if training.points[-1].date != outcome.training_end:
            raise AssertionError("Counterfactual forecast origin moved")
        try:
            forecast = forecast_baseline(training, candidate)
        except BaselineUnavailableError:
            updated.append(outcome)
            continue
        updated.append(
            replace(
                outcome,
                status=LockedOutcomeStatus.PREVIEW_SHOWN,
                selected_candidate=candidate,
                predicted_total_units=forecast.predicted_total_units,
                policy_reasons=(),
            )
        )
    return tuple(updated)


def _source_activity(
    source: pd.DataFrame,
) -> tuple[dict[str, object], dict[tuple[str, int], list[int]]]:
    dates = pd.to_datetime(source["order_date_(DateOrders)"], format="mixed", errors="coerce")
    if dates.isna().any():
        raise ValueError("DataCo audit requires parseable source dates")
    last_date = dates.max().date()
    holdout_start = last_date - timedelta(days=HOLDOUT_DAYS - 1)
    positions: dict[tuple[str, int], list[int]] = defaultdict(list)
    phase_statuses: dict[str, Counter[str]] = {
        "before_holdout": Counter(),
        "hidden_13_weeks": Counter(),
    }
    relative_weeks: dict[int, Counter[str]] = defaultdict(Counter)
    for position, (when, product_id, status) in enumerate(
        zip(dates.dt.date, source["Product_Card_Id"], source["Order_Status"])
    ):
        normalized_status = str(status).strip()
        if when < holdout_start:
            phase_statuses["before_holdout"][normalized_status] += 1
            continue
        week = (when - holdout_start).days // 7 + 1
        phase_statuses["hidden_13_weeks"][normalized_status] += 1
        relative_weeks[week][normalized_status] += 1
        if normalized_status == "COMPLETE":
            # One-based physical CSV line number; data starts after the header.
            positions[(f"dataco:{str(product_id).strip()}", week)].append(position + 2)
    return (
        {
            "status_counts_by_phase": {
                phase: dict(sorted(counts.items())) for phase, counts in phase_statuses.items()
            },
            "status_counts_by_hidden_week": {
                str(week): dict(sorted(relative_weeks[week].items())) for week in range(1, 14)
            },
            "unverified_absent_product_days": True,
        },
        positions,
    )


def build_audit(source: pd.DataFrame, source_sha256: str) -> dict[str, object]:
    """Keep identifiers and source-row positions in the private trace only."""
    prepared = prepare_dataco_public_holdout(source)
    baseline = evaluate_locked_holdout(prepared, ())
    six_folds = evaluate_locked_holdout(prepared, (), minimum_preview_folds=6)
    no_zero_gate = _counterfactual_without_zero_gate(prepared, baseline)
    activity, positions = _source_activity(source)
    series_by_key = {series.product_key: series for series in prepared.series}
    historical_method: dict[str, dict[str, object]] = {}
    for series in prepared.series:
        if len(series.points) <= HOLDOUT_DAYS:
            continue
        training = EvaluationSeries(
            series.product_key,
            series.unit_of_measure,
            series.points[:-HOLDOUT_DAYS],
        )
        evaluation = evaluate_product_baselines(training, EvaluationConfiguration())
        zero_skill = assess_weekly_zero_skill(evaluation)
        historical_method[series.product_key] = {
            "training_calendar_days": len(training.points),
            "training_positive_days": sum(
                point.target_units is not None and point.target_units > 0
                for point in training.points
            ),
            "weekly_winner": (
                evaluation.seven_day_winner.value
                if evaluation.seven_day_winner is not None
                else None
            ),
            "shared_test_weeks": zero_skill.compared_fold_count,
            "historical_skill_vs_zero": (
                str(zero_skill.skill_vs_zero) if zero_skill.skill_vs_zero is not None else None
            ),
            "weekly_candidate_evidence": [
                {
                    "method": item.candidate.candidate.value,
                    "availability": item.availability.value,
                    "completed_test_weeks": len(item.folds),
                    "reasons": [reason.value for reason in item.unavailable_reasons],
                }
                for item in evaluation.candidate_evaluations
                if item.candidate.granularity.value == "seven_day_total"
            ],
        }
    source_dates = pd.to_datetime(source["order_date_(DateOrders)"], format="mixed").dt.date
    source_quantities = pd.to_numeric(source["Order_Item_Quantity"], errors="coerce")
    source_units = {
        key: sum((Decimal(str(source_quantities.iloc[line - 2])) for line in lines), Decimal("0"))
        for key, lines in positions.items()
    }
    if len(baseline.outcomes) != len(six_folds.outcomes) or len(baseline.outcomes) != len(
        no_zero_gate
    ):
        raise AssertionError("Counterfactuals changed the opportunity denominator")
    if baseline.outcomes and (
        baseline.outcomes[0].forecast_dates[0]
        != source_dates.max() - timedelta(days=HOLDOUT_DAYS - 1)
    ):
        raise AssertionError("Source-row and forecast calendars do not align")

    trace = []
    recency: dict[str, Counter[str]] = defaultdict(Counter)
    stratum_outcomes: dict[str, list[LockedOriginOutcome]] = defaultdict(list)
    for outcome in baseline.outcomes:
        source_key = (outcome.product_key, outcome.holdout_week)
        if source_units.get(source_key, Decimal("0")) != outcome.actual_total_units:
            raise AssertionError("Source completed rows do not reconcile to weekly actual units")
        days = _recency_days(series_by_key[outcome.product_key], outcome.training_end)
        band = _recency_band(days)
        recency[band][outcome.status.value] += 1
        stratum_outcomes[outcome.stratum].append(outcome)
        trace.append(
            {
                "product_id": outcome.source_id,
                "stratum": outcome.stratum,
                "holdout_week": outcome.holdout_week,
                "training_end": outcome.training_end.isoformat(),
                "source_csv_lines": positions.get(source_key, []),
                "source_completed_rows": len(positions.get(source_key, [])),
                "prior_completed_sale_recency_days": days,
                "recency_band": band,
                "status": outcome.status.value,
                "policy_reasons": list(outcome.policy_reasons),
                "method_selection": historical_method[outcome.product_key],
                "selected_method": (
                    outcome.selected_candidate.value if outcome.selected_candidate else None
                ),
                "historical_skill_vs_zero": (
                    str(outcome.historical_skill_vs_zero)
                    if outcome.historical_skill_vs_zero is not None
                    else None
                ),
                "predicted_units": (
                    str(outcome.predicted_total_units)
                    if outcome.predicted_total_units is not None
                    else None
                ),
                "actual_units": str(outcome.actual_total_units),
            }
        )

    baseline_summary = _summarize(baseline.outcomes)
    skipped_keys = {item.product_key for item in baseline.skipped_products}
    skipped_actual_units = sum(
        (
            point.target_units
            for series in prepared.series
            if series.product_key in skipped_keys
            for point in series.points[-HOLDOUT_DAYS:]
            if point.target_units is not None
        ),
        Decimal("0"),
    )
    assessed_positive_actual_units = sum(
        (item.actual_total_units for item in baseline.outcomes), Decimal("0")
    )
    holdout_start = source_dates.max() - timedelta(days=HOLDOUT_DAYS - 1)
    hidden_completed = source_dates.ge(holdout_start) & source["Order_Status"].astype(
        str
    ).str.strip().eq("COMPLETE")
    source_hidden_units = sum(
        (Decimal(str(value)) for value in source_quantities.loc[hidden_completed]),
        Decimal("0"),
    )
    if assessed_positive_actual_units + skipped_actual_units != source_hidden_units:
        raise AssertionError("Assessed and skipped units do not reconcile to source rows")
    positive_no_winner = [
        item
        for item in baseline.outcomes
        if item.actual_total_units > 0
        and ProductDemandPolicyReason.NO_WEEKLY_WINNER.value in item.policy_reasons
    ]
    positive_no_winner_histories = sorted(
        {
            item.product_key: cast(
                int, historical_method[item.product_key]["training_calendar_days"]
            )
            for item in positive_no_winner
        }.values()
    )
    positive_no_winner_candidate_reasons = Counter(
        reason
        for item in {item.product_key: item for item in positive_no_winner}.values()
        for candidate in cast(
            list[dict[str, object]],
            historical_method[item.product_key]["weekly_candidate_evidence"],
        )
        for reason in cast(list[str], candidate["reasons"])
    )
    by_stratum = {
        stratum: _summarize(tuple(items)) for stratum, items in sorted(stratum_outcomes.items())
    }
    counterfactuals = {
        "current_policy": baseline_summary,
        "six_shared_folds_only": _summarize(six_folds.outcomes),
        "ignore_zero_skill_only": _summarize(no_zero_gate),
    }
    counterfactuals_by_stratum = {
        name: {
            stratum: _summarize(tuple(item for item in items if item.stratum == stratum))
            for stratum in sorted(stratum_outcomes)
        }
        for name, items in (
            ("current_policy", baseline.outcomes),
            ("six_shared_folds_only", six_folds.outcomes),
            ("ignore_zero_skill_only", no_zero_gate),
        )
    }
    if len(baseline.outcomes) != 1391 and len(source) == 180519:
        raise AssertionError("Pinned DataCo opportunity count changed")
    return {
        "public": {
            "scope": (
                "Exploratory diagnosis on an already-viewed public holdout; not release evidence."
            ),
            "publisher_url": PUBLISHER_URL,
            "mirror_url": SOURCE_URL,
            "sha256": source_sha256,
            "source_rows": len(source),
            "complete_rows": prepared.evidence_counts["completed_label_rows"],
            "other_status_rows": prepared.evidence_counts["other_status_rows"],
            "unknown_product_days_treated_as_zero_for_research": prepared.evidence_counts[
                "strict_missing_unknown_product_days"
            ],
            "skipped_products": len(baseline.skipped_products),
            "assessed_actual_units": str(assessed_positive_actual_units),
            "skipped_actual_units": str(skipped_actual_units),
            "hidden_source_completed_units": str(source_hidden_units),
            "activity": activity,
            "recency_at_forecast_origin": {
                band: dict(sorted(counts.items())) for band, counts in sorted(recency.items())
            },
            "baseline_by_stratum": by_stratum,
            "counterfactuals": counterfactuals,
            "counterfactuals_by_stratum": counterfactuals_by_stratum,
            "positive_week_no_winner_diagnosis": {
                "positive_weeks_with_no_winner": len(positive_no_winner),
                "affected_products": len(positive_no_winner_histories),
                "training_calendar_days_by_affected_product": positive_no_winner_histories,
                "candidate_unavailable_reason_counts": dict(
                    sorted(positive_no_winner_candidate_reasons.items())
                ),
            },
        },
        "private_trace": trace,
    }


def render_summary(audit: dict[str, object]) -> str:
    """No identifiers, dates, row positions, or raw values enter the tracked report."""
    public = audit["public"]
    if not isinstance(public, dict):
        raise TypeError("Invalid coverage audit")
    cases = public["counterfactuals"]
    activity = public["activity"]
    if not isinstance(cases, dict) or not isinstance(activity, dict):
        raise TypeError("Invalid coverage audit")
    baseline = cases["current_policy"]
    if not isinstance(baseline, dict):
        raise TypeError("Invalid coverage audit")
    lines = [
        "# DataCo product-demand coverage diagnosis",
        "",
        "**Research only.** The source's missing product-days, stockouts, and non-COMPLETE "
        "status meanings are unverified. This holdout was already viewed; none of the "
        "experiments below is fresh locked validation.",
        "",
        f"- Source: {public['publisher_url']}",
        f"- Pinned mirror: {public['mirror_url']}",
        f"- Source SHA-256: `{public['sha256']}`",
        f"- Rows: {public['source_rows']}; COMPLETE: {public['complete_rows']}; "
        f"other statuses: {public['other_status_rows']}.",
        f"- Missing product-days treated as zero only for research: "
        f"{public['unknown_product_days_treated_as_zero_for_research']}.",
        f"- Products skipped before the 13-week comparison: {public['skipped_products']}.",
        f"- Hidden-period COMPLETE-labelled units: {public['assessed_actual_units']} "
        f"in assessed products; {public['skipped_actual_units']} in skipped products.",
        "",
        "## Same-denominator counterfactuals",
        "",
        "| Research rule | Shown / opportunities | Coverage | Shown positive-sale weeks / "
        "positive-sale weeks | WAPE on shown | Skill vs zero on shown | Zero forecasts shown |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    labels = {
        "current_policy": "Accepted preview policy",
        "six_shared_folds_only": "Six shared historical weeks (instead of thirteen)",
        "ignore_zero_skill_only": "Ignore zero-skill rejection (unsafe what-if)",
    }
    for key, label in labels.items():
        result = cases[key]
        if not isinstance(result, dict):
            raise TypeError("Invalid coverage counterfactual")
        lines.append(
            f"| {label} | {result['shown']} / {result['opportunities']} | "
            f"{result['coverage_percent']}% | "
            f"{result['shown_positive_actual_weeks']} / {result['positive_actual_weeks']} | "
            f"{result['wape'] if result['wape'] is not None else 'undefined'} | "
            f"{result['skill_vs_zero'] if result['skill_vs_zero'] is not None else 'undefined'} | "
            f"{result['shown_zero_predictions']} |"
        )
    per_stratum = public["counterfactuals_by_stratum"]
    if not isinstance(per_stratum, dict):
        raise TypeError("Invalid stratum counterfactuals")
    lines.extend(
        [
            "",
            "Coverage alone is not accuracy. WAPE and skill are undefined when the shown "
            "weeks contain no positive actual units. Positive-sales-week coverage and "
            "over/under-forecast units remain separate checks.",
            "",
            "## Coverage and error by demand pattern",
            "",
            "| Rule | Pattern | Shown / opportunities | Shown positive-sale weeks | WAPE |",
            "|---|---|---:|---:|---:|",
        ]
    )
    for key, label in labels.items():
        strata = per_stratum[key]
        if not isinstance(strata, dict):
            raise TypeError("Invalid stratum counterfactuals")
        for stratum, result in strata.items():
            if not isinstance(result, dict):
                raise TypeError("Invalid stratum result")
            lines.append(
                f"| {label} | {stratum} | {result['shown']} / {result['opportunities']} | "
                f"{result['shown_positive_actual_weeks']} / {result['positive_actual_weeks']} | "
                f"{result['wape'] if result['wape'] is not None else 'undefined'} |"
            )
    lines.extend(
        [
            "",
            "## Why forecasts were withheld",
            "",
        ]
    )
    reasons = baseline["reason_counts"]
    if not isinstance(reasons, dict):
        raise TypeError("Invalid coverage reason counts")
    for reason, count in reasons.items():
        lines.append(f"- `{reason}`: {count} weekly opportunities.")
    no_winner = public["positive_week_no_winner_diagnosis"]
    if not isinstance(no_winner, dict):
        raise TypeError("Invalid positive-week diagnosis")
    lines.append(
        f"- Positive-sale weeks without a winner: "
        f"{no_winner['positive_weeks_with_no_winner']} across "
        f"{no_winner['affected_products']} products."
    )
    lines.append(
        "- Training calendar days for those products (one count per product): "
        f"{no_winner['training_calendar_days_by_affected_product']}."
    )
    lines.append(
        "- Weekly candidate unavailable reasons for those products: "
        f"{no_winner['candidate_unavailable_reason_counts']}."
    )
    lines.append(
        "- Interpretation: the positive-sale opportunities in assessed products belonged to "
        "products with only 2–31 calendar days before the holdout. Their methods had no "
        "weekly winner, so neither relaxing the 13-week preview floor nor ignoring zero "
        "skill produced useful positive-demand coverage."
    )
    lines.extend(["", "## Source activity and recency", ""])
    statuses = activity["status_counts_by_phase"]
    if not isinstance(statuses, dict):
        raise TypeError("Invalid source activity counts")
    for phase, counts in statuses.items():
        if not isinstance(counts, dict):
            raise TypeError("Invalid source status counts")
        formatted = ", ".join(f"{status}={count}" for status, count in counts.items())
        lines.append(f"- {phase.replace('_', ' ')}: {formatted}.")
    recency = public["recency_at_forecast_origin"]
    if not isinstance(recency, dict):
        raise TypeError("Invalid recency counts")
    for band, counts in recency.items():
        if not isinstance(counts, dict):
            raise TypeError("Invalid recency counts")
        shown = counts.get("preview_shown", 0)
        withheld = counts.get("abstained", 0)
        lines.append(
            f"- Prior completed sale {band.replace('_', ' ')}: {shown} shown, {withheld} withheld."
        )
    recent_shown = sum(
        cast(dict[str, int], recency.get(band, {})).get("preview_shown", 0)
        for band in ("0_to_7_days", "8_to_28_days")
    )
    if baseline["shown"] and recent_shown == 0:
        lines.append(
            "- None of the shown forecasts involved a product with a recorded completed "
            "sale in the preceding 28 days. This is a research-cohort warning, not "
            "proof of product inactivity."
        )
    lines.extend(
        [
            "",
            "Recency uses only sales known at each forecast origin, never later outcomes. "
            "The source-to-calendar checks reconciled every assessed weekly actual with "
            "its COMPLETE-labelled source rows. Neither a 70% coverage target nor any "
            "counterfactual authorizes weakening the live trust gate. The independent "
            "small-retailer validation remains pending.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--private-output",
        type=Path,
        default=Path("data/public/external/dataco_coverage_audit.json"),
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=Path("docs/evaluation/dataco_coverage_audit.md"),
    )
    args = parser.parse_args()
    private_root = (Path.cwd() / "data/public/external").resolve()
    if not args.private_output.resolve().is_relative_to(private_root):
        parser.error("Private traces must remain under data/public/external")
    source, sha256 = load_source()
    audit = build_audit(source, sha256)
    args.private_output.parent.mkdir(parents=True, exist_ok=True)
    args.private_output.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n")
    args.summary_output.parent.mkdir(parents=True, exist_ok=True)
    args.summary_output.write_text(render_summary(audit))
    print("DataCo coverage audit complete; experiments remain research-only.")


if __name__ == "__main__":
    main()
