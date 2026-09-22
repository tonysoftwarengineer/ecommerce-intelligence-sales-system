"""Strict, forecast-free audit of the public Pakistan e-commerce archive."""

from __future__ import annotations

import csv
import hashlib
import io
import re
import zipfile
from collections import Counter
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import PurePosixPath
from typing import Any

import httpx

from src.generic_sales.contracts import RevenueMode
from src.schema_mapping import validate_schema_mapping

SOURCE_URL = (
    "https://opendata.com.pk/dataset/a6a52e2b-c209-4f9f-8b99-eb67ef33d04e/"
    "resource/7395e1d0-c02b-4e1d-abb8-84ae52681ffb/download/archive.zip"
)
SOURCE_PAGE = (
    "https://opendata.com.pk/dataset/pakistan-largest-ecommerce-dataset/"
    "resource/7395e1d0-c02b-4e1d-abb8-84ae52681ffb"
)
EXPECTED_MEMBER = "Pakistan Largest Ecommerce Dataset.csv"
MAX_ARCHIVE_BYTES = 25_000_000
MAX_CSV_BYTES = 160_000_000
MAX_SOURCE_ROWS = 2_000_000
SOURCE_MAPPING = {
    "order_id": "increment_id",
    "order_date": "created_at",
    "customer_id": "Customer ID",
    "unit_price": "price",
    "quantity": "qty_ordered",
    "product_id": "sku",
    "product_category": "category_name_1",
    "order_status": "status",
}
PLACEHOLDERS = frozenset({"", "\\n", "\\N", "null", "none", "nan", "na", "n/a"})
NUMBER = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)")
ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}(?:[ T].*)?")
SLASH_DATE = re.compile(r"\d{1,2}/\d{1,2}/\d{4}(?:[ T].*)?")


class PublicSourceError(ValueError):
    """The remote source cannot be audited safely."""


@dataclass(frozen=True)
class CompatibilityAudit:
    source_sha256: str
    source_rows: int
    schema_mapping_valid: bool
    missing_required_fields: tuple[str, ...]
    issue_counts: tuple[tuple[str, int], ...]
    status_class_counts: tuple[tuple[str, int], ...]
    distinct_status_count: int
    repeated_order_total_rows: int
    conflicting_order_total_rows: int
    withholding_reasons: tuple[str, ...]
    private_status_counts: tuple[tuple[str, int], ...]
    source_columns: tuple[str, ...]

    def private_dict(self) -> dict[str, Any]:
        return {
            "source_url": SOURCE_URL,
            "source_sha256": self.source_sha256,
            "source_rows": self.source_rows,
            "source_columns": list(self.source_columns),
            "schema_mapping_valid": self.schema_mapping_valid,
            "missing_required_fields": list(self.missing_required_fields),
            "issue_counts": dict(self.issue_counts),
            "status_class_counts": dict(self.status_class_counts),
            "distinct_status_count": self.distinct_status_count,
            "status_values": dict(self.private_status_counts),
            "repeated_order_total_rows": self.repeated_order_total_rows,
            "conflicting_order_total_rows": self.conflicting_order_total_rows,
            "forecast_eligibility": "withheld",
            "forecast_produced": False,
            "withholding_reasons": list(self.withholding_reasons),
        }


def fetch_archive(transport: httpx.BaseTransport | None = None) -> bytes:
    """Fetch the fixed source URL into bounded memory; never persist raw bytes."""
    try:
        with httpx.Client(transport=transport, follow_redirects=True, timeout=45) as client:
            with client.stream("GET", SOURCE_URL) as response:
                response.raise_for_status()
                archive = bytearray()
                for chunk in response.iter_bytes():
                    if len(archive) + len(chunk) > MAX_ARCHIVE_BYTES:
                        raise PublicSourceError("Source archive exceeds the 25 MB transfer cap.")
                    archive.extend(chunk)
    except httpx.HTTPError as exc:
        raise PublicSourceError("Source URL is unavailable; no audit was produced.") from exc
    if not archive:
        raise PublicSourceError("Source URL returned an empty archive.")
    return bytes(archive)


