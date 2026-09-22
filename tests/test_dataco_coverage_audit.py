from __future__ import annotations

from datetime import date, timedelta
from typing import Any, cast

import pandas as pd

from scripts.audit_dataco_coverage import (
    _counterfactual_without_zero_gate,
    build_audit,
    render_summary,
)
from src.product_demand.dataco_public_evaluation import prepare_dataco_public_holdout
from src.product_demand.locked_evaluation import evaluate_locked_holdout


def _source(*, last_week_units: int = 1) -> pd.DataFrame:
    start = date(2025, 1, 1)
    rows: list[dict[str, str]] = []
    for offset in range(260):
        rows.append(
            {
                "order_date_(DateOrders)": (start + timedelta(days=offset)).strftime("%m/%d/%Y"),
                "Order_Id": str(offset + 1),
                "Order_Customer_Id": "private-customer",
                "Order_Item_Id": str(offset + 1),
                "Product_Card_Id": "PRIVATE-SKU",
                "Order_Item_Quantity": str(last_week_units if offset >= 253 else 1),
                "Order_Status": "COMPLETE",
            }
        )
    return pd.DataFrame(rows)


def _audit(source: pd.DataFrame) -> dict[str, Any]:
    return cast(dict[str, Any], build_audit(source, "fixture-hash"))


def test_coverage_audit_reconciles_source_rows_with_calendar_and_keeps_denominator() -> None:
    audit = _audit(_source())
    public = audit["public"]
    assert isinstance(public, dict)
    cases = public["counterfactuals"]
    assert isinstance(cases, dict)
    assert cases["current_policy"]["opportunities"] == 13
    assert cases["six_shared_folds_only"]["opportunities"] == 13
    assert cases["ignore_zero_skill_only"]["opportunities"] == 13
    assert public["assessed_actual_units"] == "91"
    assert public["skipped_actual_units"] == "0"
    assert sum(int(item["actual_units"]) for item in audit["private_trace"]) == 91
    assert audit["private_trace"][0]["source_csv_lines"]
    assert audit["private_trace"][0]["method_selection"]["weekly_winner"]
    assert public["counterfactuals_by_stratum"]["current_policy"]["dense"]["opportunities"] == 13


def test_coverage_audit_does_not_peek_at_later_sales_for_first_week() -> None:
    baseline = _audit(_source())
    changed = _audit(_source(last_week_units=100))
    first = baseline["private_trace"][0]
    changed_first = changed["private_trace"][0]

    assert first["predicted_units"] == changed_first["predicted_units"]
    assert (
        first["prior_completed_sale_recency_days"]
        == (changed_first["prior_completed_sale_recency_days"])
    )
    assert (
        baseline["private_trace"][-1]["actual_units"]
        != (changed["private_trace"][-1]["actual_units"])
    )


def test_coverage_audit_keeps_other_statuses_out_of_completed_target() -> None:
    source = _source()
    source.loc[10, "Order_Status"] = "CLOSED"
    audit = _audit(source)
    public = audit["public"]
    assert isinstance(public, dict)
    activity = public["activity"]
    assert isinstance(activity, dict)
    statuses = activity["status_counts_by_phase"]
    assert statuses["before_holdout"]["CLOSED"] == 1
    assert public["unknown_product_days_treated_as_zero_for_research"] == 1


def test_coverage_summary_is_aggregate_and_deterministic() -> None:
    source = _source()
    first = _audit(source)
    second = _audit(source)
    text = render_summary(first)

    assert first == second
    assert "PRIVATE-SKU" not in text
    assert "private-customer" not in text
    assert "2025-" not in text
    assert "source_csv_lines" not in text
    assert "Research only" in text


def test_only_one_counterfactual_changes_each_rule() -> None:
    audit = _audit(_source())
    public = audit["public"]
    assert isinstance(public, dict)
    cases = public["counterfactuals"]
    assert isinstance(cases, dict)
    baseline = cases["current_policy"]
    six = cases["six_shared_folds_only"]
    no_zero = cases["ignore_zero_skill_only"]

    assert baseline["opportunities"] == six["opportunities"] == no_zero["opportunities"]
    assert no_zero["shown"] >= baseline["shown"]
    assert six["shown"] >= baseline["shown"]


def test_skipped_new_product_units_remain_visible_in_aggregate() -> None:
    source = _source()
    new_rows = source.tail(7).copy()
    new_rows["Product_Card_Id"] = "NEW-PRIVATE-SKU"
    new_rows["Order_Item_Id"] = [str(1000 + index) for index in range(7)]
    audit = _audit(pd.concat([source, new_rows], ignore_index=True))
    public = audit["public"]

    assert public["skipped_products"] == 1
    assert public["assessed_actual_units"] == "91"
    assert public["skipped_actual_units"] == "7"
    assert public["hidden_source_completed_units"] == "98"


def test_zero_gate_counterfactual_can_expand_coverage_without_proving_skill() -> None:
    source = _source()
    source["Order_Status"] = "PENDING"
    source.loc[[0, 40, 80, 120, 160], "Order_Status"] = "COMPLETE"
    audit = _audit(source)
    public = audit["public"]
    cases = public["counterfactuals"]

    assert cases["current_policy"]["shown"] == 0
    assert cases["ignore_zero_skill_only"]["shown"] == 13
    assert cases["ignore_zero_skill_only"]["shown_positive_actual_weeks"] == 0


def test_zero_gate_counterfactual_does_not_use_future_sales() -> None:
    source = _source()
    source["Order_Status"] = "PENDING"
    source.loc[[0, 40, 80, 120, 160], "Order_Status"] = "COMPLETE"
    changed = source.copy()
    changed.loc[253:, "Order_Status"] = "COMPLETE"

    first_prepared = prepare_dataco_public_holdout(source)
    second_prepared = prepare_dataco_public_holdout(changed)
    first = _counterfactual_without_zero_gate(
        first_prepared, evaluate_locked_holdout(first_prepared, ())
    )
    second = _counterfactual_without_zero_gate(
        second_prepared, evaluate_locked_holdout(second_prepared, ())
    )

    assert first[0].predicted_total_units == second[0].predicted_total_units
    assert first[-1].actual_total_units != second[-1].actual_total_units
