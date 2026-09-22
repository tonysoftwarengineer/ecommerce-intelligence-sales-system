from __future__ import annotations

from decimal import Decimal

import pytest

from src.product_demand.evaluation_contracts import (
    BaselineCandidate,
    EvaluationAvailability,
    EvaluationUnavailableReason,
    SelectionLabel,
)
from src.product_demand.scenario_pack import (
    PRODUCT_DEMAND_SCENARIOS,
    ScenarioProductStatus,
    calculate_nonzero_average_inflation,
    run_product_demand_scenario_pack,
)


@pytest.fixture(scope="module")
def pack():
    return run_product_demand_scenario_pack()


def test_scenario_pack_contains_all_twelve_approved_patterns() -> None:
    assert len(PRODUCT_DEMAND_SCENARIOS) == 12
    assert len({scenario.name for scenario in PRODUCT_DEMAND_SCENARIOS}) == 12
    assert {scenario.name for scenario in PRODUCT_DEMAND_SCENARIOS} == {
        "stable_daily_level",
        "strong_weekday_seasonality",
        "recent_upward_level_shift",
        "intermittent_confirmed_zero_demand",
        "all_zero_active_product",
        "short_history",
        "unknown_internal_gap",
        "stockout_censored_period",
        "unconfirmed_active_period",
        "invalid_product_isolated_from_valid_product",
        "nonzero_day_average_inflation",
        "equal_error_opposite_bias",
    }


def test_every_declared_scenario_expectation_passes(pack) -> None:
    failures = {check.scenario_name: check.failures for check in pack.checks if not check.passed}

    assert failures == {}


def test_scenario_pack_is_deterministic() -> None:
    assert run_product_demand_scenario_pack() == run_product_demand_scenario_pack()


def test_invalid_product_does_not_block_valid_product(pack) -> None:
    result = pack.result("invalid_product_isolated_from_valid_product")
    products = {product.product_key: product for product in result.products}

    assert products["id:VALID"].status is ScenarioProductStatus.EVALUATED
    assert products["id:INVALID"].status is ScenarioProductStatus.INVALID
    assert products["id:INVALID"].error_reason is EvaluationUnavailableReason.INVALID_TARGET
    assert products["id:VALID"].report is not None
    assert products["id:VALID"].report.daily_leaderboard is not None


def test_unknown_stockout_and_activity_gaps_remain_explicit_evidence(pack) -> None:
    expected = {
        "unknown_internal_gap": EvaluationUnavailableReason.UNKNOWN_TARGET_GAP,
        "stockout_censored_period": EvaluationUnavailableReason.CENSORED_TARGET,
        "unconfirmed_active_period": EvaluationUnavailableReason.PRODUCT_ACTIVITY_UNCONFIRMED,
    }
    for scenario_name, reason in expected.items():
        product = pack.result(scenario_name).products[0]
        assert reason in product.evidence_reasons
        assert product.status is ScenarioProductStatus.EVALUATED


def test_nonzero_day_average_scenario_proves_weekly_inflation() -> None:
    scenario = next(
        scenario
        for scenario in PRODUCT_DEMAND_SCENARIOS
        if scenario.name == "nonzero_day_average_inflation"
    )

    evidence = calculate_nonzero_average_inflation(scenario.products[0])

    assert evidence.nonzero_day_average == Decimal("6")
    assert evidence.implied_seven_day_total == Decimal("42")
    assert evidence.observed_mean_seven_day_total == Decimal("18")
    assert evidence.inflation_units == Decimal("24")


def test_equal_mae_can_hide_opposite_operational_bias(pack) -> None:
    product = pack.result("equal_error_opposite_bias").products[0]
    assert product.report is not None
    evaluations = {
        evaluation.candidate.candidate: evaluation
        for evaluation in product.report.candidate_evaluations
    }
    latest = evaluations[BaselineCandidate.LATEST_VALUE]
    moving_average = evaluations[BaselineCandidate.MOVING_AVERAGE_7]

    assert latest.availability is EvaluationAvailability.EVALUATED
    assert latest.daily_metrics is not None
    assert moving_average.daily_metrics is not None
    assert latest.daily_metrics.mae == moving_average.daily_metrics.mae == Decimal("6")
    assert latest.daily_metrics.mean_bias_units == Decimal("6")
    assert moving_average.daily_metrics.mean_bias_units == Decimal("-6")


def test_all_scenario_reports_remain_evaluation_only(pack) -> None:
    labels = {
        product.report.selection_label
        for result in pack.results
        for product in result.products
        if product.report is not None
    }

    assert labels == {SelectionLabel.EVALUATION_ONLY}


def test_short_history_is_unavailable_instead_of_forcing_a_forecast(pack) -> None:
    product = pack.result("short_history").products[0]

    assert product.status is ScenarioProductStatus.UNAVAILABLE
    assert product.evaluated_candidates == frozenset()
    assert EvaluationUnavailableReason.SHORT_HISTORY in product.evidence_reasons