def audit_archive(archive: bytes) -> CompatibilityAudit:
    if len(archive) > MAX_ARCHIVE_BYTES:
        raise PublicSourceError("Source archive exceeds the 25 MB transfer cap.")
    try:
        with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
            members = [
                item
                for item in zipped.infolist()
                if not item.is_dir()
                and PurePosixPath(item.filename).name.casefold() == EXPECTED_MEMBER.casefold()
            ]
            if len(members) != 1:
                raise PublicSourceError("Expected exactly one published Pakistan CSV member.")
            member = members[0]
            if member.file_size > MAX_CSV_BYTES:
                raise PublicSourceError("Source CSV exceeds the 160 MB expanded-size cap.")
            with zipped.open(member) as binary:
                with io.TextIOWrapper(binary, encoding="utf-8-sig", newline="") as text_source:
                    return _profile_csv(text_source, hashlib.sha256(archive).hexdigest())
    except (zipfile.BadZipFile, UnicodeError, OSError, EOFError, csv.Error) as exc:
        raise PublicSourceError(
            "Source archive or CSV is malformed; no audit was produced."
        ) from exc


def _profile_csv(source: io.TextIOBase, source_sha256: str) -> CompatibilityAudit:
    reader = csv.DictReader(source)
    raw_columns = tuple(reader.fieldnames or ())
    named_columns = tuple(column for column in raw_columns if column.strip())
    if not named_columns or len(named_columns) != len(set(named_columns)):
        raise PublicSourceError("Source CSV has no usable unique named columns.")
    unnamed_columns = tuple(
        f"__unnamed_column_{index}"
        for index, column in enumerate(raw_columns)
        if not column.strip()
    )
    columns = tuple(
        column if column.strip() else f"__unnamed_column_{index}"
        for index, column in enumerate(raw_columns)
    )
    reader.fieldnames = list(columns)
    present_mapping = {
        field: column for field, column in SOURCE_MAPPING.items() if column in columns
    }
    mapping = validate_schema_mapping(
        columns, present_mapping, RevenueMode.UNIT_PRICE_TIMES_QUANTITY
    )
    issues: Counter[str] = Counter()
    if unnamed_columns:
        issues["unnamed_header_columns"] = len(unnamed_columns)
    status_values: Counter[str] = Counter()
    status_classes: Counter[str] = Counter()
    order_totals: dict[str, str] = {}
    repeated_total_rows = 0
    conflicting_total_rows = 0
    source_rows = 0
    for row in reader:
        source_rows += 1
        if source_rows > MAX_SOURCE_ROWS:
            raise PublicSourceError("Source CSV exceeds the two-million-row audit cap.")
        if None in row or any(value is None for value in row.values()):
            issues["malformed_row"] += 1
            continue
        if all(_missing(row[column]) for column in columns):
            issues["blank_source_row"] += 1
            continue
        if any(not _missing(row[column]) for column in unnamed_columns):
            issues["rows_with_unnamed_column_values"] += 1
        for field in ("increment_id", "Customer ID", "sku"):
            if field in columns and _missing(row[field]):
                issues[f"missing_{_field_code(field)}"] += 1
        if "created_at" in columns:
            raw_date = (row["created_at"] or "").strip()
            if _missing(raw_date):
                issues["missing_order_date"] += 1
            elif ISO_DATE.fullmatch(raw_date):
                try:
                    date.fromisoformat(raw_date[:10])
                except ValueError:
                    issues["invalid_order_date"] += 1
            elif SLASH_DATE.fullmatch(raw_date):
                issues["unconfirmed_slash_date_format"] += 1
            else:
                issues["invalid_order_date"] += 1
        for field, code in (
            ("qty_ordered", "quantity"),
            ("price", "unit_price"),
            ("grand_total", "grand_total"),
        ):
            if field not in columns:
                continue
            value = _decimal(row[field])
            if value is None:
                issues[f"invalid_{code}"] += 1
            elif value <= 0:
                issues[f"non_positive_{code}"] += 1
        if "status" in columns:
            status = (row["status"] or "").strip().casefold()
            status_values[status] += 1
            status_classes[_status_class(status)] += 1
        if "increment_id" in columns and "grand_total" in columns:
            order_id = (row["increment_id"] or "").strip()
            total = (row["grand_total"] or "").strip()
            if not _missing(order_id) and _decimal(total) is not None:
                if order_id in order_totals:
                    if order_totals[order_id] == total:
                        repeated_total_rows += 1
                    else:
                        conflicting_total_rows += 1
                else:
                    order_totals[order_id] = total

    reasons = [
        "mixed_merchant_source",
        "unconfirmed_open_day_coverage",
        "unconfirmed_stockout_tracking",
        "unconfirmed_unit_of_measure",
        "unconfirmed_revenue_authority",
    ]
    if not mapping["valid"]:
        reasons.append("missing_required_sales_mapping")
    if issues["unconfirmed_slash_date_format"]:
        reasons.append("unconfirmed_date_format")
    if status_classes["unknown"] or status_classes["refund_ambiguous"]:
        reasons.append("unclassified_order_statuses")
    if issues["invalid_quantity"] or issues["non_positive_quantity"]:
        reasons.append("unsafe_quantity_rows")
    return CompatibilityAudit(
        source_sha256=source_sha256,
        source_rows=source_rows,
        schema_mapping_valid=bool(mapping["valid"]),
        missing_required_fields=tuple(mapping["missing_required_fields"]),
        issue_counts=tuple(sorted(issues.items())),
        status_class_counts=tuple(sorted(status_classes.items())),
        distinct_status_count=len(status_values),
        repeated_order_total_rows=repeated_total_rows,
        conflicting_order_total_rows=conflicting_total_rows,
        withholding_reasons=tuple(reasons),
        private_status_counts=tuple(sorted(status_values.items())),
        source_columns=named_columns,
    )


