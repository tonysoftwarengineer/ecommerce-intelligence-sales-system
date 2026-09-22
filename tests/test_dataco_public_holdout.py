from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from scripts.evaluate_dataco_public_holdout import build_report, render_summary
from src.product_demand.dataco_public_evaluation import prepare_dataco_public_holdout
from src.product_demand.locked_evaluation import evaluate_locked_holdout


def _source(days: int = 260, *, final_week_quantity: int = 1) -> pd.DataFrame:
    start = date(2025, 1, 1)
    rows = []
    for offset in range(days):
        rows.append(
            {
                "order_date_(DateOrders)": (start + timedelta(days=offset)).strftime("%m/%d/%Y"),
                "Order_Id": str(offset + 1),
                "Order_Customer_Id": "private-customer",
                "Order_Item_Id": str(offset + 1),
                "Product_Card_Id": "SKU-SECRET",
                "Order_Item_Quantity": str(final_week_quantity if offset >= days - 7 else 1),
                "Order_Status": "COMPLETE",
            }
        )
    return pd.DataFrame(rows)


def test_dataco_adapter_keeps_missing_day_uncertainty_visible() -> None:
    source = _source()
    source.loc[20, "Order_Status"] = "PENDING"
    prepared = prepare_dataco_public_holdout(source)

    assert prepared.evaluation_mode.startswith("research_only")
    assert prepared.evidence_counts["strict_missing_unknown_product_days"] == 1
    assert prepared.series[0].points[20].target_units == 0
    assert prepared.evidence_counts["other_status_rows"] == 1


def test_dataco_blind_holdout_never_uses_later_actuals_for_first_prediction() -> None:
    normal = evaluate_locked_holdout(prepare_dataco_public_holdout(_source()), ())
    changed = evaluate_locked_holdout(
        prepare_dataco_public_holdout(_source(final_week_quantity=100)), ()
    )

    assert len(normal.outcomes) == 13
    assert normal.outcomes[0].predicted_total_units == 7
    assert normal.outcomes[0].predicted_total_units == changed.outcomes[0].predicted_total_units
    assert normal.outcomes[-1].actual_total_units != changed.outcomes[-1].actual_total_units


def test_dataco_invalid_complete_row_is_not_silently_repaired() -> None:
    source = _source()
    source.loc[3, "Order_Item_Quantity"] = "not a number"

    with pytest.raises(ValueError, match="unsafe dates, IDs, or quantities"):
        prepare_dataco_public_holdout(source)


def test_dataco_public_summary_omits_product_and_customer_ids() -> None:
    report = build_report(_source(), "test-sha")
    summary = render_summary(report)

    assert "SKU-SECRET" not in summary
    assert "private-customer" not in summary
    assert "research" in summary.lower()
    assert "SKU-SECRET" in str(report["holdout"])


def test_zero_actual_holdout_is_not_reported_as_accurate_forecasting() -> None:
    source = _source()
    source.loc[169:, "Order_Status"] = "PENDING"

    report = build_report(source, "test-sha")
    summary = render_summary(report)

    assert report["outcome_audit"]["shown_actual_units"] == "0"
    assert "not defined" in summary
    assert "do not demonstrate predictive skill" in summary
