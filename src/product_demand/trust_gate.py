"""Evidence gates that remain separate from product-demand model selection."""

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


class WeeklyZeroSkillGateStatus(str, Enum):
    """Outcome of one necessary, but not sufficient, weekly trust check."""

    PASSED = "passed"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class WeeklyZeroSkillEvidence:
    """Shared-fold evidence that a weekly method adds value over forecasting zero."""

    product_key: str
    status: WeeklyZeroSkillGateStatus
    selected_candidate: BaselineCandidate | None
    compared_fold_count: int
    selected_mean_absolute_total_error: Decimal | None
    zero_mean_absolute_total_error: Decimal | None
    skill_vs_zero: Decimal | None
    message: str
    benchmark_candidate: BaselineCandidate = BaselineCandidate.ZERO
    benchmark_granularity: ForecastGranularity = ForecastGranularity.SEVEN_DAY_TOTAL

    def __post_init__(self) -> None:
        if not self.product_key.strip() or not self.message.strip():
            raise ValueError("Weekly zero-skill evidence requires product identity and a message")
        if self.compared_fold_count < 0:
            raise ValueError("compared_fold_count must not be negative")
        if self.benchmark_candidate is not BaselineCandidate.ZERO:
            raise ValueError("The weekly zero-skill gate requires the zero benchmark")
        if self.benchmark_granularity is not ForecastGranularity.SEVEN_DAY_TOTAL:
            raise ValueError("The zero-skill gate must compare seven-day totals")

        if self.status is WeeklyZeroSkillGateStatus.UNAVAILABLE:
            if self.compared_fold_count != 0:
                raise ValueError("Unavailable gate evidence cannot claim compared folds")
            if any(
                value is not None
                for value in (
                    self.selected_mean_absolute_total_error,
                    self.zero_mean_absolute_total_error,
                    self.skill_vs_zero,
                )
            ):
                raise ValueError("Unavailable gate evidence cannot contain comparison metrics")
            return

        if self.selected_candidate is None or self.selected_candidate is BaselineCandidate.ZERO:
            raise ValueError("Evaluated gate evidence requires a non-benchmark selected method")
        if self.compared_fold_count == 0:
            raise ValueError("Evaluated gate evidence requires shared historical folds")
        if (
            self.selected_mean_absolute_total_error is None
            or self.zero_mean_absolute_total_error is None
        ):
            raise ValueError("Evaluated gate evidence requires both absolute errors")
        if self.selected_mean_absolute_total_error < 0 or self.zero_mean_absolute_total_error < 0:
            raise ValueError("Gate errors must not be negative")

        if self.zero_mean_absolute_total_error == 0:
            if self.skill_vs_zero is not None:
                raise ValueError("Relative skill is undefined when zero has no error")
            if self.status is not WeeklyZeroSkillGateStatus.FAILED:
                raise ValueError("A method cannot prove improvement over a perfect benchmark")
            return

        expected_skill = (
            self.zero_mean_absolute_total_error - self.selected_mean_absolute_total_error
        ) / self.zero_mean_absolute_total_error
        if self.skill_vs_zero != expected_skill:
            raise ValueError("skill_vs_zero must use shared-fold mean absolute total error")
        expected_status = (
            WeeklyZeroSkillGateStatus.PASSED
            if expected_skill > 0
            else WeeklyZeroSkillGateStatus.FAILED
        )
        if self.status is not expected_status:
            raise ValueError("Gate status must reflect strictly positive skill against zero")

    @property
    def passed(self) -> bool:
        """Whether this one evidence gate passed; this is not overall forecast approval."""
        return self.status is WeeklyZeroSkillGateStatus.PASSED