def _missing(value: str | None) -> bool:
    return value is None or value.strip().casefold() in PLACEHOLDERS


def _field_code(field: str) -> str:
    return {"increment_id": "order_id", "Customer ID": "customer_id", "sku": "sku"}[field]


def _decimal(value: str | None) -> Decimal | None:
    if value is None or not NUMBER.fullmatch(value.strip()):
        return None
    try:
        result = Decimal(value.strip())
    except InvalidOperation:
        return None
    return result if result.is_finite() else None


def _status_class(value: str) -> str:
    if value in {"complete", "completed"}:
        return "completed_label"
    if value in {"canceled", "cancelled"}:
        return "cancelled_label"
    if value in {"refund", "refunded", "order_refunded"}:
        return "refund_ambiguous"
    return "unknown"


def render_summary(audit: CompatibilityAudit) -> str:
    issue_rows = "\n".join(f"| `{code}` | {count:,} |" for code, count in audit.issue_counts)
    status_rows = "\n".join(
        f"| `{code}` | {count:,} |" for code, count in audit.status_class_counts
    )
    reasons = "\n".join(f"- `{code}`" for code in audit.withholding_reasons)
    return f"""# Pakistan online-retail public-source compatibility audit

This is a **multi-merchant public dataset**, not one permissioned small-retailer
export. It tests source compatibility and safe withholding, **not forecast accuracy**.
The [source listing]({SOURCE_PAGE}) specifies no reuse license. No raw source or
transaction-level derivative is published in this repository.

- Source URL: {SOURCE_URL}
- Archive SHA-256: `{audit.source_sha256}`
- Source rows audited: {audit.source_rows:,}
- Nonblank records: {audit.source_rows - dict(audit.issue_counts).get("blank_source_row", 0):,}
- Structural sales mapping valid: {str(audit.schema_mapping_valid).lower()}
- Missing required mapped fields: {", ".join(audit.missing_required_fields) or "none"}
- Distinct status labels: {audit.distinct_status_count}
- Same grand-total text repeated within an order: {audit.repeated_order_total_rows:,} rows
- Conflicting grand-total text within an order: {audit.conflicting_order_total_rows:,} rows
- Forecast eligibility: **withheld**; no forecast was produced.

## Source quality counts

| Issue code | Count |
| --- | ---: |
{issue_rows or "| none | 0 |"}

## Status-label counts

These are labels in the source, not confirmed accounting or fulfillment rules.

| Label class | Rows |
| --- | ---: |
{status_rows or "| none | 0 |"}

## Why forecasting is withheld

{reasons}

Open-day coverage, stockout completeness, unit meaning, and revenue authority
remain unconfirmed. Missing product-day rows are **not** treated as zero sales.
The independent-business forecast checkpoint and the RAG Phase 2 locked test
remain separate and pending.

## Reproduce

From the repository root, run `python3 -m scripts.evaluate_pakistan_public_compatibility`.
The command fetches the fixed ZIP URL into bounded memory, streams its CSV,
writes detailed aggregate diagnostics to ignored `data/public/external/`, and
regenerates this Markdown report. It does not retain the raw archive or rows.
"""
