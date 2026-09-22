from __future__ import annotations

import csv
from pathlib import Path

from scripts.evaluate_french_bakery_source import _is_external_local_path
from src.generic_sales.contracts import RevenueMode
from src.product_demand.external_source_compatibility import (
    ForecastEligibility,
    WithholdingReasonCode,
    build_local_diagnostic_artifact,
    evaluate_french_bakery_compatibility,
    parse_french_bakery_source,
    parse_french_price,
    render_french_bakery_compatibility_markdown,
)
from src.schema_mapping import validate_schema_mapping


def _write_nested_source(path: Path, rows: list[list[str] | str]) -> Path:
    with path.open("w", encoding="utf-8", newline="") as destination:
        writer = csv.writer(destination)
        writer.writerow(["", "date", "time", "ticket_number", "article", "Quantity", "unit_price"])
        for row in rows:
            if isinstance(row, str):
                writer.writerow([row])
            else:
                nested = next(iter(_csv_lines(row)))
                writer.writerow([nested])
    return path


def _csv_lines(row: list[str]):
    import io

    buffer = io.StringIO(newline="")
    csv.writer(buffer).writerow(row)
    yield buffer.getvalue().rstrip("\r\n")


def _valid_rows() -> list[list[str] | str]:
    return [
        ["0", "2021-01-02", "08:38", "150040.0", "PRIVATE-PRODUCT", "1.0", "0,90 €"],
        ["1", "2021-01-04", "09:15", "150041.0", "OTHER-ITEM", "-1.0", "1,20 €"],
        "broken,nested,row",
    ]


def test_nested_rows_preserve_physical_positions_and_parse_french_values(
    tmp_path: Path,
) -> None:
    source = _write_nested_source(tmp_path / "bakery.csv", _valid_rows())

    profile = parse_french_bakery_source(source)

    assert [row.source_row_number for row in profile.rows] == [2, 3]
    assert profile.rows[0].sale_date.isoformat() == "2021-01-02"
    assert profile.rows[0].unit_price_eur == parse_french_price("0,90 €")
    assert profile.rows[0].source_index == 0
    assert profile.quarantined_rows[0].source_row_number == 4


def test_malformed_nested_row_is_quarantined_without_reconstruction(tmp_path: Path) -> None:
    source = _write_nested_source(tmp_path / "bakery.csv", _valid_rows())

    evaluation = evaluate_french_bakery_compatibility(source)

    assert evaluation.counts.source_rows == 3
    assert evaluation.counts.parseable_rows == 2
    assert evaluation.counts.quarantined_rows == 1
    assert evaluation.forecast_eligibility is ForecastEligibility.WITHHELD
    assert evaluation.forecast_produced is False


def test_all_absent_semantics_have_specific_withholding_reasons(tmp_path: Path) -> None:
    source = _write_nested_source(tmp_path / "bakery.csv", _valid_rows())

    evaluation = evaluate_french_bakery_compatibility(source)

    assert {reason.code for reason in evaluation.withholding_reasons} == set(WithholdingReasonCode)
    reasons = {reason.code: reason for reason in evaluation.withholding_reasons}
    assert reasons[WithholdingReasonCode.UNKNOWN_NO_SALE_DATES].affected_rows == 1
    assert reasons[WithholdingReasonCode.UNCLASSIFIED_NON_POSITIVE_QUANTITY].affected_rows == 1


def test_missing_customer_identity_remains_blocked_by_shared_sales_contract() -> None:
    columns = ["date", "ticket_number", "article", "Quantity", "unit_price"]
    mapping = {
        "order_id": "ticket_number",
        "order_date": "date",
        "unit_price": "unit_price",
        "quantity": "Quantity",
        "product_name": "article",
    }

    result = validate_schema_mapping(
        columns,
        mapping,
        RevenueMode.UNIT_PRICE_TIMES_QUANTITY,
    )

    assert result["valid"] is False
    assert "customer_id" in result["missing_required_fields"]


def test_public_report_is_aggregate_only_and_deterministic(tmp_path: Path) -> None:
    source = _write_nested_source(tmp_path / "bakery.csv", _valid_rows())

    first = evaluate_french_bakery_compatibility(source)
    second = evaluate_french_bakery_compatibility(source)
    report = render_french_bakery_compatibility_markdown(first)

    assert first.to_aggregate_dict() == second.to_aggregate_dict()
    assert "source_row_number" not in str(first.to_aggregate_dict())
    assert "PRIVATE-PRODUCT" not in report
    assert "OTHER-ITEM" not in report
    assert "0,90" not in report
    assert "2021-01-02" not in report
    assert "150040" not in report
    assert "No forecast was produced" in report


def test_local_diagnostics_keep_affected_positions_outside_aggregate_result(
    tmp_path: Path,
) -> None:
    source = _write_nested_source(tmp_path / "bakery.csv", _valid_rows())
    profile = parse_french_bakery_source(source)
    evaluation = evaluate_french_bakery_compatibility(source)

    local_artifact = build_local_diagnostic_artifact(profile, evaluation)

    diagnostics = local_artifact["local_diagnostics"]
    assert diagnostics["quarantine_records"][0]["source_row_number"] == 4
    assert diagnostics["non_positive_quantity_source_rows"] == [3]


def test_private_output_must_remain_in_ignored_external_data_directory(
    tmp_path: Path,
) -> None:
    assert _is_external_local_path(tmp_path / "data/public/external/result.json")
    assert not _is_external_local_path(tmp_path / "docs/result.json")
