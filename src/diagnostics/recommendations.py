"""Deterministic, human-reviewed recommendation ranking."""

from __future__ import annotations

from dataclasses import replace

from src.diagnostics.contracts import (
    ConfidenceLevel,
    DiagnosticInsight,
    DiagnosticReport,
    Priority,
    RecommendationScore,
    RecommendedAction,
)

PRIORITY_ORDER = {
    Priority.CRITICAL: 4,
    Priority.HIGH: 3,
    Priority.MEDIUM: 2,
    Priority.LOW: 1,
}


def rank_recommendations(report: DiagnosticReport) -> DiagnosticReport:
    """Attach safe recommendations to supported findings and rank them.

    A recommendation is an investigation prompt, not an instruction to change a
    price, discount, inventory position, or customer communication. Ranking is
    intentionally transparent: impact + urgency + confidence, each scored 0–3.
    """
    ranked_insights = []
    for insight in report.insights:
        recommendation = _recommendation_for(insight)
        if recommendation is None:
            ranked_insights.append(insight)
            continue
        score = _score(insight)
        priority = _priority(score)
        if insight.id == "recognized_sales_change" and priority is Priority.HIGH:
            priority = Priority.MEDIUM
        ranked_insights.append(
            replace(
                insight,
                priority=priority,
                recommended_action=replace(recommendation, priority=priority, score=score),
            )
        )
    ranked_insights.sort(key=_sort_key)
    return replace(report, insights=tuple(ranked_insights))


def _recommendation_for(insight: DiagnosticInsight) -> RecommendedAction | None:
    if not insight.evidence:
        return None
    if insight.id == "recognized_sales_change":
        return RecommendedAction(
            id="review_latest_sales_change",
            title="Review the latest sales change",
            description=(
                "Validate the order-count and average-order-value contributors before taking "
                "action; this two-period comparison is not a causal finding."
            ),
            priority=Priority.LOW,
        )
    metric = insight.evidence[0].metric
    direction = _direction(insight)
    templates = {
        ("recognized_sales", "low"): (
            "investigate_sales_decline",
            "Investigate the sales decline",
            "Review completed orders, cancellations, checkout performance, traffic, and fulfilment "
            "conditions before changing pricing or discounts.",
        ),
        ("recognized_sales", "high"): (
            "validate_sales_increase",
            "Validate the sales increase and operational readiness",
            "Confirm promotion, bulk-order, or product-mix effects and review fulfilment capacity "
            "before making a commercial decision.",
        ),
        ("completed_orders", "low"): (
            "investigate_order_decline",
            "Investigate the reduction in completed orders",
            "Review traffic, checkout performance, cancellations, payment failures, and product "
            "availability before intervening.",
        ),
        ("completed_orders", "high"): (
            "validate_order_increase",
            "Validate the increase in completed orders",
            "Confirm demand drivers and review fulfilment capacity before changing operations.",
        ),
        ("average_order_value", "low"): (
            "review_lower_order_value",
            "Review the lower average order value",
            "Review product mix, discounts, and basket composition before changing prices "
            "or offers.",
        ),
        ("average_order_value", "high"): (
            "review_higher_order_value",
            "Review the higher average order value",
            "Review product mix and larger orders to understand the movement before "
            "changing offers.",
        ),
    }
    template = templates.get((metric, direction))
    if template is None:
        return None
    return RecommendedAction(
        id=template[0], title=template[1], description=template[2], priority=Priority.LOW
    )


def _score(insight: DiagnosticInsight) -> RecommendationScore:
    evidence = insight.evidence[0]
    percent_change = abs(evidence.percent_change or 0.0)
    impact = (
        3 if percent_change >= 50 else 2 if percent_change >= 20 else 1 if percent_change > 0 else 0
    )
    if insight.id == "recognized_sales_change":
        impact = min(impact, 2)
    urgency = (
        1
        if insight.id == "recognized_sales_change"
        else _urgency(evidence.metric, _direction(insight))
    )
    confidence = {
        ConfidenceLevel.HIGH: 3,
        ConfidenceLevel.MEDIUM: 2,
        ConfidenceLevel.LOW: 1,
        ConfidenceLevel.UNAVAILABLE: 0,
    }[insight.confidence]
    return RecommendationScore(
        impact=impact,
        urgency=urgency,
        confidence=confidence,
        total=impact + urgency + confidence,
    )


def _urgency(metric: str, direction: str) -> int:
    if metric in {"recognized_sales", "completed_orders"}:
        return 3 if direction == "low" else 2
    if metric == "average_order_value":
        return 2 if direction == "low" else 1
    return 1


def _priority(score: RecommendationScore) -> Priority:
    if score.total >= 7:
        return Priority.HIGH
    if score.total >= 4:
        return Priority.MEDIUM
    return Priority.LOW


def _direction(insight: DiagnosticInsight) -> str:
    change = insight.evidence[0].absolute_change
    return "high" if change is not None and change > 0 else "low"


def _sort_key(insight: DiagnosticInsight) -> tuple[int, int, str]:
    action_score = insight.recommended_action.score if insight.recommended_action else None
    return (
        -PRIORITY_ORDER[insight.priority],
        -(action_score.total if action_score else 0),
        insight.id,
    )
