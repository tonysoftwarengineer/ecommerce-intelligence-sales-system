from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from src.product_demand.contracts import ProductDateStatus
from src.product_demand.evaluation_contracts import (
    BaselineCandidate,
    EvaluationConfiguration,
    EvaluationSeries,
    EvaluationSeriesPoint,
    ForecastGranularity,
)
from src.product_demand.metrics import evaluate_product_baselines
from src.product_demand.trust_gate import (
    WeeklyZeroSkillGateStatus,
    assess_weekly_zero_skill,
    assess_weekly_zero_skill_portfolio,
    weekly_zero_skill_evidence_to_dict,
    weekly_zero_skill_portfolio_to_dict,
)


def _series(values: list[int], product_key: str = "id:A") -> EvaluationSeries:
    start = date(2025, 1, 1)
    return EvaluationSeries(
        product_key=product_key,
        unit_of_measure="piece",
        points=tuple(
            EvaluationSeriesPoint(
                date=start + timedelta(days=offset),
                status=(
                    ProductDateStatus.CONFIRMED_ZERO if value == 0 else ProductDateStatus.OBSERVED
                ),
                target_units=Decimal(value),
                included=True,
            )
            for offset, value in enumerate(values)
        ),
    )


def test_weekly_method_passes_only_when_it_beats_zero_on_shared_folds() -> None:
    report = evaluate_product_baselines(_series([3] * 70), EvaluationConfiguration())

    evidence = assess_weekly_zero_skill(report)

    assert evidence.status is WeeklyZeroSkillGateStatus.PASSED
    assert evidence.passed is True
    assert evidence.selected_candidate is BaselineCandidate.LAST_WEEK_TOTAL
    assert evidence.benchmark_candidate is BaselineCandidate.ZERO
    assert evidence.benchmark_granularity is ForecastGranularity.SEVEN_DAY_TOTAL
    assert evidence.compared_fold_count == 6
    assert evidence.selected_mean_absolute_total_error == 0
    assert evidence.zero_mean_absolute_total_error == 21
    assert evidence.skill_vs_zero == 1
    assert "only the zero-skill gate" in evidence.message


def test_sparse_method_fails_when_zero_has_lower_weekly_error() -> None:
    values = [10 if index % 28 == 27 else 0 for index in range(140)]
    report = evaluate_product_baselines(_series(values, "id:SPARSE"), EvaluationConfiguration())

    evidence = assess_weekly_zero_skill(report)

    assert evidence.status is WeeklyZeroSkillGateStatus.FAILED
    assert evidence.passed is False
    assert evidence.selected_candidate is BaselineCandidate.SBA_CROSTON
    assert evidence.skill_vs_zero == Decimal("-0.4750000000000000000000000")
    assert evidence.selected_mean_absolute_total_error is not None
    assert evidence.zero_mean_absolute_total_error is not None
    assert evidence.selected_mean_absolute_total_error > evidence.zero_mean_absolute_total_error
    assert "Do not show a numeric forecast" in evidence.message


def test_perfect_zero_benchmark_cannot_be_claimed_as_positive_skill() -> None:
    report = evaluate_product_baselines(_series([0] * 70, "id:ZERO"), EvaluationConfiguration())

    evidence = assess_weekly_zero_skill(report)

    assert evidence.status is WeeklyZeroSkillGateStatus.FAILED
    assert evidence.zero_mean_absolute_total_error == 0
    assert evidence.selected_mean_absolute_total_error == 0
    assert evidence.skill_vs_zero is None
    assert "did not prove additional forecasting value" in evidence.message


def test_gate_is_unavailable_when_zero_was_not_evaluated() -> None:
    report = evaluate_product_baselines(
        _series([3] * 70),
        EvaluationConfiguration(),
        candidates=(
            BaselineCandidate.LAST_WEEK_TOTAL,
            BaselineCandidate.MEAN_4_WEEKLY_TOTALS,
        ),
    )

    evidence = assess_weekly_zero_skill(report)

    assert evidence.status is WeeklyZeroSkillGateStatus.UNAVAILABLE
    assert evidence.passed is False
    assert evidence.selected_candidate is BaselineCandidate.LAST_WEEK_TOTAL
    assert evidence.compared_fold_count == 0
    assert evidence.skill_vs_zero is None


def test_gate_serialization_states_its_limited_scope() -> None:
    report = evaluate_product_baselines(_series([3] * 70), EvaluationConfiguration())

    payload = weekly_zero_skill_evidence_to_dict(assess_weekly_zero_skill(report))

    assert payload["status"] == "passed"
    assert payload["passed"] is True
    assert payload["benchmark_candidate"] == "zero"
    assert payload["benchmark_granularity"] == "seven_day_total"
    assert payload["skill_vs_zero"] == "1"
    assert isinstance(payload["scope"], str)
    assert "does not approve" in payload["scope"]


def test_portfolio_gate_preserves_product_failures_beside_passes() -> None:
    stable = evaluate_product_baselines(_series([3] * 70, "id:STABLE"), EvaluationConfiguration())
    sparse_values = [10 if index % 28 == 27 else 0 for index in range(140)]
    sparse = evaluate_product_baselines(
        _series(sparse_values, "id:SPARSE"), EvaluationConfiguration()
    )

    evidence = assess_weekly_zero_skill_portfolio((stable, sparse))
    payload = weekly_zero_skill_portfolio_to_dict(evidence)

    assert [item.product_key for item in evidence] == ["id:SPARSE", "id:STABLE"]
    assert payload["product_count"] == 2
    assert payload["status_counts"] == {"failed": 1, "passed": 1}
    products = payload["products"]
    assert isinstance(products, list)
    assert len(products) == 2
