"""Compatibility evaluation for the nested French bakery public CSV.

This module is intentionally separate from the shared sales and product-demand
pipelines.  It establishes whether the external source contains the business
semantics required by those pipelines; it never invents those semantics or
produces a forecast.
"""

from __future__ import annotations

import csv
import hashlib
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from enum import Enum
from pathlib import Path
from typing import Any

SOURCE_NAME = "French Bakery Daily Sales"
SOURCE_URL = "https://github.com/Juli27co/French-bakery-daily-sales"
EXPECTED_HEADER = (
    "",
    "date",
    "time",
    "ticket_number",
    "article",
    "Quantity",
    "unit_price",
)


class ExternalSourceFormatError(ValueError):
    """The source file does not have the expected outer CSV structure."""


class ForecastEligibility(str, Enum):
    """Whether this compatibility check may enter the forecasting pipeline."""

    WITHHELD = "withheld"


class WithholdingReasonCode(str, Enum):
    """Stable, machine-readable reasons for withholding the forecast."""

    MISSING_CUSTOMER_IDENTITY = "missing_customer_identity"
    UNCONFIRMED_COMPLETED_SALES = "unconfirmed_completed_sales_status"
    UNKNOWN_NO_SALE_DATES = "unknown_no_sale_dates"
    UNCLASSIFIED_NON_POSITIVE_QUANTITY = "unclassified_non_positive_quantity"
    MISSING_UNIT_OF_MEASURE = "missing_unit_of_measure"
    MISSING_CATEGORY = "missing_product_category"


@dataclass(frozen=True)
class ParsedBakeryRow:
    """A safely parsed source row with its original physical CSV position."""

    source_row_number: int
    source_index: int
    sale_date: date
    sale_time: time
    quantity: Decimal
    unit_price_eur: Decimal


@dataclass(frozen=True)
class QuarantinedSourceRow:
    """A malformed row excluded without guessing or reconstruction."""

    source_row_number: int
    reason_code: str


@dataclass(frozen=True)
class BakerySourceProfile:
    """Parsed rows and local-only diagnostics from the source adapter."""

    source_sha256: str
    source_row_count: int
    rows: tuple[ParsedBakeryRow, ...]
    quarantined_rows: tuple[QuarantinedSourceRow, ...]


@dataclass(frozen=True)
class WithholdingReason:
    """One absent or unconfirmed business meaning and its aggregate scope."""

    code: WithholdingReasonCode
    affected_rows: int
    explanation: str


@dataclass(frozen=True)
class CompatibilityCounts:
    """Aggregate-only source facts safe for the committed report."""

    source_rows: int
    parseable_rows: int
    quarantined_rows: int
    affected_rows: int
    observed_calendar_dates: int
    calendar_span_days: int
    missing_calendar_dates: int
    non_positive_quantity_rows: int
    non_positive_unit_price_rows: int


@dataclass(frozen=True)
class BakeryCompatibilityEvaluation:
    """Typed outcome of the external-source compatibility checkpoint."""

    source_name: str
    source_url: str
    source_sha256: str
    forecast_eligibility: ForecastEligibility
    forecast_produced: bool
    counts: CompatibilityCounts
    withholding_reasons: tuple[WithholdingReason, ...]

    def to_aggregate_dict(self) -> dict[str, Any]:
        """Return the deterministic aggregate result without source row positions."""
        payload = asdict(self)
        payload["forecast_eligibility"] = self.forecast_eligibility.value
        payload["withholding_reasons"] = [
            {
                "code": reason.code.value,
                "affected_rows": reason.affected_rows,
                "explanation": reason.explanation,
            }
            for reason in self.withholding_reasons
        ]
        return payload


