"""Build API-safe diagnostic sections without weakening the analytics path."""

from __future__ import annotations

import logging
from typing import Callable

import pandas as pd

from src.diagnostics.anomaly import build_monthly_anomaly_report
from src.diagnostics.comparison import build_latest_complete_period_revenue_report
from src.diagnostics.contracts import DiagnosticReport, DiagnosticStatus, Limitation
from src.diagnostics.recommendations import rank_recommendations

logger = logging.getLogger(__name__)
CONTRACT_VERSION = "1.0"


def build_diagnostic_sections(
    canonical_data: pd.DataFrame,
    latest_period_complete: bool,
) -> dict:
    """Build comparison and anomaly sections independently for graceful degradation."""
    currency = _currency(canonical_data)
    return {
        "comparison": _build_section(
            "comparison",
            currency,
            lambda: build_latest_complete_period_revenue_report(
                canonical_data, latest_period_complete
            ),
        ),
        "anomalies": _build_section(
            "anomaly detection",
            currency,
            lambda: build_monthly_anomaly_report(canonical_data, latest_period_complete),
        ),
    }


def unavailable_diagnostic_sections(code: str, message: str) -> dict:
    """Return stable unavailable contracts without executing diagnostic builders."""
    section = {
        "status": DiagnosticStatus.UNAVAILABLE.value,
        "insights": [],
        "unavailable_capabilities": [{"code": code, "message": message}],
    }
    return {"comparison": dict(section), "anomalies": dict(section)}


def _build_section(
    section_name: str,
    currency: str,
    builder: Callable[[], DiagnosticReport],
) -> dict:
    try:
        return diagnostic_report_to_dict(rank_recommendations(builder()))
    except Exception:
        logger.exception("%s diagnostic section is unavailable", section_name)
        return diagnostic_report_to_dict(
            DiagnosticReport(
                contract_version=CONTRACT_VERSION,
                currency=currency,
                insights=(),
                unavailable_capabilities=(
                    Limitation(
                        code="diagnostic_processing_error",
                        message=(
                            f"{section_name.capitalize()} is temporarily unavailable. "
                            "Core sales analytics remain available."
                        ),
                    ),
                ),
                status=DiagnosticStatus.UNAVAILABLE,
            )
        )


def diagnostic_report_to_dict(report: DiagnosticReport) -> dict:
    """Serialize domain contracts explicitly so API output remains stable and auditable."""
    return {
        "status": report.status.value,
        "insights": [
            {
                "id": insight.id,
                "title": insight.title,
                "category": insight.category.value,
                "observation": insight.observation,
                "confidence": insight.confidence.value,
                "priority": insight.priority.value,
                "comparison_period": (
                    {
                        "current_label": insight.comparison_period.current_label,
                        "baseline_label": insight.comparison_period.baseline_label,
                        "basis": insight.comparison_period.basis,
                    }
                    if insight.comparison_period
                    else None
                ),
                "evidence": [
                    {
                        "metric": evidence.metric,
                        "current_value": evidence.current_value,
                        "baseline_value": evidence.baseline_value,
                        "absolute_change": evidence.absolute_change,
                        "percent_change": evidence.percent_change,
                        "unit": evidence.unit,
                        "provenance": evidence.provenance,
                    }
                    for evidence in insight.evidence
                ],
                "contributors": [
                    {
                        "factor": contributor.factor,
                        "contribution_value": contributor.contribution_value,
                        "unit": contributor.unit,
                        "explanation": contributor.explanation,
                        "share_of_change_percent": contributor.share_of_change_percent,
                    }
                    for contributor in insight.contributors
                ],
                "limitations": [
                    {"code": limitation.code, "message": limitation.message}
                    for limitation in insight.limitations
                ],
                "recommended_action": (
                    {
                        "id": insight.recommended_action.id,
                        "title": insight.recommended_action.title,
                        "description": insight.recommended_action.description,
                        "priority": insight.recommended_action.priority.value,
                        "requires_human_review": insight.recommended_action.requires_human_review,
                        "estimated_impact": insight.recommended_action.estimated_impact,
                        "impact_unit": insight.recommended_action.impact_unit,
                        "score": (
                            {
                                "impact": insight.recommended_action.score.impact,
                                "urgency": insight.recommended_action.score.urgency,
                                "confidence": insight.recommended_action.score.confidence,
                                "total": insight.recommended_action.score.total,
                            }
                            if insight.recommended_action.score
                            else None
                        ),
                    }
                    if insight.recommended_action
                    else None
                ),
            }
            for insight in report.insights
        ],
        "unavailable_capabilities": [
            {"code": limitation.code, "message": limitation.message}
            for limitation in report.unavailable_capabilities
        ],
    }


def _currency(canonical_data: pd.DataFrame) -> str:
    currencies = sorted(str(value) for value in canonical_data["currency"].dropna().unique())
    if len(currencies) != 1:
        raise ValueError("Diagnostic sections require exactly one currency")
    return currencies[0]
