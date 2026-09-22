from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from src.product_demand.contracts import ProductDateStatus
from src.product_demand.evaluation_contracts import (
    BaselineCandidate,
    EvaluationConfiguration,
    EvaluationSeries,
    EvaluationSeriesPoint,
)
from src.product_demand.history_sensitivity import (
    DEFAULT_HISTORY_CHECKPOINTS,
    HistoryCheckpointStatus,
    HistoryCheckpointUnavailableReason,
    evaluate_history_sensitivity,
    evaluate_history_sensitivity_portfolio,
    history_sensitivity_portfolio_to_dict,
)
from src.product_demand.metrics import evaluate_product_baselines


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


def _report(values: list[int], product_key: str = "id:A", candidates=None):
    return evaluate_product_baselines(
        _series(values, product_key),
        EvaluationConfiguration(),
        candidates=candidates,
    )


def test_default_checkpoints_select_before_one_fixed_holdout() -> None:
    result = evaluate_history_sensitivity(_report([3] * 350))

    assert tuple(item.selection_fold_count for item in result.checkpoints) == (
        DEFAULT_HISTORY_CHECKPOINTS
    )
    assert result.holdout_fold_count == 13
    assert result.shared_weekly_fold_count >= 39
    assert all(item.status is HistoryCheckpointStatus.EVALUATED for item in result.checkpoints)
    assert all(
        item.selected_candidate is BaselineCandidate.LAST_WEEK_TOTAL for item in result.checkpoints
    )
    assert all(item.selection_mean_absolute_total_error == 0 for item in result.checkpoints)
    assert all(item.holdout_selected_mean_absolute_total_error == 0 for item in result.checkpoints)
    assert all(item.holdout_zero_mean_absolute_total_error == 21 for item in result.checkpoints)
    assert all(item.holdout_skill_vs_zero == 1 for item in result.checkpoints)
    assert all(item.passed_zero_gate is True for item in result.checkpoints)


def test_changing_only_holdout_actuals_cannot_change_pre_holdout_method_selection() -> None:
    ordinary = evaluate_history_sensitivity(_report([3] * 350))
    shocked = evaluate_history_sensitivity(_report([3] * 259 + [100] * 91))

    assert [item.selected_candidate for item in ordinary.checkpoints] == [
        item.selected_candidate for item in shocked.checkpoints
    ]
    assert [item.selection_mean_absolute_total_error for item in ordinary.checkpoints] == [
        item.selection_mean_absolute_total_error for item in shocked.checkpoints
    ]
    assert [item.holdout_selected_mean_absolute_total_error for item in ordinary.checkpoints] != [
        item.holdout_selected_mean_absolute_total_error for item in shocked.checkpoints
    ]


def test_checkpoint_is_unavailable_when_selection_and_holdout_folds_do_not_fit() -> None:
    result = evaluate_history_sensitivity(_report([3] * 126), checkpoints=(3, 6))

    assert all(item.status is HistoryCheckpointStatus.UNAVAILABLE for item in result.checkpoints)
    assert all(
        item.unavailable_reason is HistoryCheckpointUnavailableReason.INSUFFICIENT_SHARED_FOLDS
        for item in result.checkpoints
    )
    assert all(item.selected_candidate is None for item in result.checkpoints)


def test_zero_benchmark_is_required_for_every_checkpoint() -> None:
    result = evaluate_history_sensitivity(
        _report(
            [3] * 350,
            candidates=(
                BaselineCandidate.LAST_WEEK_TOTAL,
                BaselineCandidate.MEAN_4_WEEKLY_TOTALS,
                BaselineCandidate.SBA_CROSTON,
            ),
        )
    )

    assert all(item.status is HistoryCheckpointStatus.UNAVAILABLE for item in result.checkpoints)
    assert all(
        item.unavailable_reason is HistoryCheckpointUnavailableReason.NO_ZERO_BENCHMARK
        for item in result.checkpoints
    )


def test_perfect_zero_holdout_cannot_pass_or_invent_relative_skill() -> None:
    result = evaluate_history_sensitivity(_report([0] * 350, "id:ZERO"))

    assert all(item.status is HistoryCheckpointStatus.EVALUATED for item in result.checkpoints)
    assert all(item.holdout_zero_mean_absolute_total_error == 0 for item in result.checkpoints)
    assert all(item.holdout_skill_vs_zero is None for item in result.checkpoints)
    assert all(item.passed_zero_gate is False for item in result.checkpoints)


def test_portfolio_serialization_is_deterministic_and_retains_failures() -> None:
    reports = (_report([0] * 350, "id:ZERO"), _report([3] * 350, "id:ACTIVE"))
    first = evaluate_history_sensitivity_portfolio(reports)
    second = evaluate_history_sensitivity_portfolio(reports)

    assert first == second
    payload = history_sensitivity_portfolio_to_dict(
        first,
        {"id:ACTIVE": "active", "id:ZERO": "inactive"},
    )
    assert payload["product_count"] == 2
    assert payload["checkpoint_selection_folds"] == [3, 6, 13, 26]
    checkpoint = payload["checkpoint_summaries"]["3"]
    assert checkpoint["status_counts"] == {"evaluated": 2}
    assert checkpoint["zero_gate_passed"] == 1
    assert checkpoint["zero_gate_failed"] == 1
    assert len(payload["products"]) == 2
    assert payload["strata"]["active"]["checkpoint_summaries"]["3"]["zero_gate_passed"] == 1
    assert payload["strata"]["inactive"]["checkpoint_summaries"]["3"]["zero_gate_failed"] == 1
    assert "not accepted production thresholds" in payload["scope"]
