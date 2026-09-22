from src.diagnostics.contracts import (
    ConfidenceLevel,
    DiagnosticCategory,
    DiagnosticInsight,
    DiagnosticReport,
    DiagnosticStatus,
    EvidenceItem,
    Priority,
)
from src.diagnostics.recommendations import rank_recommendations


def _insight(identifier: str, metric: str, percent_change: float) -> DiagnosticInsight:
    return DiagnosticInsight(
        id=identifier,
        title=identifier,
        category=DiagnosticCategory.ANOMALY,
        observation="A validated unusual movement was detected.",
        confidence=ConfidenceLevel.MEDIUM,
        priority=Priority.MEDIUM,
        evidence=(
            EvidenceItem(
                metric=metric,
                current_value=40.0 if percent_change < 0 else 160.0,
                baseline_value=100.0,
                absolute_change=percent_change,
                percent_change=percent_change,
                unit="NGN" if metric != "completed_orders" else "orders",
                provenance="test",
            ),
        ),
    )


def test_low_sales_is_ranked_above_high_average_order_value() -> None:
    report = DiagnosticReport(
        contract_version="1.0",
        currency="NGN",
        status=DiagnosticStatus.AVAILABLE,
        insights=(
            _insight("anomaly_average_order_value", "average_order_value", 60.0),
            _insight("anomaly_recognized_sales", "recognized_sales", -60.0),
        ),
    )

    ranked = rank_recommendations(report)

    assert [insight.id for insight in ranked.insights] == [
        "anomaly_recognized_sales",
        "anomaly_average_order_value",
    ]
    sales_action = ranked.insights[0].recommended_action
    assert sales_action is not None
    assert sales_action.id == "investigate_sales_decline"
    assert sales_action.requires_human_review is True
    assert sales_action.priority is Priority.HIGH
    assert sales_action.score is not None
    assert sales_action.score.total == 8


def test_two_period_sales_change_is_never_higher_than_medium_priority() -> None:
    report = DiagnosticReport(
        contract_version="1.0",
        currency="NGN",
        insights=(_insight("recognized_sales_change", "recognized_sales", -80.0),),
    )

    ranked = rank_recommendations(report)

    action = ranked.insights[0].recommended_action
    assert action is not None
    assert action.priority is Priority.MEDIUM
    assert action.score is not None
    assert action.score.impact == 2


def test_unsupported_insights_do_not_receive_a_recommendation() -> None:
    report = DiagnosticReport(
        contract_version="1.0",
        currency="NGN",
        insights=(_insight("anomaly_unknown_metric", "refund_rate", -70.0),),
    )

    ranked = rank_recommendations(report)

    assert ranked.insights[0].recommended_action is None


def test_no_findings_report_remains_empty() -> None:
    report = DiagnosticReport(
        contract_version="1.0",
        currency="NGN",
        status=DiagnosticStatus.NO_FINDINGS,
        insights=(),
    )

    ranked = rank_recommendations(report)

    assert ranked.status is DiagnosticStatus.NO_FINDINGS
    assert ranked.insights == ()
