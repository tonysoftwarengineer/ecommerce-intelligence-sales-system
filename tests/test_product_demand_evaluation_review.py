from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from src.product_demand.evaluation_review import (
    review_evidence_to_dict,
    review_public_evaluations,
)
from src.product_demand.public_data_evaluation import (
    evaluate_public_series,
    prepare_m5_public_evaluation,
)


def _calendar(days: int) -> pd.DataFrame:
    start = date(2020, 1, 1)
    return pd.DataFrame(
        {
            "d": [f"d_{index}" for index in range(1, days + 1)],
            "date": [start + timedelta(days=index - 1) for index in range(1, days + 1)],
        }
    )


def _row(source_id: str, values: list[int]) -> dict[str, object]:
    return {
        "id": source_id,
        "item_id": source_id,
        "dept_id": "D1",
        "cat_id": "C1",
        "store_id": "S1",
        "state_id": "CA",
        **{f"d_{index}": value for index, value in enumerate(values, start=1)},
    }


def test_review_exposes_relative_skill_bias_stability_and_granularity() -> None:
    days = 84
    sales = pd.DataFrame([_row("STABLE", [3] * days)])
    prepared = prepare_m5_public_evaluation(sales, _calendar(days), per_stratum=1)
    reports = evaluate_public_series(prepared)

    review = review_public_evaluations(prepared, reports)
    product = review.products[0]

    assert product.daily_winner.value == "latest_value"
    assert product.daily_rmsse is None
    assert product.daily_skill_vs_zero == 1
    assert product.daily_bias_fraction_of_mean_actual == 0
    assert product.selected_daily_fold_win_rate == 1
    assert product.selected_daily_fold_win_rate_including_zero == 1
    assert product.zero_fold_win_rate == 0
    assert product.daily_subperiod_stable is True
    assert product.selected_daily_ever_varied_within_week is False
    assert product.weekly_skill_vs_zero == 1
    assert product.weekly_skill_vs_last_week_total is None
    assert product.weekly_bias_fraction_of_mean_actual == 0
    assert product.weekly_subperiod_stable is True
    assert product.daily_total_vs_weekly == "equal_error"


def test_review_summary_preserves_rmsse_undefined_instead_of_calling_it_failure() -> None:
    days = 84
    sales = pd.DataFrame([_row("STABLE", [3] * days)])
    prepared = prepare_m5_public_evaluation(sales, _calendar(days), per_stratum=1)
    review = review_public_evaluations(prepared, evaluate_public_series(prepared))

    evidence = review_evidence_to_dict(review)

    assert evidence["daily_rmsse_state_counts"] == {"undefined": 1}
    assert evidence["daily_skill_vs_zero"]["median"] == "1"
    assert evidence["daily_subperiod_stable_products"] == 1
    assert evidence["date_varying_daily_winner_products"] == 0
    assert evidence["weekly_skill_vs_zero"]["median"] == "1"
    assert evidence["weekly_subperiod_stable_products"] == 1
    assert evidence["daily_total_vs_weekly_counts"] == {"equal_error": 1}


def test_review_detects_changing_subperiod_winners() -> None:
    values = ([2] * 84) + ([2, 2, 2, 2, 2, 10, 10] * 8)
    sales = pd.DataFrame([_row("SHIFT", values)])
    prepared = prepare_m5_public_evaluation(
        sales,
        _calendar(len(values)),
        per_stratum=1,
    )

    review = review_public_evaluations(prepared, evaluate_public_series(prepared))
    product = review.products[0]

    assert product.shared_daily_folds >= 3
    assert product.daily_first_half_winner != product.daily_second_half_winner
    assert product.daily_subperiod_stable is False


def test_review_requires_reports_for_the_exact_prepared_products() -> None:
    sales = pd.DataFrame([_row("A", [1] * 84), _row("B", [2] * 84)])
    prepared = prepare_m5_public_evaluation(sales, _calendar(84), per_stratum=2)
    reports = evaluate_public_series(prepared)

    with pytest.raises(ValueError, match="must match"):
        review_public_evaluations(prepared, reports[:1])


def test_review_is_deterministic() -> None:
    values = [1, 0, 0, 2, 0, 0, 0] * 12
    sales = pd.DataFrame([_row("SPARSE", values)])
    prepared = prepare_m5_public_evaluation(sales, _calendar(len(values)), per_stratum=1)
    reports = evaluate_public_series(prepared)

    first = review_public_evaluations(prepared, reports)
    second = review_public_evaluations(prepared, reports)

    assert first == second
