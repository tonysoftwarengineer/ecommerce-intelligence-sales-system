"""Accepted preview-only trust policy for product-demand forecasts."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from src.product_demand.contracts import (
    ProductDemandAvailability,
    ProductDemandProductReadiness,
    ProductDemandReasonCode,
)
from src.product_demand.evaluation_contracts import (
    BaselineCandidate,
    ForecastGranularity,
    ProductEvaluationReport,
)
from src.product_demand.trust_gate import (
    WeeklyZeroSkillEvidence,
    WeeklyZeroSkillGateStatus,
)

MINIMUM_PREVIEW_FOLDS = 13


class ProductDemandTrustState(str, Enum):
    UNAVAILABLE = "unavailable"
    LIMITED_PREVIEW = "limited_preview"
    SUPPORTED_WEEKLY = "supported_weekly"


class ProductDemandPolicyReason(str, Enum):
    UNSAFE_SEMANTICS = "unsafe_semantics"
    NO_WEEKLY_WINNER = "no_weekly_winner"
    ZERO_SKILL_EVIDENCE_UNAVAILABLE = "zero_skill_evidence_unavailable"
    INSUFFICIENT_SHARED_FOLDS = "insufficient_shared_folds"
    NON_POSITIVE_ZERO_SKILL = "non_positive_zero_skill"
    FINAL_FORECAST_UNAVAILABLE = "final_forecast_unavailable"


SEMANTIC_PREVIEW_BLOCKERS = frozenset(
    {
        ProductDemandReasonCode.STOCKOUT_DATA_UNAVAILABLE,
        ProductDemandReasonCode.INCOMPLETE_DAILY_COVERAGE,
    }
)


@dataclass(frozen=True)
class ProductDemandTrustDecision:
    """One auditable product-level decision; it does not contain a forecast value."""

    product_key: str
    state: ProductDemandTrustState
    selected_candidate: BaselineCandidate | None
    shared_fold_count: int
    skill_vs_zero: Decimal | None
    policy_reasons: tuple[ProductDemandPolicyReason, ...]
    data_reason_codes: tuple[ProductDemandReasonCode, ...]
    explanations: tuple[str, ...]
    warning: str
    minimum_preview_folds: int = MINIMUM_PREVIEW_FOLDS

    def __post_init__(self) -> None:
        if not self.product_key.strip() or not self.warning.strip():
            raise ValueError("Product-demand trust decisions require identity and a warning")
        if self.shared_fold_count < 0 or self.minimum_preview_folds <= 0:
            raise ValueError("Product-demand trust fold counts are invalid")
        object.__setattr__(self, "policy_reasons", tuple(dict.fromkeys(self.policy_reasons)))
        object.__setattr__(self, "data_reason_codes", tuple(dict.fromkeys(self.data_reason_codes)))
        object.__setattr__(self, "explanations", tuple(dict.fromkeys(self.explanations)))

        if self.state is ProductDemandTrustState.UNAVAILABLE:
            if not self.policy_reasons:
                raise ValueError("Unavailable decisions require at least one policy reason")
            return

        if self.state is ProductDemandTrustState.SUPPORTED_WEEKLY:
            raise ValueError("Supported weekly forecasts are not approved in policy version 1")
        if self.policy_reasons:
            raise ValueError("Limited previews cannot retain a blocking policy reason")
        if self.selected_candidate is None or self.selected_candidate is BaselineCandidate.ZERO:
            raise ValueError("Limited previews require a non-benchmark selected method")
        if self.shared_fold_count < self.minimum_preview_folds:
            raise ValueError("Limited previews require the accepted minimum shared folds")
        if self.skill_vs_zero is None or self.skill_vs_zero <= 0:
            raise ValueError("Limited previews require strictly positive skill against zero")

    @property
    def numeric_forecast_allowed(self) -> bool:
        return self.state is ProductDemandTrustState.LIMITED_PREVIEW

    @property
    def granularity(self) -> ForecastGranularity | None:
        return ForecastGranularity.SEVEN_DAY_TOTAL if self.numeric_forecast_allowed else None


def assess_product_demand_trust(
    readiness: ProductDemandProductReadiness,
    report: ProductEvaluationReport | None,
    zero_skill: WeeklyZeroSkillEvidence | None,
    minimum_preview_folds: int = MINIMUM_PREVIEW_FOLDS,
    *,
    scope_label: str = "product",
) -> ProductDemandTrustDecision:
    """Apply accepted ADR-010 gates without calculating or exposing a forecast."""
    if minimum_preview_folds <= 0:
        raise ValueError("minimum_preview_folds must be positive")
    if scope_label not in {"product", "category"}:
        raise ValueError("scope_label must be product or category")
    title = "Product-demand" if scope_label == "product" else "Category-demand"
    evidence_keys = {item.product_key for item in (report, zero_skill) if item is not None}
    if evidence_keys and evidence_keys != {readiness.product_key}:
        raise ValueError("Readiness, evaluation, and zero-skill evidence must match one product")
    if report is None and zero_skill is not None:
        raise ValueError("Zero-skill evidence requires a product evaluation report")
    if (
        report is not None
        and zero_skill is not None
        and zero_skill.selected_candidate is not None
        and report.seven_day_winner is not zero_skill.selected_candidate
    ):
        raise ValueError("Zero-skill evidence must match the selected weekly winner")

    semantic_blockers = tuple(
        reason for reason in readiness.reason_codes if reason in SEMANTIC_PREVIEW_BLOCKERS
    )
    if readiness.status is ProductDemandAvailability.UNAVAILABLE or semantic_blockers:
        return _unavailable(
            readiness,
            report,
            zero_skill,
            minimum_preview_folds,
            ProductDemandPolicyReason.UNSAFE_SEMANTICS,
            (
                f"{title} forecast unavailable because the {scope_label}'s quantity or calendar "
                "meaning is not safe enough for evaluation. Correct the listed data issue and "
                "run the analysis again."
            ),
        )

    if report is None or report.seven_day_winner is None:
        return _unavailable(
            readiness,
            report,
            zero_skill,
            minimum_preview_folds,
            ProductDemandPolicyReason.NO_WEEKLY_WINNER,
            (
                f"{title} forecast unavailable because no weekly method has enough fair "
                f"historical evidence. Add more complete {scope_label} history and run the "
                "analysis again."
            ),
        )

    if zero_skill is None or zero_skill.status is WeeklyZeroSkillGateStatus.UNAVAILABLE:
        return _unavailable(
            readiness,
            report,
            zero_skill,
            minimum_preview_folds,
            ProductDemandPolicyReason.ZERO_SKILL_EVIDENCE_UNAVAILABLE,
            (
                f"{title} forecast unavailable because the selected method could not be "
                "compared fairly with the zero benchmark."
            ),
        )

    if zero_skill.compared_fold_count < minimum_preview_folds:
        return _unavailable(
            readiness,
            report,
            zero_skill,
            minimum_preview_folds,
            ProductDemandPolicyReason.INSUFFICIENT_SHARED_FOLDS,
            (
                f"{title} forecast unavailable because only "
                f"{zero_skill.compared_fold_count} shared historical test weeks are available; "
                f"the limited preview requires at least {minimum_preview_folds}."
            ),
        )

    if zero_skill.status is WeeklyZeroSkillGateStatus.FAILED:
        return _unavailable(
            readiness,
            report,
            zero_skill,
            minimum_preview_folds,
            ProductDemandPolicyReason.NON_POSITIVE_ZERO_SKILL,
            (
                f"{title} forecast unavailable because the selected weekly method did not "
                "perform better than forecasting zero on the same historical weeks."
            ),
        )

    return ProductDemandTrustDecision(
        product_key=readiness.product_key,
        state=ProductDemandTrustState.LIMITED_PREVIEW,
        selected_candidate=zero_skill.selected_candidate,
        shared_fold_count=zero_skill.compared_fold_count,
        skill_vs_zero=zero_skill.skill_vs_zero,
        policy_reasons=(),
        data_reason_codes=readiness.reason_codes,
        explanations=(
            *readiness.explanations,
            (
                "The selected weekly method performed better than forecasting zero on the same "
                "historical test weeks. This supports exploration, not an inventory commitment."
            ),
        ),
        warning=(
            "Preview — not decision-ready. This is a seven-day fulfilled-unit estimate, not a "
            "reorder quantity or a prediction for each individual day."
        ),
        minimum_preview_folds=minimum_preview_folds,
    )


def product_demand_trust_decision_to_dict(
    decision: ProductDemandTrustDecision,
) -> dict[str, object]:
    """Serialize a stable policy result without adding a forecast value."""
    return {
        "product_key": decision.product_key,
        "state": decision.state.value,
        "numeric_forecast_allowed": decision.numeric_forecast_allowed,
        "supported_use_approved": False,
        "granularity": decision.granularity.value if decision.granularity is not None else None,
        "selected_candidate": (
            decision.selected_candidate.value if decision.selected_candidate is not None else None
        ),
        "shared_fold_count": decision.shared_fold_count,
        "minimum_preview_folds": decision.minimum_preview_folds,
        "skill_vs_zero": (
            str(decision.skill_vs_zero) if decision.skill_vs_zero is not None else None
        ),
        "policy_reasons": [reason.value for reason in decision.policy_reasons],
        "data_reason_codes": [reason.value for reason in decision.data_reason_codes],
        "explanations": list(decision.explanations),
        "warning": decision.warning,
    }


def _unavailable(
    readiness: ProductDemandProductReadiness,
    report: ProductEvaluationReport | None,
    zero_skill: WeeklyZeroSkillEvidence | None,
    minimum_preview_folds: int,
    policy_reason: ProductDemandPolicyReason,
    explanation: str,
) -> ProductDemandTrustDecision:
    return ProductDemandTrustDecision(
        product_key=readiness.product_key,
        state=ProductDemandTrustState.UNAVAILABLE,
        selected_candidate=(
            zero_skill.selected_candidate
            if zero_skill is not None and zero_skill.selected_candidate is not None
            else report.seven_day_winner
            if report is not None
            else None
        ),
        shared_fold_count=zero_skill.compared_fold_count if zero_skill is not None else 0,
        skill_vs_zero=zero_skill.skill_vs_zero if zero_skill is not None else None,
        policy_reasons=(policy_reason,),
        data_reason_codes=readiness.reason_codes,
        explanations=(*readiness.explanations, explanation),
        warning="Forecast unavailable. Review the explanation before trying again.",
        minimum_preview_folds=minimum_preview_folds,
    )


def block_final_product_demand_forecast(
    decision: ProductDemandTrustDecision,
    explanation: str,
) -> ProductDemandTrustDecision:
    """Downgrade an allowed preview when final forecast generation cannot run safely."""
    if not decision.numeric_forecast_allowed:
        raise ValueError("Only an allowed limited preview can be downgraded")
    if not explanation.strip():
        raise ValueError("Final forecast failure requires an explanation")
    return ProductDemandTrustDecision(
        product_key=decision.product_key,
        state=ProductDemandTrustState.UNAVAILABLE,
        selected_candidate=decision.selected_candidate,
        shared_fold_count=decision.shared_fold_count,
        skill_vs_zero=decision.skill_vs_zero,
        policy_reasons=(ProductDemandPolicyReason.FINAL_FORECAST_UNAVAILABLE,),
        data_reason_codes=decision.data_reason_codes,
        explanations=(*decision.explanations, explanation),
        warning="Forecast unavailable. The selected method cannot safely use the latest history.",
        minimum_preview_folds=decision.minimum_preview_folds,
    )