def parse_french_bakery_source(path: Path) -> BakerySourceProfile:
    """Unpack the nested rows while preserving physical source positions.

    The dataset stores each logical record as one quoted field containing a
    second CSV record.  Any row that cannot be parsed exactly is quarantined;
    records are never spliced together or otherwise repaired.
    """
    digest = hashlib.sha256()
    try:
        with path.open("rb") as binary_source:
            for block in iter(lambda: binary_source.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise ExternalSourceFormatError(f"Could not read source file: {exc}") from exc

    parsed_rows: list[ParsedBakeryRow] = []
    quarantined_rows: list[QuarantinedSourceRow] = []
    source_row_count = 0

    try:
        with path.open("r", encoding="utf-8-sig", newline="") as source:
            reader = csv.reader(source)
            header = next(reader, None)
            if tuple(header or ()) != EXPECTED_HEADER:
                raise ExternalSourceFormatError(
                    "Source header does not match the published French bakery schema."
                )

            for source_row_number, outer_row in enumerate(reader, start=2):
                source_row_count += 1
                parsed = _parse_nested_source_row(outer_row, source_row_number)
                if isinstance(parsed, QuarantinedSourceRow):
                    quarantined_rows.append(parsed)
                else:
                    parsed_rows.append(parsed)
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        raise ExternalSourceFormatError(f"Could not parse source file: {exc}") from exc

    return BakerySourceProfile(
        source_sha256=digest.hexdigest(),
        source_row_count=source_row_count,
        rows=tuple(parsed_rows),
        quarantined_rows=tuple(quarantined_rows),
    )


def evaluate_french_bakery_compatibility(path: Path) -> BakeryCompatibilityEvaluation:
    """Profile the source and explain why forecasting must be withheld."""
    profile = parse_french_bakery_source(path)
    return evaluate_french_bakery_profile(profile)


def evaluate_french_bakery_profile(
    profile: BakerySourceProfile,
) -> BakeryCompatibilityEvaluation:
    """Create the aggregate compatibility result from an already parsed profile."""
    observed_dates = {row.sale_date for row in profile.rows}
    calendar_span_days = _calendar_span_days(observed_dates)
    missing_calendar_dates = max(calendar_span_days - len(observed_dates), 0)

    non_positive_quantity_rows = tuple(
        row.source_row_number for row in profile.rows if row.quantity <= 0
    )
    non_positive_unit_price_rows = tuple(
        row.source_row_number for row in profile.rows if row.unit_price_eur <= 0
    )
    affected_source_rows = {record.source_row_number for record in profile.quarantined_rows}
    affected_source_rows.update(non_positive_quantity_rows)
    affected_source_rows.update(non_positive_unit_price_rows)

    parseable_count = len(profile.rows)
    reasons = (
        WithholdingReason(
            code=WithholdingReasonCode.MISSING_CUSTOMER_IDENTITY,
            affected_rows=parseable_count,
            explanation=(
                "The published source has transaction tickets but no stable customer identity."
            ),
        ),
        WithholdingReason(
            code=WithholdingReasonCode.UNCONFIRMED_COMPLETED_SALES,
            affected_rows=parseable_count,
            explanation=(
                "The source does not classify completed, cancelled, returned, or refunded rows."
            ),
        ),
        WithholdingReason(
            code=WithholdingReasonCode.UNKNOWN_NO_SALE_DATES,
            affected_rows=missing_calendar_dates,
            explanation=(
                "Dates without rows cannot be distinguished from closures, missing exports, "
                "stockouts, or genuine zero demand."
            ),
        ),
        WithholdingReason(
            code=WithholdingReasonCode.UNCLASSIFIED_NON_POSITIVE_QUANTITY,
            affected_rows=len(non_positive_quantity_rows),
            explanation=("Non-positive quantities exist without return or cancellation semantics."),
        ),
        WithholdingReason(
            code=WithholdingReasonCode.MISSING_UNIT_OF_MEASURE,
            affected_rows=parseable_count,
            explanation="The source does not define the unit represented by each quantity.",
        ),
        WithholdingReason(
            code=WithholdingReasonCode.MISSING_CATEGORY,
            affected_rows=parseable_count,
            explanation="The source does not provide a confirmed product-category hierarchy.",
        ),
    )

    return BakeryCompatibilityEvaluation(
        source_name=SOURCE_NAME,
        source_url=SOURCE_URL,
        source_sha256=profile.source_sha256,
        forecast_eligibility=ForecastEligibility.WITHHELD,
        forecast_produced=False,
        counts=CompatibilityCounts(
            source_rows=profile.source_row_count,
            parseable_rows=parseable_count,
            quarantined_rows=len(profile.quarantined_rows),
            affected_rows=len(affected_source_rows),
            observed_calendar_dates=len(observed_dates),
            calendar_span_days=calendar_span_days,
            missing_calendar_dates=missing_calendar_dates,
            non_positive_quantity_rows=len(non_positive_quantity_rows),
            non_positive_unit_price_rows=len(non_positive_unit_price_rows),
        ),
        withholding_reasons=reasons,
    )


def build_local_diagnostic_artifact(
    profile: BakerySourceProfile,
    evaluation: BakeryCompatibilityEvaluation,
) -> dict[str, Any]:
    """Add traceable row positions for the ignored local diagnostic artifact only."""
    return {
        "evaluation": evaluation.to_aggregate_dict(),
        "local_diagnostics": {
            "quarantine_records": [asdict(record) for record in profile.quarantined_rows],
            "non_positive_quantity_source_rows": [
                row.source_row_number for row in profile.rows if row.quantity <= 0
            ],
            "non_positive_unit_price_source_rows": [
                row.source_row_number for row in profile.rows if row.unit_price_eur <= 0
            ],
        },
    }


def render_french_bakery_compatibility_markdown(
    evaluation: BakeryCompatibilityEvaluation,
) -> str:
    """Render an aggregate-only report without transactions or business values."""
    counts = evaluation.counts
    reason_rows = "\n".join(
        f"| `{reason.code.value}` | {reason.affected_rows:,} | {reason.explanation} |"
        for reason in evaluation.withholding_reasons
    )
    return f"""# French Bakery External-Source Compatibility Evaluation

## Outcome

**Forecast eligibility: `{evaluation.forecast_eligibility.value}`. No forecast was produced.**

This is the expected safe result. The source can be parsed for aggregate profiling, but it
does not contain enough confirmed business semantics to enter the frozen product-demand
forecasting pipeline.

## Source provenance

- Source: [{evaluation.source_name}]({evaluation.source_url})
- Source type: external public dataset
- Permissioned independent-business export: no
- Source SHA-256: `{evaluation.source_sha256}`

## Aggregate findings

| Measure | Count |
| --- | ---: |
| Source rows | {counts.source_rows:,} |
| Parseable nested rows | {counts.parseable_rows:,} |
| Quarantined malformed rows | {counts.quarantined_rows:,} |
| Rows affected by a row-level quality issue | {counts.affected_rows:,} |
| Observed calendar dates | {counts.observed_calendar_dates:,} |
| Calendar span in days | {counts.calendar_span_days:,} |
| Dates with no source rows | {counts.missing_calendar_dates:,} |
| Rows with non-positive quantity | {counts.non_positive_quantity_rows:,} |
| Rows with non-positive unit price | {counts.non_positive_unit_price_rows:,} |

## Why forecasting was withheld

| Reason code | Aggregate scope | Meaning |
| --- | ---: | --- |
{reason_rows}

The adapter did not invent customer identities, order statuses, units, categories, closure
dates, stockout facts, or return meanings. The malformed source row was quarantined without
attempting to reconstruct it.

## Limitations and decision

- This result tests external-source compatibility, not forecast accuracy.
- It does not change the dashboard contract, forecasting methods, thresholds, or preview rules.
- It does not clear the permissioned independent-business evaluation checkpoint.
- It does not authorize RAG Phase 2.
- Raw rows, affected row positions, and detailed profiling output remain local and Git-ignored.

The successful outcome of this checkpoint is an explainable withheld forecast rather than a
forced prediction from ambiguous data.

## Reproduce locally

```bash
python3 -m scripts.evaluate_french_bakery_source \\
  --csv data/public/external/french_bakery_sales.csv \\
  --private-output data/public/external/french_bakery_compatibility.json \\
  --summary-output docs/evaluation/french_bakery_source_compatibility.md
```
"""


def _parse_nested_source_row(
    outer_row: list[str], source_row_number: int
) -> ParsedBakeryRow | QuarantinedSourceRow:
    if len(outer_row) != 1:
        return QuarantinedSourceRow(source_row_number, "malformed_outer_row")
    try:
        inner_row = next(csv.reader([outer_row[0]], strict=True))
    except csv.Error:
        return QuarantinedSourceRow(source_row_number, "malformed_nested_row")
    if len(inner_row) != len(EXPECTED_HEADER):
        return QuarantinedSourceRow(source_row_number, "malformed_nested_row")

    source_index, raw_date, raw_time, ticket_number, article, quantity, unit_price = inner_row
    if not ticket_number.strip() or not article.strip():
        return QuarantinedSourceRow(source_row_number, "missing_required_source_value")
    try:
        return ParsedBakeryRow(
            source_row_number=source_row_number,
            source_index=int(source_index),
            sale_date=datetime.strptime(raw_date, "%Y-%m-%d").date(),
            sale_time=datetime.strptime(raw_time, "%H:%M").time(),
            quantity=Decimal(quantity),
            unit_price_eur=parse_french_price(unit_price),
        )
    except (ValueError, InvalidOperation):
        return QuarantinedSourceRow(source_row_number, "invalid_source_value")


def parse_french_price(value: str) -> Decimal:
    """Parse a French decimal price such as ``0,90 €`` without using floats."""
    normalized = value.replace("\u00a0", " ").strip()
    if not normalized.endswith("€"):
        raise InvalidOperation("French price is missing its euro symbol.")
    numeric = normalized[:-1].replace(" ", "").replace(",", ".")
    if not numeric:
        raise InvalidOperation("French price has no numeric value.")
    return Decimal(numeric)


def _calendar_span_days(observed_dates: set[date]) -> int:
    if not observed_dates:
        return 0
    first_date = min(observed_dates)
    last_date = max(observed_dates)
    return ((last_date - first_date) // timedelta(days=1)) + 1