def assess_weekly_zero_skill(report: ProductEvaluationReport) -> WeeklyZeroSkillEvidence:
    """Compare the selected weekly method with zero on identical historical weeks."""
    selected_candidate = report.seven_day_winner
    if selected_candidate is None:
        return _unavailable(
            report,
            None,
            "No weekly method has enough fair evaluation evidence for the zero-skill check.",
        )

    selected = _evaluated_candidate(report, selected_candidate)
    zero = _evaluated_candidate(report, BaselineCandidate.ZERO)
    if selected is None or zero is None:
        return _unavailable(
            report,
            selected_candidate,
            "The selected weekly method and zero benchmark were not both evaluated.",
        )

    selected_folds = _folds_by_dates(selected)
    zero_folds = _folds_by_dates(zero)
    shared_dates = tuple(sorted(set(selected_folds) & set(zero_folds)))
    if not shared_dates:
        return _unavailable(
            report,
            selected_candidate,
            "The selected weekly method and zero benchmark share no historical test weeks.",
        )

    selected_error = _mean_absolute_total_error(selected_folds, shared_dates)
    zero_error = _mean_absolute_total_error(zero_folds, shared_dates)
    skill = None if zero_error == 0 else (zero_error - selected_error) / zero_error
    passed = skill is not None and skill > 0

    if zero_error == 0:
        message = (
            "The zero benchmark was perfect on the shared historical weeks, so the selected "
            "method did not prove additional forecasting value. Do not show a numeric forecast."
        )
    elif passed:
        message = (
            "The selected weekly method beat forecasting zero on the same historical weeks. "
            "This passes only the zero-skill gate; it does not yet make the forecast supported "
            "or decision-ready."
        )
    else:
        message = (
            "The selected weekly method did not beat forecasting zero on the same historical "
            "weeks. Do not show a numeric forecast for this product."
        )

    return WeeklyZeroSkillEvidence(
        product_key=report.product_key,
        status=(WeeklyZeroSkillGateStatus.PASSED if passed else WeeklyZeroSkillGateStatus.FAILED),
        selected_candidate=selected_candidate,
        compared_fold_count=len(shared_dates),
        selected_mean_absolute_total_error=selected_error,
        zero_mean_absolute_total_error=zero_error,
        skill_vs_zero=skill,
        message=message,
    )


def weekly_zero_skill_evidence_to_dict(
    evidence: WeeklyZeroSkillEvidence,
) -> dict[str, object]:
    """Serialize gate evidence without converting it into a production trust label."""
    return {
        "product_key": evidence.product_key,
        "status": evidence.status.value,
        "passed": evidence.passed,
        "selected_candidate": (
            evidence.selected_candidate.value if evidence.selected_candidate is not None else None
        ),
        "benchmark_candidate": evidence.benchmark_candidate.value,
        "benchmark_granularity": evidence.benchmark_granularity.value,
        "compared_fold_count": evidence.compared_fold_count,
        "selected_mean_absolute_total_error": _string_or_none(
            evidence.selected_mean_absolute_total_error
        ),
        "zero_mean_absolute_total_error": _string_or_none(evidence.zero_mean_absolute_total_error),
        "skill_vs_zero": _string_or_none(evidence.skill_vs_zero),
        "scope": (
            "Necessary zero-benchmark evidence only. Passing does not approve a supported or "
            "user-facing forecast."
        ),
        "message": evidence.message,
    }


def assess_weekly_zero_skill_portfolio(
    reports: Iterable[ProductEvaluationReport],
) -> tuple[WeeklyZeroSkillEvidence, ...]:
    """Apply the same zero-skill rule independently to every product."""
    return tuple(
        assess_weekly_zero_skill(report)
        for report in sorted(reports, key=lambda item: item.product_key)
    )


def weekly_zero_skill_portfolio_to_dict(
    evidence: Iterable[WeeklyZeroSkillEvidence],
) -> dict[str, object]:
    """Summarize gate outcomes while retaining every product-level decision."""
    items = tuple(evidence)
    counts = Counter(item.status.value for item in items)
    return {
        "scope": (
            "Necessary zero-benchmark evidence only. A pass does not approve a supported or "
            "user-facing forecast."
        ),
        "product_count": len(items),
        "status_counts": dict(sorted(counts.items())),
        "products": [weekly_zero_skill_evidence_to_dict(item) for item in items],
    }


def _unavailable(
    report: ProductEvaluationReport,
    selected_candidate: BaselineCandidate | None,
    message: str,
) -> WeeklyZeroSkillEvidence:
    return WeeklyZeroSkillEvidence(
        product_key=report.product_key,
        status=WeeklyZeroSkillGateStatus.UNAVAILABLE,
        selected_candidate=selected_candidate,
        compared_fold_count=0,
        selected_mean_absolute_total_error=None,
        zero_mean_absolute_total_error=None,
        skill_vs_zero=None,
        message=message,
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


def _mean_absolute_total_error(
    folds: dict[tuple[object, ...], RollingOriginFold],
    shared_dates: tuple[tuple[object, ...], ...],
) -> Decimal:
    errors = tuple(
        abs(folds[dates].predicted_total_units - sum(folds[dates].actual_daily_units, Decimal("0")))
        for dates in shared_dates
    )
    return sum(errors, Decimal("0")) / Decimal(len(errors))


def _string_or_none(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None
