from __future__ import annotations

import csv
import hashlib
import io
import zipfile
from pathlib import Path

import httpx
import pytest

from scripts.evaluate_pakistan_public_compatibility import _is_external_local_path
from src.product_demand.pakistan_public_compatibility import (
    EXPECTED_MEMBER,
    MAX_ARCHIVE_BYTES,
    PublicSourceError,
    audit_archive,
    fetch_archive,
    render_summary,
)

HEADERS = [
    "increment_id",
    "created_at",
    "Customer ID",
    "sku",
    "qty_ordered",
    "price",
    "grand_total",
    "status",
    "category_name_1",
]


def _archive(rows: list[list[str]], *, member: str = EXPECTED_MEMBER) -> bytes:
    csv_content = io.StringIO(newline="")
    writer = csv.writer(csv_content)
    writer.writerow(HEADERS)
    writer.writerows(rows)
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zipped:
        zipped.writestr(member, csv_content.getvalue())
    return archive.getvalue()


def _rows() -> list[list[str]]:
    return [
        [
            "ORDER-SECRET",
            "2025-01-02",
            "CUSTOMER-SECRET",
            "SKU-SECRET",
            "2",
            "10.00",
            "20.00",
            "complete",
            "Home",
        ],
        [
            "ORDER-SECRET",
            "2025-01-02",
            "CUSTOMER-SECRET",
            "SKU-OTHER",
            "1",
            "20.00",
            "20.00",
            "complete",
            "Home",
        ],
        ["ORDER-2", "1/2/2025", "\\N", "", "-1", "bad", "10.00", "order_refunded", "Home"],
        ["ORDER-3", "not-a-date", "CUSTOMER-3", "SKU-3", "1", "5.00", "5.00", "received", "Home"],
    ]


def test_fetches_fixed_url_without_writing_a_raw_file() -> None:
    payload = _archive(_rows())
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=payload))

    assert fetch_archive(transport) == payload


def test_network_failure_and_oversized_archive_fail_closed() -> None:
    failed = httpx.MockTransport(lambda request: httpx.Response(503))
    with pytest.raises(PublicSourceError, match="unavailable"):
        fetch_archive(failed)
    oversized = httpx.MockTransport(
        lambda request: httpx.Response(200, content=b"x" * (MAX_ARCHIVE_BYTES + 1))
    )
    with pytest.raises(PublicSourceError, match="transfer cap"):
        fetch_archive(oversized)


def test_zip_member_and_malformed_archives_are_rejected() -> None:
    with pytest.raises(PublicSourceError, match="malformed"):
        audit_archive(b"not a zip")
    with pytest.raises(PublicSourceError, match="exactly one"):
        audit_archive(_archive(_rows(), member="other.csv"))
    duplicate = io.BytesIO()
    with zipfile.ZipFile(duplicate, "w") as zipped:
        zipped.writestr(EXPECTED_MEMBER, "a\n1\n")
        zipped.writestr(f"nested/{EXPECTED_MEMBER}", "a\n1\n")
    with pytest.raises(PublicSourceError, match="exactly one"):
        audit_archive(duplicate.getvalue())


def test_full_profile_counts_ambiguities_and_never_forecasts() -> None:
    payload = _archive(_rows())
    audit = audit_archive(payload)
    assert audit.source_sha256 == hashlib.sha256(payload).hexdigest()
    assert audit.source_rows == 4
    assert audit.schema_mapping_valid
    assert audit.repeated_order_total_rows == 1
    assert audit.distinct_status_count == 3
    assert dict(audit.issue_counts) == {
        "invalid_order_date": 1,
        "invalid_unit_price": 1,
        "missing_customer_id": 1,
        "missing_sku": 1,
        "non_positive_quantity": 1,
        "unconfirmed_slash_date_format": 1,
    }
    assert "unconfirmed_stockout_tracking" in audit.withholding_reasons
    assert "unconfirmed_open_day_coverage" in audit.withholding_reasons
    assert "unclassified_order_statuses" in audit.withholding_reasons
    assert audit.private_dict()["forecast_produced"] is False
    assert audit.private_dict()["forecast_eligibility"] == "withheld"


def test_aggregate_report_is_deterministic_and_contains_no_source_values() -> None:
    payload = _archive(_rows())
    first = render_summary(audit_archive(payload))
    assert first == render_summary(audit_archive(payload))
    for secret in ("ORDER-SECRET", "CUSTOMER-SECRET", "SKU-SECRET", "2025-01-02", "10.00"):
        assert secret not in first
    assert "forecast accuracy" in first
    assert "no forecast was produced" in first


def test_missing_contract_columns_are_reported_without_inventing_them() -> None:
    content = io.BytesIO()
    with zipfile.ZipFile(content, "w") as zipped:
        zipped.writestr(EXPECTED_MEMBER, "increment_id,created_at,sku\nA,2025-01-01,P\n")
    audit = audit_archive(content.getvalue())
    assert not audit.schema_mapping_valid
    assert set(audit.missing_required_fields) == {"customer_id", "unit_price", "quantity"}
    assert "missing_required_sales_mapping" in audit.withholding_reasons


def test_unnamed_source_columns_are_counted_without_using_their_values() -> None:
    content = io.BytesIO()
    csv_source = io.StringIO(newline="")
    writer = csv.writer(csv_source)
    writer.writerow([*HEADERS, "", ""])
    writer.writerow([*_rows()[0], "", "PRIVATE-EXTRA"])
    with zipfile.ZipFile(content, "w") as zipped:
        zipped.writestr(EXPECTED_MEMBER, csv_source.getvalue())
    audit = audit_archive(content.getvalue())
    assert dict(audit.issue_counts)["unnamed_header_columns"] == 2
    assert dict(audit.issue_counts)["rows_with_unnamed_column_values"] == 1
    assert "PRIVATE-EXTRA" not in render_summary(audit)


def test_padded_blank_records_do_not_masquerade_as_invalid_orders() -> None:
    audit = audit_archive(_archive([_rows()[0], [""] * len(HEADERS)]))
    assert audit.source_rows == 2
    assert dict(audit.issue_counts)["blank_source_row"] == 1
    assert "missing_customer_id" not in dict(audit.issue_counts)
    assert dict(audit.status_class_counts) == {"completed_label": 1}


def test_private_artifact_directory_is_required(tmp_path: Path) -> None:
    assert _is_external_local_path(tmp_path / "data/public/external/result.json")
    assert not _is_external_local_path(tmp_path / "docs/result.json")
