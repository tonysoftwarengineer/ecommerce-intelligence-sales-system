"""History-fold sensitivity evidence for weekly product-demand candidates."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from src.product_demand.evaluation_contracts import (
    BaselineCandidate,
    CandidateEvaluation,
    EvaluationAvailability,
    ForecastGranularity,
    ProductEvaluationReport,
    RollingOriginFold,
)

DEFAULT_HISTORY_CHECKPOINTS = (3, 6, 13, 26)
DEFAULT_HOLDOUT_FOLDS = 13


class HistoryCheckpointStatus(str, Enum):
    EVALUATED = "evaluated"
    UNAVAILABLE = "unavailable"


class HistoryCheckpointUnavailableReason(str, Enum):
    NO_WEEKLY_CANDIDATES = "no_weekly_candidates"
    NO_ZERO_BENCHMARK = "no_zero_benchmark"
    INSUFFICIENT_SHARED_FOLDS = "insufficient_shared_folds"


@dataclass(frozen=True)
class HistoryCheckpointEvidence:
    """Method-selection evidence from N folds, tested on one fixed future holdout."""

    selection_fold_count: int
    holdout_fold_count: int
    status: HistoryCheckpointStatus
    selected_candidate: BaselineCandidate | None
    selection_mean_absolute_total_error: Decimal | None
    holdout_selected_mean_absolute_total_error: Decimal | None
    holdout_zero_mean_absolute_total_error: Decimal | None
    holdout_skill_vs_zero: Decimal | None
    passed_zero_gate: bool | None
    unavailable_reason: HistoryCheckpointUnavailableReason | None
    message: str

    def __post_init__(self) -> None:
        if self.selection_fold_count <= 0 or self.holdout_fold_count <= 0:
            raise ValueError("History sensitivity fold counts must be positive")
        if not self.message.strip():
            raise ValueError("History sensitivity evidence requires a message")

        metrics = (
            self.selection_mean_absolute_total_error,
            self.holdout_selected_mean_absolute_total_error,
            self.holdout_zero_mean_absolute_total_error,
        )
        if self.status is HistoryCheckpointStatus.UNAVAILABLE:
            if self.unavailable_reason is None:
                raise ValueError("Unavailable checkpoints require a reason")
            if self.selected_candidate is not None or any(value is not None for value in metrics):
                raise ValueError("Unavailable checkpoints cannot claim method evidence")
            if self.holdout_skill_vs_zero is not None or self.passed_zero_gate is not None:
                raise ValueError("Unavailable checkpoints cannot claim a gate outcome")
            return

        if self.unavailable_reason is not None:
            raise ValueError("Evaluated checkpoints cannot have an unavailable reason")
        if self.selected_candidate is None or self.selected_candidate is BaselineCandidate.ZERO:
            raise ValueError("Evaluated checkpoints require a non-benchmark method")
        if any(value is None for value in metrics):
            raise ValueError("Evaluated checkpoints require selection and holdout errors")
        if any(value is not None and value < 0 for value in metrics):
            raise ValueError("History sensitivity errors must not be negative")

        zero_error = self.holdout_zero_mean_absolute_total_error
        selected_error = self.holdout_selected_mean_absolute_total_error
        if zero_error is None or selected_error is None:
            raise AssertionError("Evaluated checkpoint errors were not retained")
        if zero_error == 0:
            if self.holdout_skill_vs_zero is not None or self.passed_zero_gate is not False:
                raise ValueError(
                    "A perfect zero holdout requires undefined skill and a failed gate"
                )
            return

        expected_skill = (zero_error - selected_error) / zero_error
        if self.holdout_skill_vs_zero != expected_skill:
            raise ValueError("Holdout skill must be calculated against zero on identical folds")
        if self.passed_zero_gate is not (expected_skill > 0):
            raise ValueError("Holdout gate outcome must require strictly positive skill")


@dataclass(frozen=True)
class ProductHistorySensitivity:
    product_key: str
    shared_weekly_fold_count: int
    holdout_fold_count: int
    checkpoints: tuple[HistoryCheckpointEvidence, ...]
    message: str

    def __post_init__(self) -> None:
        if not self.product_key.strip() or not self.message.strip():
            raise ValueError("History sensitivity requires product identity and a message")
        if self.shared_weekly_fold_count < 0 or self.holdout_fold_count <= 0:
            raise ValueError("History sensitivity fold counts are invalid")
        checkpoints = tuple(self.checkpoints)
        counts = [item.selection_fold_count for item in checkpoints]
        if counts != sorted(counts) or len(counts) != len(set(counts)):
            raise ValueError("History checkpoints must be unique and ascending")
        if any(item.holdout_fold_count != self.holdout_fold_count for item in checkpoints):
            raise ValueError("Every checkpoint must use the same holdout size")
        object.__setattr__(self, "checkpoints", checkpoints)


def evaluate_history_sensitivity(
    report: ProductEvaluationReport,
    checkpoints: Iterable[int] = DEFAULT_HISTORY_CHECKPOINTS,
    holdout_folds: int = DEFAULT_HOLDOUT_FOLDS,
) -> ProductHistorySensitivity:
    """Select on varying fold counts and score each choice on one fixed holdout."""
    checkpoint_values = _validated_checkpoints(checkpoints)
    if holdout_folds <= 0:
        raise ValueError("holdout_folds must be positive")

    evaluated = tuple(
        evaluation
        for evaluation in report.candidate_evaluations
        if evaluation.availability is EvaluationAvailability.EVALUATED
    )
    nonbenchmark = tuple(
        item
        for item in evaluated
        if item.candidate.granularity is ForecastGranularity.SEVEN_DAY_TOTAL
        and not item.candidate.benchmark_only
    )
    zero = next(
        (item for item in evaluated if item.candidate.candidate is BaselineCandidate.ZERO),
        None,
    )

    if not nonbenchmark:
        return _all_unavailable(
            report,
            checkpoint_values,
            holdout_folds,
            HistoryCheckpointUnavailableReason.NO_WEEKLY_CANDIDATES,
            "No non-benchmark weekly candidates have evaluated fold evidence.",
        )
    if zero is None:
        return _all_unavailable(
            report,
            checkpoint_values,
            holdout_folds,
            HistoryCheckpointUnavailableReason.NO_ZERO_BENCHMARK,
            "The weekly zero benchmark is unavailable, so holdout skill cannot be measured.",
        )

    candidates = (*nonbenchmark, zero)
    fold_maps = {item.candidate.candidate: _folds_by_dates(item) for item in candidates}
    shared_keys = set.intersection(*(set(items) for items in fold_maps.values()))
    ordered_keys = tuple(sorted(shared_keys))
    selection_pool = ordered_keys[:-holdout_folds] if len(ordered_keys) > holdout_folds else ()
    holdout_keys = ordered_keys[-holdout_folds:] if len(ordered_keys) >= holdout_folds else ()

    evidence = tuple(
        _evaluate_checkpoint(
            checkpoint,
            holdout_folds,
            selection_pool,
            holdout_keys,
            nonbenchmark,
            zero,
            fold_maps,
        )
        for checkpoint in checkpoint_values
    )
    return ProductHistorySensitivity(
        product_key=report.product_key,
        shared_weekly_fold_count=len(ordered_keys),
        holdout_fold_count=holdout_folds,
        checkpoints=evidence,
        message=(
            "Each checkpoint selected a weekly method from the immediately preceding folds and "
            "was judged on the same later holdout. Results are sensitivity evidence, not an "
            "accepted production history threshold."
        ),
    )


def evaluate_history_sensitivity_portfolio(
    reports: Iterable[ProductEvaluationReport],
    checkpoints: Iterable[int] = DEFAULT_HISTORY_CHECKPOINTS,
    holdout_folds: int = DEFAULT_HOLDOUT_FOLDS,
) -> tuple[ProductHistorySensitivity, ...]:
    checkpoint_values = _validated_checkpoints(checkpoints)
    return tuple(
        evaluate_history_sensitivity(report, checkpoint_values, holdout_folds)
        for report in sorted(reports, key=lambda item: item.product_key)
    )


def history_sensitivity_product_to_dict(
    result: ProductHistorySensitivity,
) -> dict[str, object]:
    return {
        "product_key": result.product_key,
        "shared_weekly_fold_count": result.shared_weekly_fold_count,
        "holdout_fold_count": result.holdout_fold_count,
        "scope": (
            "Fixed-holdout history sensitivity only. This does not accept a production trust "
            "threshold or authorize a user-facing forecast."
        ),
        "message": result.message,
        "checkpoints": [_checkpoint_to_dict(item) for item in result.checkpoints],
    }


def history_sensitivity_portfolio_to_dict(
    results: Iterable[ProductHistorySensitivity],
    strata_by_product: Mapping[str, str] | None = None,
) -> dict[str, object]:
    items = tuple(results)
    checkpoint_counts = sorted(
        {checkpoint.selection_fold_count for item in items for checkpoint in item.checkpoints}
    )
    payload: dict[str, object] = {
        "scope": (
            "Fixed-holdout history sensitivity only. Checkpoints are experimental and are not "
            "accepted production thresholds."
        ),
        "product_count": len(items),
        "checkpoint_selection_folds": checkpoint_counts,
        "checkpoint_summaries": _checkpoint_summaries(items, checkpoint_counts),
        "products": [history_sensitivity_product_to_dict(item) for item in items],
    }
    if strata_by_product is not None:
        missing = sorted(
            item.product_key for item in items if item.product_key not in strata_by_product
        )
        if missing:
            raise ValueError(f"History sensitivity strata are missing products: {missing}")
        strata: dict[str, object] = {}
        for stratum in sorted({strata_by_product[item.product_key] for item in items}):
            members = tuple(
                item for item in items if strata_by_product[item.product_key] == stratum
            )
            strata[stratum] = {
                "product_count": len(members),
                "checkpoint_summaries": _checkpoint_summaries(members, checkpoint_counts),
            }
        payload["strata"] = strata
    return payload


def _checkpoint_summaries(
    items: tuple[ProductHistorySensitivity, ...],
    checkpoint_counts: list[int],
) -> dict[str, object]:
    summaries: dict[str, object] = {}
    for count in checkpoint_counts:
        checkpoints = tuple(
            checkpoint
            for item in items
            for checkpoint in item.checkpoints
            if checkpoint.selection_fold_count == count
        )
        evaluated = tuple(
            item for item in checkpoints if item.status is HistoryCheckpointStatus.EVALUATED
        )
        summaries[str(count)] = {
            "status_counts": dict(
                sorted(Counter(item.status.value for item in checkpoints).items())
            ),
            "selected_candidate_counts": dict(
                sorted(
                    Counter(
                        item.selected_candidate.value
                        for item in evaluated
                        if item.selected_candidate is not None
                    ).items()
                )
            ),
            "zero_gate_passed": sum(item.passed_zero_gate is True for item in evaluated),
            "zero_gate_failed": sum(item.passed_zero_gate is False for item in evaluated),
            "holdout_skill_vs_zero": _distribution(
                item.holdout_skill_vs_zero
                for item in evaluated
                if item.holdout_skill_vs_zero is not None
            ),
        }
    return summaries


def _evaluate_checkpoint(
    checkpoint: int,
    holdout_folds: int,
    selection_pool: tuple[tuple[object, ...], ...],
    holdout_keys: tuple[tuple[object, ...], ...],
    candidates: tuple[CandidateEvaluation, ...],
    zero: CandidateEvaluation,
    fold_maps: dict[BaselineCandidate, dict[tuple[object, ...], RollingOriginFold]],
) -> HistoryCheckpointEvidence:
    if len(selection_pool) < checkpoint or len(holdout_keys) != holdout_folds:
        return HistoryCheckpointEvidence(
            selection_fold_count=checkpoint,
            holdout_fold_count=holdout_folds,
            status=HistoryCheckpointStatus.UNAVAILABLE,
            selected_candidate=None,
            selection_mean_absolute_total_error=None,
            holdout_selected_mean_absolute_total_error=None,
            holdout_zero_mean_absolute_total_error=None,
            holdout_skill_vs_zero=None,
            passed_zero_gate=None,
            unavailable_reason=HistoryCheckpointUnavailableReason.INSUFFICIENT_SHARED_FOLDS,
            message=(
                f"At least {checkpoint + holdout_folds} shared weekly folds are required to "
                "separate method selection from the fixed holdout."
            ),
        )

    selection_keys = selection_pool[-checkpoint:]
    selected = min(
        candidates,
        key=lambda item: _selection_rank(item, fold_maps[item.candidate.candidate], selection_keys),
    )
    selected_map = fold_maps[selected.candidate.candidate]
    zero_map = fold_maps[zero.candidate.candidate]
    selection_error = _mean_absolute_total_error(selected_map, selection_keys)
    holdout_selected_error = _mean_absolute_total_error(selected_map, holdout_keys)
    holdout_zero_error = _mean_absolute_total_error(zero_map, holdout_keys)
    skill = (
        None
        if holdout_zero_error == 0
        else (holdout_zero_error - holdout_selected_error) / holdout_zero_error
    )
    passed = skill is not None and skill > 0
    return HistoryCheckpointEvidence(
        selection_fold_count=checkpoint,
        holdout_fold_count=holdout_folds,
        status=HistoryCheckpointStatus.EVALUATED,
        selected_candidate=selected.candidate.candidate,
        selection_mean_absolute_total_error=selection_error,
        holdout_selected_mean_absolute_total_error=holdout_selected_error,
        holdout_zero_mean_absolute_total_error=holdout_zero_error,
        holdout_skill_vs_zero=skill,
        passed_zero_gate=passed,
        unavailable_reason=None,
        message=(
            "The method was selected without seeing the fixed holdout and then compared with "
            "forecasting zero on those same future weeks."
        ),
    )


def _all_unavailable(
    report: ProductEvaluationReport,
    checkpoints: tuple[int, ...],
    holdout_folds: int,
    reason: HistoryCheckpointUnavailableReason,
    message: str,
) -> ProductHistorySensitivity:
    return ProductHistorySensitivity(
        product_key=report.product_key,
        shared_weekly_fold_count=0,
        holdout_fold_count=holdout_folds,
        checkpoints=tuple(
            HistoryCheckpointEvidence(
                selection_fold_count=count,
                holdout_fold_count=holdout_folds,
                status=HistoryCheckpointStatus.UNAVAILABLE,
                selected_candidate=None,
                selection_mean_absolute_total_error=None,
                holdout_selected_mean_absolute_total_error=None,
                holdout_zero_mean_absolute_total_error=None,
                holdout_skill_vs_zero=None,
                passed_zero_gate=None,
                unavailable_reason=reason,
                message=message,
            )
            for count in checkpoints
        ),
        message=message,
    )


def _selection_rank(
    evaluation: CandidateEvaluation,
    folds: dict[tuple[object, ...], RollingOriginFold],
    keys: tuple[tuple[object, ...], ...],
) -> tuple[Decimal, Decimal, int, str]:
    errors = tuple(_total_error(folds[key]) for key in keys)
    return (
        _mean(tuple(abs(error) for error in errors)),
        abs(_mean(errors)),
        evaluation.candidate.complexity_rank,
        evaluation.candidate.candidate.value,
    )


def _mean_absolute_total_error(
    folds: dict[tuple[object, ...], RollingOriginFold],
    keys: tuple[tuple[object, ...], ...],
) -> Decimal:
    return _mean(tuple(abs(_total_error(folds[key])) for key in keys))


def _total_error(fold: RollingOriginFold) -> Decimal:
    return fold.predicted_total_units - sum(fold.actual_daily_units, Decimal("0"))


def _mean(values: tuple[Decimal, ...]) -> Decimal:
    if not values:
        raise ValueError("A mean requires at least one value")
    return sum(values, Decimal("0")) / Decimal(len(values))


def _folds_by_dates(
    evaluation: CandidateEvaluation,
) -> dict[tuple[object, ...], RollingOriginFold]:
    return {tuple(fold.forecast_dates): fold for fold in evaluation.folds}


def _validated_checkpoints(checkpoints: Iterable[int]) -> tuple[int, ...]:
    values = tuple(checkpoints)
    if not values or any(
        not isinstance(value, int) or isinstance(value, bool) or value <= 0 for value in values
    ):
        raise ValueError("History checkpoints must be unique positive integers")
    if len(values) != len(set(values)):
        raise ValueError("History checkpoints must be unique positive integers")
    return tuple(sorted(values))


def _distribution(values: Iterable[Decimal]) -> dict[str, object] | None:
    ordered = sorted(values)
    if not ordered:
        return None
    middle = len(ordered) // 2
    median = (
        ordered[middle]
        if len(ordered) % 2
        else (ordered[middle - 1] + ordered[middle]) / Decimal("2")
    )
    return {
        "count": len(ordered),
        "minimum": str(ordered[0]),
        "median": str(median),
        "maximum": str(ordered[-1]),
    }


def _checkpoint_to_dict(evidence: HistoryCheckpointEvidence) -> dict[str, object]:
    return {
        "selection_fold_count": evidence.selection_fold_count,
        "holdout_fold_count": evidence.holdout_fold_count,
        "status": evidence.status.value,
        "selected_candidate": (
            evidence.selected_candidate.value if evidence.selected_candidate is not None else None
        ),
        "selection_mean_absolute_total_error": _string_or_none(
            evidence.selection_mean_absolute_total_error
        ),
        "holdout_selected_mean_absolute_total_error": _string_or_none(
            evidence.holdout_selected_mean_absolute_total_error
        ),
        "holdout_zero_mean_absolute_total_error": _string_or_none(
            evidence.holdout_zero_mean_absolute_total_error
        ),
        "holdout_skill_vs_zero": _string_or_none(evidence.holdout_skill_vs_zero),
        "passed_zero_gate": evidence.passed_zero_gate,
        "unavailable_reason": (
            evidence.unavailable_reason.value if evidence.unavailable_reason is not None else None
        ),
        "message": evidence.message,
    }


def _string_or_none(value: Decimal | None) -> str | None:
    return None if value is None else str(value)
