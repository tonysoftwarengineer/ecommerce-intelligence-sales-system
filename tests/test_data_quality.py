import pandas as pd

import src.generic_sales.reporting as reporting
from src.generic_sales.contracts import DataQualityStatus, DataValidationResult, ValidationIssue
from src.generic_sales.data_quality import assess_data_quality, data_quality_report_to_dict


def validation(total: int, invalid: int, *, blocked: bool = False) -> DataValidationResult:
    valid = total - invalid
    return DataValidationResult(
        total_rows=total,
        valid_rows=valid,
        invalid_rows=invalid,
        invalid_row_positions=tuple(range(invalid)),
        issues=tuple(
            ValidationIssue(
                row_number=index + 2,
                field="order_date",
                code="invalid_date",
                message="Order date must match the selected date format.",
            )
            for index in range(invalid)
        ),
        warnings=(),
        blocking_errors=("No valid rows remain after data validation.",) if blocked else (),
    )


def assess(total: int, invalid: int, *, blocked: bool = False):
    return assess_data_quality(
        validation(total, invalid, blocked=blocked),
        {"order_date": "Sale Date"},
        "%Y-%m-%d",
    )


def test_data_quality_thresholds_are_deterministic_at_boundaries() -> None:
    assert assess(100, 0).status is DataQualityStatus.NORMAL
    assert assess(100, 4).status is DataQualityStatus.NORMAL
    assert assess(100, 5).status is DataQualityStatus.CAUTION
    assert assess(100, 19).status is DataQualityStatus.CAUTION
    assert assess(100, 20).status is DataQualityStatus.PREVIEW


def test_preview_is_not_decision_ready_and_restricts_decision_outputs() -> None:
    report = assess(650, 290)

    assert report.invalid_row_percentage == 44.6
    assert report.decision_ready is False
    assert report.preview_only is True
    assert report.restricted_outputs == ("forecast", "diagnostics", "recommendations")
    assert "290 of 650" in report.message
    assert "preview only" in report.message


def test_blocked_validation_cannot_preview() -> None:
    report = assess(1, 1, blocked=True)

    assert report.status is DataQualityStatus.BLOCKED
    assert report.decision_ready is False
    assert report.preview_only is False


def test_repair_actions_group_issues_and_name_the_source_column() -> None:
    report = assess(10, 3)

    assert len(report.correction_actions) == 1
    action = report.correction_actions[0]
    assert action.field == "order_date"
    assert action.source_column == "Sale Date"
    assert action.affected_rows == 3
    assert action.sample_row_numbers == (2, 3, 4)
    assert "%Y-%m-%d" in action.instruction

    serialized = data_quality_report_to_dict(report)
    assert serialized["status"] == "preview"
    assert serialized["correction_actions"][0]["source_column"] == "Sale Date"


def test_preview_report_skips_forecast_and_diagnostic_builders(monkeypatch) -> None:
    def must_not_run(*args, **kwargs):
        raise AssertionError("Decision-support builder must not run in Preview Mode")

    monkeypatch.setattr(reporting, "forecast_generic_revenue", must_not_run)
    monkeypatch.setattr(reporting, "build_diagnostic_sections", must_not_run)
    canonical = pd.DataFrame(
        {
            "order_id": ["A1", "A2"],
            "order_date": pd.to_datetime(["2025-01-01", "2025-02-01"]),
            "customer_id": ["C1", "C2"],
            "revenue": [100, 200],
            "currency": ["NGN", "NGN"],
        }
    )

    result = reporting.build_generic_sales_report(
        canonical,
        latest_period_complete=True,
        decision_support_ready=False,
        decision_support_reason="20.0% of source rows were excluded.",
    )

    assert result["forecast"]["status"] == "unavailable"
    assert result["forecast"]["model_evaluations"] == []
    assert result["diagnostics"]["comparison"]["status"] == "unavailable"
    assert result["diagnostics"]["comparison"]["unavailable_capabilities"] == [
        {
            "code": "insufficient_data_quality",
            "message": (
                "Diagnostics and recommendations were not calculated because this is a "
                "preview-only analysis. 20.0% of source rows were excluded."
            ),
        }
    ]
