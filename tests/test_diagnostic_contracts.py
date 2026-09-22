import pytest

from src.diagnostics.contracts import (
    ComparisonPeriod,
    ConfidenceLevel,
    DiagnosticCategory,
    DiagnosticInsight,
    DiagnosticReport,
    EvidenceItem,
    Limitation,
    Priority,
    RecommendedAction,
)


def _evidence() -> EvidenceItem:
    return EvidenceItem(
        metric="net_revenue",
        current_value=860.0,
        baseline_value=1000.0,
        absolute_change=-140.0,
        percent_change=-14.0,
        unit="USD",
        provenance="canonical_sales.net_revenue",
    )


def _insight(identifier: str = "revenue_decline") -> DiagnosticInsight:
    return DiagnosticInsight(
        id=identifier,
        title="Revenue declined",
        category=DiagnosticCategory.PERFORMANCE_CHANGE,
        observation="Net revenue decreased 14.0% from June 2026 to July 2026.",
        confidence=ConfidenceLevel.HIGH,
        priority=Priority.HIGH,
        evidence=(_evidence(),),
        comparison_period=ComparisonPeriod(
            current_label="2026-07",
            baseline_label="2026-06",
            basis="previous_complete_month",
        ),
        recommended_action=RecommendedAction(
            id="investigate_order_volume",
            title="Investigate completed order volume",
            description="Review traffic, checkout, and cancellation changes before acting.",
            priority=Priority.HIGH,
        ),
    )


def test_diagnostic_report_accepts_traceable_insights() -> None:
    report = DiagnosticReport(
        contract_version="1.0",
        currency="USD",
        insights=(_insight(),),
        unavailable_capabilities=(
            Limitation(
                code="inventory_data_missing",
                message="Inventory recommendations require inventory and lead-time fields.",
            ),
        ),
    )

    assert report.currency == "USD"
    assert report.insights[0].evidence[0].percent_change == -14.0
    assert report.insights[0].recommended_action is not None


def test_evidence_change_requires_baseline() -> None:
    with pytest.raises(ValueError, match="require a baseline_value"):
        EvidenceItem(
            metric="net_revenue",
            current_value=860.0,
            absolute_change=-140.0,
            unit="USD",
            provenance="canonical_sales.net_revenue",
        )


def test_unavailable_insight_requires_limitation() -> None:
    with pytest.raises(ValueError, match="require at least one limitation"):
        DiagnosticInsight(
            id="anomaly_unavailable",
            title="Anomaly detection unavailable",
            category=DiagnosticCategory.ANOMALY,
            observation="There is not enough complete history for anomaly detection.",
            confidence=ConfidenceLevel.UNAVAILABLE,
            priority=Priority.LOW,
            evidence=(_evidence(),),
        )


def test_recommended_action_cannot_skip_human_review() -> None:
    with pytest.raises(ValueError, match="must require human review"):
        RecommendedAction(
            id="automatic_discount_change",
            title="Change discount",
            description="Apply a discount without human review.",
            priority=Priority.CRITICAL,
            requires_human_review=False,
        )


def test_report_rejects_duplicate_insight_ids() -> None:
    with pytest.raises(ValueError, match="ids must be unique"):
        DiagnosticReport(
            contract_version="1.0",
            currency="USD",
            insights=(_insight(), _insight()),
        )
