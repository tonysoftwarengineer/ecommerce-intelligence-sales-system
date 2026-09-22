from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pandas as pd
import pytest

from src.product_demand.evaluation_contracts import EvaluationConfiguration
from src.product_demand.public_data_evaluation import (
    M5_STRATA,
    evaluate_public_series,
    prepare_m5_public_evaluation,
    prepare_uci_public_evaluation,
    public_evaluation_evidence,
)


def _m5_calendar(days: int) -> pd.DataFrame:
    start = date(2011, 1, 29)
    return pd.DataFrame(
        {
            "d": [f"d_{index}" for index in range(1, days + 1)],
            "date": [start + timedelta(days=index - 1) for index in range(1, days + 1)],
        }
    )


def _m5_row(source_id: str, values: list[int]) -> dict[str, object]:
    return {
        "id": source_id,
        "item_id": source_id.split("_")[0],
        "dept_id": "D1",
        "cat_id": "C1",
        "store_id": "S1",
        "state_id": "CA",
        **{f"d_{index}": value for index, value in enumerate(values, start=1)},
    }


def test_uci_adapter_keeps_strict_unknowns_and_labels_research_zero_assumption() -> None:
    rows = []
    for day in range(1, 43):
        if day == 20:
            continue
        rows.append(
            {
                "Invoice": f"A{day}",
                "StockCode": "SAFE",
                "Description": "Safe product",
                "Quantity": 2,
                "InvoiceDate": pd.Timestamp("2025-01-01") + pd.Timedelta(days=day - 1),
            }
        )
    rows.extend(
        [
            {
                "Invoice": "B1",
                "StockCode": "AMBIGUOUS",
                "Description": "Ambiguous product",
                "Quantity": 3,
                "InvoiceDate": pd.Timestamp("2025-01-01"),
            },
            {
                "Invoice": "B2",
                "StockCode": "AMBIGUOUS",
                "Description": "Ambiguous product",
                "Quantity": -1,
                "InvoiceDate": pd.Timestamp("2025-01-02"),
            },
            {
                "Invoice": "C3",
                "StockCode": "SAFE",
                "Description": "Safe product",
                "Quantity": -2,
                "InvoiceDate": pd.Timestamp("2025-01-10"),
            },
        ]
    )

    prepared = prepare_uci_public_evaluation(pd.DataFrame(rows), product_limit=2)

    assert prepared.selected_source_ids == ("SAFE", "AMBIGUOUS")
    assert len(prepared.series) == 1
    assert prepared.series[0].product_key == "id:SAFE"
    assert prepared.evidence_counts["strict_missing_unknown_days"] == 1
    assert prepared.evidence_counts["research_unavailable_products"] == 1
    assert prepared.evidence_counts["negative_non_cancellation_rows"] == 1
    assert "research_only" in prepared.evaluation_mode


def test_uci_top_product_ties_are_resolved_by_product_code() -> None:
    source = pd.DataFrame(
        [
            {
                "Invoice": "1",
                "StockCode": code,
                "Description": code,
                "Quantity": 1,
                "InvoiceDate": "2025-01-01",
            }
            for code in ("B", "A")
        ]
    )

    prepared = prepare_uci_public_evaluation(source, product_limit=1)

    assert prepared.selected_source_ids == ("A",)


def test_m5_adapter_samples_every_stratum_and_trims_prelaunch_zeros() -> None:
    days = 400
    dense = [1] * days
    intermittent = [1 if index % 3 == 0 else 0 for index in range(days)]
    sparse = [1 if index % 20 == 0 else 0 for index in range(days)]
    delayed = ([0] * 370) + ([2] * 30)
    sales = pd.DataFrame(
        [
            _m5_row("DENSE_S1_evaluation", dense),
            _m5_row("INTERMITTENT_S1_evaluation", intermittent),
            _m5_row("SPARSE_S1_evaluation", sparse),
            _m5_row("DELAYED_S1_evaluation", delayed),
        ]
    )

    prepared = prepare_m5_public_evaluation(
        sales,
        _m5_calendar(days),
        per_stratum=1,
        sample_seed="fixed",
    )

    assert {profile.stratum for profile in prepared.profiles} == set(M5_STRATA)
    delayed_profile = next(
        profile for profile in prepared.profiles if profile.stratum == "delayed_start"
    )
    assert delayed_profile.first_source_day_number == 371
    assert delayed_profile.calendar_days == 30
    assert prepared.evidence_counts["prelaunch_zero_days_trimmed"] >= 370


