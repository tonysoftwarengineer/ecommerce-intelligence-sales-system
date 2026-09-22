"""Safety checks for evaluation-only policy candidates, not release rules."""

from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal

import pytest

from scripts.compare_product_demand_sparse_policies import (
    block_evidence,
    evaluate_series,
    initial_decisions,
    summarize,
    training_sparse,
)
from src.product_demand.contracts import ProductDateStatus
from src.product_demand.evaluation_contracts import (
    EvaluationConfiguration,
    EvaluationSeries,
    EvaluationSeriesPoint,
)
from src.product_demand.metrics import evaluate_product_baselines
from src.product_demand.trust_gate import assess_weekly_zero_skill


def series(values):
    start = date(2025, 1, 1)
    return EvaluationSeries(
        product_key="test-product",
        unit_of_measure="piece",
        points=tuple(
            EvaluationSeriesPoint(
                date=start + timedelta(days=index),
                status=ProductDateStatus.OBSERVED if value else ProductDateStatus.CONFIRMED_ZERO,
                target_units=Decimal(value),
                included=True,
            )
            for index, value in enumerate(values)
        ),
    )


@pytest.mark.parametrize(
    "pairs,passed,reason",
    [
        ([(Decimal(1), Decimal(2))] * 39, True, None),
        ([(Decimal(1), Decimal(2))] * 38, False, "insufficient_consistency_weeks"),
        (
            [(Decimal(1), Decimal(2))] * 26 + [(Decimal(2), Decimal(2))] * 13,
            False,
            "inconsistent_block_skill",
        ),
        ([(Decimal(0), Decimal(0))] * 39, False, "inconsistent_block_skill"),
        (
            [(Decimal(0), Decimal(5))] * 13 + [(Decimal(2), Decimal(1))] * 26,
            False,
            "inconsistent_block_skill",
        ),
    ],
)
def test_consistency_requires_each_block_to_add_value(pairs, passed, reason):
    evidence = block_evidence(pairs)
    assert evidence["passed"] is passed
    assert evidence["reason"] == reason


def test_consistency_uses_recent_blocks_not_ancient_success():
    good = [(Decimal(0), Decimal(5))] * 39
    bad = [(Decimal(2), Decimal(1))] * 39
    assert block_evidence(bad + good)["passed"]
    assert not block_evidence(good + bad)["passed"]


@pytest.mark.parametrize(
    "values,expected",
    [
        ([1] + [0] * 9, True),
        ([1, 1] + [0] * 8, False),
        ([0] * 10, True),
    ],
)
def test_training_only_sparse_boundary(values, expected):
    assert training_sparse(series(values)) is expected


def test_unknown_day_cannot_be_classified_as_zero():
    history = series([1] + [0] * 9)
    unknown = replace(
        history.points[1],
        status=ProductDateStatus.MISSING_UNKNOWN,
        target_units=None,
        included=False,
    )
    history = replace(history, points=(history.points[0], unknown, *history.points[2:]))
    with pytest.raises(ValueError, match="known training targets"):
        training_sparse(history)


def test_candidate_cannot_bypass_failed_current_gate():
    decision = initial_decisions(series([0] * 119))
    assert not any(decision["permissions"].values())


def test_weekly_only_evaluation_preserves_current_weekly_selection():
    history = series([3 + (index % 7) for index in range(210)])
    original = evaluate_product_baselines(history, EvaluationConfiguration())
    decision = initial_decisions(history)
    assert decision["selected_method"] == original.seven_day_winner.value
    assert decision["historical_skill_vs_zero"] == str(
        assess_weekly_zero_skill(original).skill_vs_zero
    )


def test_future_changes_cannot_change_initial_policy_decisions():
    original = series([3] * 210)
    revised = series([3] * 119 + [1000] * 91)
    assert evaluate_series(original)["decision"] == evaluate_series(revised)["decision"]


def test_abstention_accuracy_is_undefined_not_perfect():
    metrics = summarize([], 13)
    assert metrics["coverage_percent"] == 0
    assert metrics["mae"] is None and metrics["wape_percent"] is None
    assert metrics["skill_vs_zero_percent"] is None


def test_opposite_errors_do_not_cancel():
    metrics = summarize([(Decimal(5), Decimal(3)), (Decimal(1), Decimal(3))], 2)
    assert metrics["mae"] == 2
    assert metrics["overforecast_units"] == "2"
    assert metrics["underforecast_units"] == "2"
