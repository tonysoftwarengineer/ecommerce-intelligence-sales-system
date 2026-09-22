from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from src.product_demand.contracts import (
    ProductDateStatus,
    ProductDemandAvailability,
    ProductDemandProductReadiness,
    ProductDemandReasonCode,
    ProductIdentitySource,
)
from src.product_demand.evaluation_contracts import (
    BaselineCandidate,
    EvaluationConfiguration,
    EvaluationSeries,
    EvaluationSeriesPoint,
    ForecastGranularity,
)
from src.product_demand.metrics import evaluate_product_baselines
from src.product_demand.trust_gate import assess_weekly_zero_skill
from src.product_demand.trust_policy import (
    MINIMUM_PREVIEW_FOLDS,
    ProductDemandPolicyReason,
    ProductDemandTrustDecision,
    ProductDemandTrustState,
    assess_product_demand_trust,
    product_demand_trust_decision_to_dict,
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


def _evidence(values: list[int], product_key: str = "id:A", candidates=None):
    report = evaluate_product_baselines(
        _series(values, product_key),
        EvaluationConfiguration(),
        candidates=candidates,
    )
    return report, assess_weekly_zero_skill(report)


def _readiness(
    *,
    product_key: str = "id:A",
    status: ProductDemandAvailability = ProductDemandAvailability.READY,
    identity_source: ProductIdentitySource = ProductIdentitySource.PRODUCT_ID,
    reasons: tuple[ProductDemandReasonCode, ...] = (),
) -> ProductDemandProductReadiness:
    return ProductDemandProductReadiness(
        product_key=product_key,
        product_id=(
            product_key.removeprefix("id:")
            if identity_source is ProductIdentitySource.PRODUCT_ID
            else None
        ),
        product_name=("Example" if identity_source is ProductIdentitySource.PRODUCT_NAME else None),
        identity_source=identity_source,
        unit_of_measure="piece",
        status=status,
        reason_codes=reasons,
        explanations=tuple(f"Data limitation: {reason.value}." for reason in reasons),
    )


def test_exact_boundary_allows_only_a_limited_weekly_preview() -> None:
    report, zero_skill = _evidence([3] * 119)

    decision = assess_product_demand_trust(_readiness(), report, zero_skill)

    assert zero_skill.compared_fold_count == MINIMUM_PREVIEW_FOLDS
    assert decision.state is ProductDemandTrustState.LIMITED_PREVIEW
    assert decision.numeric_forecast_allowed is True
    assert decision.granularity is ForecastGranularity.SEVEN_DAY_TOTAL
    assert decision.selected_candidate is BaselineCandidate.LAST_WEEK_TOTAL
    assert decision.skill_vs_zero == 1
    assert decision.policy_reasons == ()
    assert "not decision-ready" in decision.warning


def test_one_fold_below_boundary_blocks_the_numeric_forecast() -> None:
    report, zero_skill = _evidence([3] * 112)

    decision = assess_product_demand_trust(_readiness(), report, zero_skill)

    assert zero_skill.compared_fold_count == MINIMUM_PREVIEW_FOLDS - 1
    assert decision.state is ProductDemandTrustState.UNAVAILABLE
    assert decision.numeric_forecast_allowed is False
    assert decision.granularity is None
    assert decision.policy_reasons == (ProductDemandPolicyReason.INSUFFICIENT_SHARED_FOLDS,)
    assert "requires at least 13" in decision.explanations[-1]


@pytest.mark.parametrize(
    "reason",
    [
        ProductDemandReasonCode.STOCKOUT_DATA_UNAVAILABLE,
        ProductDemandReasonCode.INCOMPLETE_DAILY_COVERAGE,
    ],
)
def test_unresolved_calendar_semantics_block_an_otherwise_good_method(reason) -> None:
    report, zero_skill = _evidence([3] * 119)
    readiness = _readiness(status=ProductDemandAvailability.LIMITED, reasons=(reason,))

    decision = assess_product_demand_trust(readiness, report, zero_skill)

    assert decision.state is ProductDemandTrustState.UNAVAILABLE
    assert decision.policy_reasons == (ProductDemandPolicyReason.UNSAFE_SEMANTICS,)
    assert decision.data_reason_codes == (reason,)


def test_confirmed_product_name_fallback_can_remain_a_limited_preview() -> None:
    report, zero_skill = _evidence([3] * 119, "name:Example")
    readiness = _readiness(
        product_key="name:Example",
        status=ProductDemandAvailability.LIMITED,
        identity_source=ProductIdentitySource.PRODUCT_NAME,
        reasons=(ProductDemandReasonCode.PRODUCT_NAME_FALLBACK,),
    )

    decision = assess_product_demand_trust(readiness, report, zero_skill)

    assert decision.state is ProductDemandTrustState.LIMITED_PREVIEW
    assert decision.data_reason_codes == (ProductDemandReasonCode.PRODUCT_NAME_FALLBACK,)
    assert decision.explanations[0].startswith("Data limitation")


def test_non_positive_zero_skill_blocks_an_all_zero_product() -> None:
    report, zero_skill = _evidence([0] * 119)

    decision = assess_product_demand_trust(_readiness(), report, zero_skill)

    assert zero_skill.skill_vs_zero is None
    assert decision.state is ProductDemandTrustState.UNAVAILABLE
    assert decision.policy_reasons == (ProductDemandPolicyReason.NON_POSITIVE_ZERO_SKILL,)
    assert "did not perform better" in decision.explanations[-1]


def test_missing_zero_evidence_blocks_a_weekly_winner() -> None:
    report, zero_skill = _evidence(
        [3] * 119,
        candidates=(
            BaselineCandidate.LAST_WEEK_TOTAL,
            BaselineCandidate.MEAN_4_WEEKLY_TOTALS,
            BaselineCandidate.SBA_CROSTON,
        ),
    )

    decision = assess_product_demand_trust(_readiness(), report, zero_skill)

    assert decision.state is ProductDemandTrustState.UNAVAILABLE
    assert decision.policy_reasons == (ProductDemandPolicyReason.ZERO_SKILL_EVIDENCE_UNAVAILABLE,)


def test_no_weekly_winner_blocks_a_numeric_forecast() -> None:
    report, zero_skill = _evidence(
        [3] * 119,
        candidates=(BaselineCandidate.ZERO, BaselineCandidate.LATEST_VALUE),
    )

    decision = assess_product_demand_trust(_readiness(), report, zero_skill)

    assert decision.state is ProductDemandTrustState.UNAVAILABLE
    assert decision.policy_reasons == (ProductDemandPolicyReason.NO_WEEKLY_WINNER,)


def test_supported_weekly_state_cannot_be_constructed_in_policy_version_one() -> None:
    with pytest.raises(ValueError, match="not approved"):
        ProductDemandTrustDecision(
            product_key="id:A",
            state=ProductDemandTrustState.SUPPORTED_WEEKLY,
            selected_candidate=BaselineCandidate.LAST_WEEK_TOTAL,
            shared_fold_count=13,
            skill_vs_zero=Decimal("0.5"),
            policy_reasons=(),
            data_reason_codes=(),
            explanations=(),
            warning="Supported.",
        )


def test_evidence_for_different_products_cannot_be_combined() -> None:
    report, zero_skill = _evidence([3] * 119, "id:B")

    with pytest.raises(ValueError, match="must match one product"):
        assess_product_demand_trust(_readiness(product_key="id:A"), report, zero_skill)


def test_serialized_contract_never_claims_supported_use_or_daily_prediction() -> None:
    report, zero_skill = _evidence([3] * 119)
    decision = assess_product_demand_trust(_readiness(), report, zero_skill)

    payload = product_demand_trust_decision_to_dict(decision)

    assert payload["state"] == "limited_preview"
    assert payload["numeric_forecast_allowed"] is True
    assert payload["supported_use_approved"] is False
    assert payload["granularity"] == "seven_day_total"
    assert payload["minimum_preview_folds"] == 13
    assert payload["policy_reasons"] == []