def test_m5_sampling_is_deterministic_and_does_not_depend_on_row_order() -> None:
    days = 60
    rows = [_m5_row(f"ITEM{index}_S1_evaluation", [1] * days) for index in range(1, 5)]
    first = prepare_m5_public_evaluation(
        pd.DataFrame(rows), _m5_calendar(days), per_stratum=2, sample_seed="fixed"
    )
    second = prepare_m5_public_evaluation(
        pd.DataFrame(list(reversed(rows))),
        _m5_calendar(days),
        per_stratum=2,
        sample_seed="fixed",
    )

    assert first.selected_source_ids == second.selected_source_ids


def test_m5_sampling_excludes_previously_evaluated_source_ids() -> None:
    days = 60
    rows = [_m5_row(f"ITEM{index}_S1_evaluation", [1] * days) for index in range(1, 6)]
    development = prepare_m5_public_evaluation(
        pd.DataFrame(rows),
        _m5_calendar(days),
        per_stratum=2,
        sample_seed="development",
    )
    locked = prepare_m5_public_evaluation(
        pd.DataFrame(rows),
        _m5_calendar(days),
        per_stratum=2,
        sample_seed="locked",
        excluded_source_ids=frozenset(development.selected_source_ids),
    )

    assert set(development.selected_source_ids).isdisjoint(locked.selected_source_ids)
    assert locked.evidence_counts["excluded_source_products"] == 2


def test_m5_adapter_rejects_negative_daily_sales() -> None:
    sales = pd.DataFrame([_m5_row("ITEM_S1_evaluation", [1, -1, 2])])

    with pytest.raises(ValueError, match="must not be negative"):
        prepare_m5_public_evaluation(sales, _m5_calendar(3), per_stratum=1)


def test_public_evidence_reports_coverage_and_metric_distributions() -> None:
    days = 70
    sales = pd.DataFrame([_m5_row("ITEM_S1_evaluation", [3] * days)])
    prepared = prepare_m5_public_evaluation(
        sales,
        _m5_calendar(days),
        per_stratum=1,
        sample_seed="fixed",
    )
    reports = evaluate_public_series(
        prepared,
        EvaluationConfiguration(minimum_folds=3),
    )

    evidence = public_evaluation_evidence(prepared, reports)

    assert evidence["prepared_product_count"] == 1
    assert evidence["products_with_daily_winner"] == 1
    assert evidence["daily_winner_counts"] == {"latest_value": 1}
    assert evidence["daily_rank_one_counts_including_benchmark"] == {"latest_value": 1}
    assert evidence["selected_daily_vs_zero_counts"] == {"selected_better_than_zero": 1}
    latest = evidence["candidate_evidence"]["latest_value"]
    assert latest["daily_mae"]["median"] == "0"
    assert latest["seven_day_absolute_error"]["median"] == "0"
    assert reports[0].selection_label.value == "evaluation_only"


def test_public_evidence_does_not_hide_when_zero_benchmark_ties_selected_method() -> None:
    days = 70
    sales = pd.DataFrame([_m5_row("ZERO_S1_evaluation", [1] + ([0] * (days - 1)))])
    prepared = prepare_m5_public_evaluation(
        sales,
        _m5_calendar(days),
        per_stratum=1,
        sample_seed="fixed",
    )
    reports = evaluate_public_series(prepared)

    evidence = public_evaluation_evidence(prepared, reports)

    assert evidence["daily_rank_one_counts_including_benchmark"] == {"zero": 1}
    assert evidence["selected_daily_vs_zero_counts"] == {"tie": 1}


def test_public_data_preparation_does_not_mutate_source_frames() -> None:
    sales = pd.DataFrame([_m5_row("ITEM_S1_evaluation", [1] * 40)])
    calendar = _m5_calendar(40)
    sales_before = sales.copy(deep=True)
    calendar_before = calendar.copy(deep=True)

    prepare_m5_public_evaluation(sales, calendar, per_stratum=1)

    pd.testing.assert_frame_equal(sales, sales_before)
    pd.testing.assert_frame_equal(calendar, calendar_before)


def test_public_metrics_keep_decimal_values_in_unit_space() -> None:
    sales = pd.DataFrame([_m5_row("ITEM_S1_evaluation", [1, 0] * 35)])
    prepared = prepare_m5_public_evaluation(sales, _m5_calendar(70), per_stratum=1)
    reports = evaluate_public_series(prepared)

    candidate = next(
        item
        for item in reports[0].candidate_evaluations
        if item.candidate.candidate.value == "seasonal_naive_7"
    )

    assert candidate.daily_metrics is not None
    assert isinstance(candidate.daily_metrics.mae, Decimal)
