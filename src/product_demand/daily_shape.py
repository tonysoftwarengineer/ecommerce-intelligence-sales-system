"""Evaluate whether daily forecast shape adds value beyond a flat weekly allocation."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
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


class DailyShapeEvaluationStatus(str, Enum):
    EVALUATED = "evaluated"
    UNAVAILABLE = "unavailable"


class DailyShapeUnavailableReason(str, Enum):
    NO_WEEKLY_WINNER = "no_weekly_winner"
    NO_DATE_VARYING_CANDIDATE = "no_date_varying_candidate"
    NO_SHARED_FOLDS = "no_shared_folds"
    NO_APPLIED_VARIATION = "no_applied_variation"


class DailyShapeComparison(str, Enum):
    BETTER_THAN_FLAT = "better_than_flat"
    EQUAL_TO_FLAT = "equal_to_flat"
    WORSE_THAN_FLAT = "worse_than_flat"


@dataclass(frozen=True)
class DailyShapeCandidateEvidence:
    """One daily method rescaled to the selected weekly total on shared folds."""

    candidate: BaselineCandidate
    compared_fold_count: int
    varying_fold_count: int
    flat_mean_absolute_daily_error: Decimal
    shaped_mean_absolute_daily_error: Decimal
    skill_vs_flat: Decimal | None
    comparison: DailyShapeComparison
    first_half_skill_vs_flat: Decimal | None
    second_half_skill_vs_flat: Decimal | None
    positive_skill_in_both_halves: bool

    def __post_init__(self) -> None:
        if self.candidate is BaselineCandidate.ZERO:
            raise ValueError("The zero benchmark cannot provide a daily allocation shape")
        if self.compared_fold_count <= 0:
            raise ValueError("Daily-shape evidence requires compared folds")
        if self.varying_fold_count <= 0 or self.varying_fold_count > self.compared_fold_count:
            raise ValueError("Daily-shape evidence requires applied date variation")
        if self.flat_mean_absolute_daily_error < 0:
            raise ValueError("Flat-allocation error must not be negative")
        if self.shaped_mean_absolute_daily_error < 0:
            raise ValueError("Shaped-allocation error must not be negative")
        expected_comparison = _comparison(
            self.shaped_mean_absolute_daily_error,
            self.flat_mean_absolute_daily_error,
        )
        if self.comparison is not expected_comparison:
            raise ValueError("Daily-shape comparison must reflect the two errors")
        expected_skill = _relative_skill(
            self.shaped_mean_absolute_daily_error,
            self.flat_mean_absolute_daily_error,
        )
        if self.skill_vs_flat != expected_skill:
            raise ValueError("Daily-shape skill must use flat allocation as its benchmark")
        expected_both = (
            self.first_half_skill_vs_flat is not None
            and self.first_half_skill_vs_flat > 0
            and self.second_half_skill_vs_flat is not None
            and self.second_half_skill_vs_flat > 0
        )
        if self.positive_skill_in_both_halves is not expected_both:
            raise ValueError("Subperiod consistency must require positive skill in both halves")


@dataclass(frozen=True)
class DailyShapeEvaluation:
    """Evaluation-only daily-shape evidence for one product."""

    product_key: str
    status: DailyShapeEvaluationStatus
    weekly_total_candidate: BaselineCandidate | None
    candidate_evidence: tuple[DailyShapeCandidateEvidence, ...] = ()
    lowest_error_candidate: BaselineCandidate | None = None
    unavailable_reason: DailyShapeUnavailableReason | None = None
    message: str = ""

    def __post_init__(self) -> None:
        if not self.product_key.strip() or not self.message.strip():
            raise ValueError("Daily-shape evaluation requires product identity and a message")
        evidence = tuple(self.candidate_evidence)
        candidates = [item.candidate for item in evidence]
        if len(candidates) != len(set(candidates)):
            raise ValueError("Daily-shape candidate evidence must be unique")
        object.__setattr__(self, "candidate_evidence", evidence)

        if self.status is DailyShapeEvaluationStatus.UNAVAILABLE:
            if evidence or self.lowest_error_candidate is not None:
                raise ValueError("Unavailable daily-shape evaluation cannot select a candidate")
            if self.unavailable_reason is None:
                raise ValueError("Unavailable daily-shape evaluation requires a reason")
            return

        if self.weekly_total_candidate is None or not evidence:
            raise ValueError("Evaluated daily shape requires weekly and daily evidence")
        if self.unavailable_reason is not None:
            raise ValueError("Evaluated daily shape cannot have an unavailable reason")
        if self.lowest_error_candidate not in candidates:
            raise ValueError("Lowest-error daily-shape candidate must reference the evidence")


def evaluate_daily_shape(report: ProductEvaluationReport) -> DailyShapeEvaluation:
    """Compare date-varying daily proportions while holding weekly totals fixed."""
    weekly_candidate = report.seven_day_winner
    if weekly_candidate is None:
        return _unavailable(
            report,
            None,
            DailyShapeUnavailableReason.NO_WEEKLY_WINNER,
            "No evaluated weekly method is available to anchor the daily-shape comparison.",
        )
    weekly = _evaluated_candidate(report, weekly_candidate)
    if weekly is None:
        return _unavailable(
            report,
            weekly_candidate,
            DailyShapeUnavailableReason.NO_WEEKLY_WINNER,
            "The selected weekly method has no evaluated fold evidence.",
        )

    daily_candidates = tuple(
        evaluation
        for evaluation in report.candidate_evaluations
        if evaluation.availability is EvaluationAvailability.EVALUATED
        and evaluation.candidate.granularity is ForecastGranularity.DAILY
        and not evaluation.candidate.benchmark_only
        and _ever_varies(evaluation)
    )
    if not daily_candidates:
        return _unavailable(
            report,
            weekly_candidate,
            DailyShapeUnavailableReason.NO_DATE_VARYING_CANDIDATE,
            "No evaluated daily method produced a changing pattern across the seven dates.",
        )

    maps = (_folds_by_dates(weekly), *(_folds_by_dates(item) for item in daily_candidates))
    shared_dates = set(maps[0])
    for fold_map in maps[1:]:
        shared_dates &= set(fold_map)
    if not shared_dates:
        return _unavailable(
            report,
            weekly_candidate,
            DailyShapeUnavailableReason.NO_SHARED_FOLDS,
            "The weekly and date-varying daily methods share no historical test weeks.",
        )

    ordered_shared_dates = tuple(sorted(shared_dates))
    usable_dates = tuple(
        dates
        for dates in ordered_shared_dates
        if all(_can_apply_shape(maps[0][dates], fold_map[dates]) for fold_map in maps[1:])
    )
    if not usable_dates:
        return _unavailable(
            report,
            weekly_candidate,
            DailyShapeUnavailableReason.NO_APPLIED_VARIATION,
            "Daily proportions could not be applied to any shared nonzero weekly forecast.",
        )

    applied_candidates = tuple(
        (candidate, fold_map)
        for candidate, fold_map in zip(daily_candidates, maps[1:])
        if _applies_variation(maps[0], fold_map, usable_dates)
    )
    if not applied_candidates:
        return _unavailable(
            report,
            weekly_candidate,
            DailyShapeUnavailableReason.NO_APPLIED_VARIATION,
            "Daily methods did not create a changing allocation after weekly reconciliation.",
        )
    evidence = tuple(
        _candidate_evidence(maps[0], fold_map, candidate, usable_dates)
        for candidate, fold_map in applied_candidates
    )

    complexity_ranks = {
        item.candidate.candidate: item.candidate.complexity_rank for item in daily_candidates
    }
    ranked = sorted(
        evidence,
        key=lambda item: (
            item.shaped_mean_absolute_daily_error,
            complexity_ranks[item.candidate],
            item.candidate.value,
        ),
    )
    return DailyShapeEvaluation(
        product_key=report.product_key,
        status=DailyShapeEvaluationStatus.EVALUATED,
        weekly_total_candidate=weekly_candidate,
        candidate_evidence=evidence,
        lowest_error_candidate=ranked[0].candidate,
        message=(
            "Daily methods were reconciled to the selected weekly total and compared with an "
            "equal seven-day allocation. This is evaluation evidence, not daily forecast approval."
        ),
    )


def daily_shape_evaluation_to_dict(evaluation: DailyShapeEvaluation) -> dict[str, object]:
    return {
        "product_key": evaluation.product_key,
        "status": evaluation.status.value,
        "weekly_total_candidate": (
            evaluation.weekly_total_candidate.value
            if evaluation.weekly_total_candidate is not None
            else None
        ),
        "lowest_error_candidate": (
            evaluation.lowest_error_candidate.value
            if evaluation.lowest_error_candidate is not None
            else None
        ),
        "unavailable_reason": (
            evaluation.unavailable_reason.value
            if evaluation.unavailable_reason is not None
            else None
        ),
        "message": evaluation.message,
        "scope": (
            "Daily-shape evaluation only. Positive skill does not approve user-facing daily "
            "forecasts without stability and history policy."
        ),
        "candidates": [_candidate_to_dict(item) for item in evaluation.candidate_evidence],
    }


def evaluate_daily_shape_portfolio(
    reports: Iterable[ProductEvaluationReport],
) -> tuple[DailyShapeEvaluation, ...]:
    return tuple(
        evaluate_daily_shape(report)
        for report in sorted(reports, key=lambda item: item.product_key)
    )


def daily_shape_portfolio_to_dict(
    evaluations: Iterable[DailyShapeEvaluation],
) -> dict[str, object]:
    items = tuple(evaluations)
    statuses = Counter(item.status.value for item in items)
    comparisons: Counter[str] = Counter()
    positive_both = 0
    for item in items:
        if item.lowest_error_candidate is None:
            continue
        best = next(
            evidence
            for evidence in item.candidate_evidence
            if evidence.candidate is item.lowest_error_candidate
        )
        comparisons[best.comparison.value] += 1
        positive_both += best.positive_skill_in_both_halves
    return {
        "scope": (
            "Daily-shape evaluation only. Weekly totals are held constant and no daily output "
            "is approved by this report."
        ),
        "product_count": len(items),
        "status_counts": dict(sorted(statuses.items())),
        "lowest_error_comparison_counts": dict(sorted(comparisons.items())),
        "lowest_error_positive_in_both_halves": positive_both,
        "products": [daily_shape_evaluation_to_dict(item) for item in items],
    }


def _candidate_evidence(
    weekly_folds: dict[tuple[object, ...], RollingOriginFold],
    daily_folds: dict[tuple[object, ...], RollingOriginFold],
    daily_candidate: CandidateEvaluation,
    dates: tuple[tuple[object, ...], ...],
) -> DailyShapeCandidateEvidence:
    flat_error, shaped_error, varying_count = _allocation_errors(
        weekly_folds,
        daily_folds,
        dates,
    )
    first_dates, second_dates = _split_dates(dates)
    first_skill = _period_skill(weekly_folds, daily_folds, first_dates)
    second_skill = _period_skill(weekly_folds, daily_folds, second_dates)
    return DailyShapeCandidateEvidence(
        candidate=daily_candidate.candidate.candidate,
        compared_fold_count=len(dates),
        varying_fold_count=varying_count,
        flat_mean_absolute_daily_error=flat_error,
        shaped_mean_absolute_daily_error=shaped_error,
        skill_vs_flat=_relative_skill(shaped_error, flat_error),
        comparison=_comparison(shaped_error, flat_error),
        first_half_skill_vs_flat=first_skill,
        second_half_skill_vs_flat=second_skill,
        positive_skill_in_both_halves=(
            first_skill is not None
            and first_skill > 0
            and second_skill is not None
            and second_skill > 0
        ),
    )


def _allocation_errors(
    weekly_folds: dict[tuple[object, ...], RollingOriginFold],
    daily_folds: dict[tuple[object, ...], RollingOriginFold],
    dates: tuple[tuple[object, ...], ...],
) -> tuple[Decimal, Decimal, int]:
    flat_errors: list[Decimal] = []
    shaped_errors: list[Decimal] = []
    varying_count = 0
    for key in dates:
        weekly = weekly_folds[key]
        daily = daily_folds[key]
        if daily.predicted_daily_units is None:
            raise ValueError("Daily-shape comparison requires daily predictions")
        if daily.actual_daily_units != weekly.actual_daily_units:
            raise ValueError("Daily-shape comparison requires identical historical truth")
        weekly_total = weekly.predicted_total_units
        flat: tuple[Decimal, ...] = _equal_allocation(weekly_total)
        daily_total = sum(daily.predicted_daily_units, Decimal("0"))
        if weekly_total == 0:
            shaped: tuple[Decimal, ...] = (Decimal("0"),) * 7
        elif daily_total > 0:
            shaped = _proportional_allocation(
                weekly_total,
                daily.predicted_daily_units,
                daily_total,
            )
        else:
            raise ValueError("A nonzero weekly total cannot use an all-zero daily shape")
        varying_count += len(set(shaped)) > 1
        flat_errors.extend(
            abs(predicted - actual) for predicted, actual in zip(flat, weekly.actual_daily_units)
        )
        shaped_errors.extend(
            abs(predicted - actual) for predicted, actual in zip(shaped, weekly.actual_daily_units)
        )
    return _mean(flat_errors), _mean(shaped_errors), varying_count


def _period_skill(
    weekly_folds: dict[tuple[object, ...], RollingOriginFold],
    daily_folds: dict[tuple[object, ...], RollingOriginFold],
    dates: tuple[tuple[object, ...], ...],
) -> Decimal | None:
    if not dates:
        return None
    flat, shaped, _ = _allocation_errors(weekly_folds, daily_folds, dates)
    return _relative_skill(shaped, flat)


def _split_dates(
    dates: tuple[tuple[object, ...], ...],
) -> tuple[tuple[tuple[object, ...], ...], tuple[tuple[object, ...], ...]]:
    if len(dates) < 2:
        return (), ()
    middle = len(dates) // 2
    return dates[:middle], dates[middle:]


def _can_apply_shape(weekly: RollingOriginFold, daily: RollingOriginFold) -> bool:
    if daily.predicted_daily_units is None:
        return False
    return weekly.predicted_total_units == 0 or sum(daily.predicted_daily_units, Decimal("0")) > 0


def _applies_variation(
    weekly_folds: dict[tuple[object, ...], RollingOriginFold],
    daily_folds: dict[tuple[object, ...], RollingOriginFold],
    dates: tuple[tuple[object, ...], ...],
) -> bool:
    return any(
        weekly_folds[key].predicted_total_units > 0
        and daily_folds[key].predicted_daily_units is not None
        and len(set(daily_folds[key].predicted_daily_units or ())) > 1
        for key in dates
    )


def _equal_allocation(total: Decimal) -> tuple[Decimal, ...]:
    repeated = total / Decimal("7")
    first_six = (repeated,) * 6
    return (*first_six, total - sum(first_six, Decimal("0")))


def _proportional_allocation(
    total: Decimal,
    shape: tuple[Decimal, ...],
    shape_total: Decimal,
) -> tuple[Decimal, ...]:
    first_six = tuple(total * value / shape_total for value in shape[:6])
    return (*first_six, total - sum(first_six, Decimal("0")))


def _ever_varies(evaluation: CandidateEvaluation) -> bool:
    return any(
        fold.predicted_daily_units is not None and len(set(fold.predicted_daily_units)) > 1
        for fold in evaluation.folds
    )


def _evaluated_candidate(
    report: ProductEvaluationReport,
    candidate: BaselineCandidate,
) -> CandidateEvaluation | None:
    matches = tuple(
        evaluation
        for evaluation in report.candidate_evaluations
        if evaluation.candidate.candidate is candidate
        and evaluation.availability is EvaluationAvailability.EVALUATED
    )
    return matches[0] if len(matches) == 1 else None


def _folds_by_dates(
    evaluation: CandidateEvaluation,
) -> dict[tuple[object, ...], RollingOriginFold]:
    return {tuple(fold.forecast_dates): fold for fold in evaluation.folds}


def _relative_skill(candidate_error: Decimal, benchmark_error: Decimal) -> Decimal | None:
    if benchmark_error == 0:
        return None
    return (benchmark_error - candidate_error) / benchmark_error


def _comparison(candidate_error: Decimal, benchmark_error: Decimal) -> DailyShapeComparison:
    if candidate_error < benchmark_error:
        return DailyShapeComparison.BETTER_THAN_FLAT
    if candidate_error > benchmark_error:
        return DailyShapeComparison.WORSE_THAN_FLAT
    return DailyShapeComparison.EQUAL_TO_FLAT


def _mean(values: list[Decimal]) -> Decimal:
    if not values:
        raise ValueError("Daily-shape error calculation requires values")
    return sum(values, Decimal("0")) / Decimal(len(values))


def _unavailable(
    report: ProductEvaluationReport,
    weekly_candidate: BaselineCandidate | None,
    reason: DailyShapeUnavailableReason,
    message: str,
) -> DailyShapeEvaluation:
    return DailyShapeEvaluation(
        product_key=report.product_key,
        status=DailyShapeEvaluationStatus.UNAVAILABLE,
        weekly_total_candidate=weekly_candidate,
        unavailable_reason=reason,
        message=message,
    )


def _candidate_to_dict(evidence: DailyShapeCandidateEvidence) -> dict[str, object]:
    return {
        "candidate": evidence.candidate.value,
        "compared_fold_count": evidence.compared_fold_count,
        "varying_fold_count": evidence.varying_fold_count,
        "flat_mean_absolute_daily_error": str(evidence.flat_mean_absolute_daily_error),
        "shaped_mean_absolute_daily_error": str(evidence.shaped_mean_absolute_daily_error),
        "skill_vs_flat": _string_or_none(evidence.skill_vs_flat),
        "comparison": evidence.comparison.value,
        "first_half_skill_vs_flat": _string_or_none(evidence.first_half_skill_vs_flat),
        "second_half_skill_vs_flat": _string_or_none(evidence.second_half_skill_vs_flat),
        "positive_skill_in_both_halves": evidence.positive_skill_in_both_halves,
    }


def _string_or_none(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None
