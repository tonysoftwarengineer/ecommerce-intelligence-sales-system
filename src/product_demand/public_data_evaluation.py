"""Dataset adapters and aggregate evidence for Milestone 11B public evaluation.

The adapters in this module are deliberately outside the baseline formulas. They
translate two documented public schemas into the same ``EvaluationSeries``
contract used by the synthetic scenarios; they do not alter forecasting rules.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType

import pandas as pd

from src.generic_sales.contracts import RevenueMode
from src.product_demand.calendar import build_product_demand_calendar
from src.product_demand.contracts import (
    ProductDateStatus,
    ProductDemandAssumptions,
)
from src.product_demand.evaluation_contracts import (
    BaselineCandidate,
    EvaluationAvailability,
    EvaluationConfiguration,
    EvaluationSeries,
    EvaluationSeriesPoint,
    ProductEvaluationReport,
)
from src.product_demand.evaluation_series import prepare_evaluation_series
from src.product_demand.metrics import evaluate_product_baselines

UCI_REQUIRED_COLUMNS = (
    "Invoice",
    "StockCode",
    "Description",
    "Quantity",
    "InvoiceDate",
)
M5_ID_COLUMNS = ("id", "item_id", "dept_id", "cat_id", "store_id", "state_id")
M5_STRATA = ("delayed_start", "sparse", "intermittent", "dense")


@dataclass(frozen=True)
class _M5SeriesMetadata:
    row_position: int
    source_id: str
    stratum: str
    first_day: int | None
    nonzero_days: int
    active_days: int


@dataclass(frozen=True)
class PublicProductProfile:
    """Descriptive sampling evidence; no field is a production trust label."""

    product_key: str
    source_id: str
    stratum: str
    first_date: date
    calendar_days: int
    nonzero_days: int
    zero_target_days: int
    observed_days: int
    confirmed_zero_days: int
    first_source_day_number: int | None = None

    def __post_init__(self) -> None:
        if not self.product_key.strip() or not self.source_id.strip() or not self.stratum.strip():
            raise ValueError("Public product profile text fields must not be blank")
        if self.calendar_days <= 0:
            raise ValueError("Public product profiles require at least one calendar day")
        if any(
            value < 0
            for value in (
                self.nonzero_days,
                self.zero_target_days,
                self.observed_days,
                self.confirmed_zero_days,
            )
        ):
            raise ValueError("Public product profile day counts must not be negative")
        if self.nonzero_days + self.zero_target_days != self.calendar_days:
            raise ValueError("Public product target day counts must equal calendar_days")
        if self.observed_days + self.confirmed_zero_days != self.calendar_days:
            raise ValueError("Public product status day counts must equal calendar_days")
        if self.first_source_day_number is not None and self.first_source_day_number <= 0:
            raise ValueError("first_source_day_number must be positive when present")


@dataclass(frozen=True)
class PublicDatasetPreparation:
    """A reproducible public-data sample prepared for the unchanged evaluator."""

    dataset_name: str
    evaluation_mode: str
    source_row_count: int
    source_product_count: int
    selected_source_ids: tuple[str, ...]
    series: tuple[EvaluationSeries, ...]
    profiles: tuple[PublicProductProfile, ...]
    evidence_counts: Mapping[str, int] = field(default_factory=dict)
    assumptions: tuple[str, ...] = field(default_factory=tuple)
    limitations: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.dataset_name.strip() or not self.evaluation_mode.strip():
            raise ValueError("Public dataset name and evaluation mode must not be blank")
        if self.source_row_count < 0 or self.source_product_count < 0:
            raise ValueError("Public source counts must not be negative")
        selected = tuple(self.selected_source_ids)
        series = tuple(self.series)
        profiles = tuple(self.profiles)
        if len(selected) != len(set(selected)):
            raise ValueError("Selected public source ids must be unique")
        if len(series) != len(profiles):
            raise ValueError("Every public evaluation series requires one profile")
        if {item.product_key for item in series} != {profile.product_key for profile in profiles}:
            raise ValueError("Public profiles must match prepared evaluation series")
        counts = {str(name): int(value) for name, value in self.evidence_counts.items()}
        if any(value < 0 for value in counts.values()):
            raise ValueError("Public evidence counts must not be negative")
        object.__setattr__(self, "selected_source_ids", selected)
        object.__setattr__(self, "series", series)
        object.__setattr__(self, "profiles", profiles)
        object.__setattr__(self, "evidence_counts", MappingProxyType(counts))
        object.__setattr__(self, "assumptions", tuple(self.assumptions))
        object.__setattr__(self, "limitations", tuple(self.limitations))


def load_uci_public_evaluation(
    workbook: Path,
    *,
    product_limit: int = 25,
) -> PublicDatasetPreparation:
    """Load the official UCI workbook and prepare a bounded research sample."""
    sheets = pd.read_excel(
        workbook,
        sheet_name=None,
        usecols=list(UCI_REQUIRED_COLUMNS),
        dtype={"Invoice": str, "StockCode": str, "Description": str},
    )
    source = pd.concat(sheets.values(), ignore_index=True)
    return prepare_uci_public_evaluation(source, product_limit=product_limit)


def prepare_uci_public_evaluation(
    source: pd.DataFrame,
    *,
    product_limit: int = 25,
) -> PublicDatasetPreparation:
    """Adapt UCI transactions without hiding negative-quantity ambiguity.

    The actual baseline evaluation is explicitly a research-only complete-ledger
    view. A strict view is also built and counted to prove that absent dates stay
    unknown when completeness is not asserted.
    """
    if product_limit <= 0:
        raise ValueError("product_limit must be positive")
    missing = sorted(set(UCI_REQUIRED_COLUMNS) - set(source.columns))
    if missing:
        raise ValueError(f"UCI source is missing required columns: {missing}")

    normalized = source.loc[:, list(UCI_REQUIRED_COLUMNS)].copy(deep=True)
    normalized["StockCode"] = normalized["StockCode"].fillna("").astype(str).str.strip()
    normalized["Invoice"] = normalized["Invoice"].fillna("").astype(str).str.strip()
    normalized["Description"] = normalized["Description"].fillna("").astype(str).str.strip()
    normalized["InvoiceDate"] = pd.to_datetime(normalized["InvoiceDate"], errors="coerce")
    normalized["Quantity"] = pd.to_numeric(normalized["Quantity"], errors="coerce")

    identified = normalized.loc[normalized["StockCode"] != ""].copy()
    selected_ids = _top_uci_product_ids(identified, product_limit)
    sample = identified.loc[identified["StockCode"].isin(selected_ids)].copy()
    cancelled = sample["Invoice"].str.upper().str.startswith("C", na=False)
    canonical = pd.DataFrame(
        {
            "source_row": sample.index + 2,
            "product_id": sample["StockCode"],
            "product_name": sample["Description"],
            "quantity": sample["Quantity"],
            "returned_quantity": None,
            "order_status": cancelled.map({True: "cancelled", False: "completed"}),
            "order_date": sample["InvoiceDate"],
            "recognition_date": sample["InvoiceDate"],
        }
    ).reset_index(drop=True)

    strict = build_product_demand_calendar(
        canonical,
        RevenueMode.ROW_TOTAL,
        ProductDemandAssumptions(default_unit_of_measure="source_item"),
    )
    research = build_product_demand_calendar(
        canonical,
        RevenueMode.ROW_TOTAL,
        ProductDemandAssumptions(
            default_unit_of_measure="source_item",
            export_covers_all_open_days=True,
        ),
    )
    series = prepare_evaluation_series(research.calendar)
    profiles = tuple(_profile_series(item, "high_transaction_frequency") for item in series)

    strict_readiness = Counter(item.status.value for item in strict.readiness.products)
    research_readiness = Counter(item.status.value for item in research.readiness.products)
    strict_statuses = Counter(strict.calendar["status"])
    research_statuses = Counter(research.calendar["status"])
    negative = normalized["Quantity"].lt(0)
    cancellations = normalized["Invoice"].str.upper().str.startswith("C", na=False)
    evidence = {
        "rows_without_product_code": int((normalized["StockCode"] == "").sum()),
        "invalid_date_rows": int(normalized["InvoiceDate"].isna().sum()),
        "invalid_quantity_rows": int(normalized["Quantity"].isna().sum()),
        "negative_quantity_rows": int(negative.sum()),
        "cancellation_rows": int(cancellations.sum()),
        "negative_non_cancellation_rows": int((negative & ~cancellations).sum()),
        "sample_source_rows": len(canonical),
        "strict_missing_unknown_days": int(
            strict_statuses[ProductDateStatus.MISSING_UNKNOWN.value]
        ),
        "strict_limited_products": int(strict_readiness["limited"]),
        "strict_unavailable_products": int(strict_readiness["unavailable"]),
        "research_observed_days": int(research_statuses[ProductDateStatus.OBSERVED.value]),
        "research_confirmed_zero_days": int(
            research_statuses[ProductDateStatus.CONFIRMED_ZERO.value]
        ),
        "research_limited_products": int(research_readiness["limited"]),
        "research_unavailable_products": int(research_readiness["unavailable"]),
        "research_evaluated_products": len(series),
    }
    return PublicDatasetPreparation(
        dataset_name="UCI Online Retail II",
        evaluation_mode="research_only_complete_transaction_ledger",
        source_row_count=len(normalized),
        source_product_count=int(identified["StockCode"].nunique()),
        selected_source_ids=selected_ids,
        series=series,
        profiles=profiles,
        evidence_counts=evidence,
        assumptions=(
            "StockCode is the stable source product identity.",
            "Invoice identifiers beginning with C are pre-fulfilment cancellations.",
            "For evaluation only, absent product rows inside the observed product window are "
            "treated as confirmed zero sales from a complete transaction ledger.",
            "The source unit is labelled source_item; no stocking conversion is inferred.",
        ),
        limitations=(
            "UCI does not prove stockout completeness, business-open dates, or real stocking "
            "units, so the sample measures observed fulfilled sales only.",
            "Products with zero or ambiguous negative non-cancellation quantities remain "
            "unavailable instead of being silently repaired.",
            "The top transaction-frequency sample is a stress sample, not a representative "
            "estimate of all retailers or all UCI products.",
        ),
    )


def load_m5_public_evaluation(
    sales_path: Path,
    calendar_path: Path,
    *,
    per_stratum: int = 6,
    sample_seed: str = "milestone-11b-public-v1",
    excluded_source_ids: frozenset[str] = frozenset(),
) -> PublicDatasetPreparation:
    """Load M5 with bounded integer dtypes before deterministic stratified sampling."""
    header = pd.read_csv(sales_path, nrows=0).columns.tolist()
    day_columns = _m5_day_columns(header)
    dtypes = {column: "int32" for column in day_columns}
    sales = pd.read_csv(sales_path, dtype=dtypes)
    calendar = pd.read_csv(calendar_path, usecols=["d", "date"])
    return prepare_m5_public_evaluation(
        sales,
        calendar,
        per_stratum=per_stratum,
        sample_seed=sample_seed,
        excluded_source_ids=excluded_source_ids,
    )


def prepare_m5_public_evaluation(
    sales: pd.DataFrame,
    calendar: pd.DataFrame,
    *,
    per_stratum: int = 6,
    sample_seed: str = "milestone-11b-public-v1",
    excluded_source_ids: frozenset[str] = frozenset(),
) -> PublicDatasetPreparation:
    """Create a deterministic item-store sample spanning four demand patterns."""
    if per_stratum <= 0:
        raise ValueError("per_stratum must be positive")
    if not sample_seed.strip():
        raise ValueError("sample_seed must not be blank")
    missing_ids = sorted(set(M5_ID_COLUMNS) - set(sales.columns))
    if missing_ids:
        raise ValueError(f"M5 sales source is missing identifier columns: {missing_ids}")
    if sales["id"].isna().any() or sales["id"].astype(str).duplicated().any():
        raise ValueError("M5 source ids must be non-blank and unique")
    day_columns = _m5_day_columns(sales.columns)
    values = sales.loc[:, day_columns].apply(pd.to_numeric, errors="coerce")
    if values.isna().any().any():
        raise ValueError("M5 daily sales values must be numeric and complete")
    if values.lt(0).any().any():
        raise ValueError("M5 daily sales values must not be negative")
    date_by_day = _m5_date_mapping(calendar, day_columns)

    metadata: list[_M5SeriesMetadata] = []
    for row_position, (_, row) in enumerate(sales.iterrows()):
        row_values = values.iloc[row_position]
        positive = row_values.gt(0)
        if not bool(positive.any()):
            metadata.append(
                _M5SeriesMetadata(
                    row_position=row_position,
                    source_id=str(row["id"]),
                    stratum="all_zero",
                    first_day=None,
                    nonzero_days=0,
                    active_days=0,
                )
            )
            continue
        first_column = str(positive.idxmax())
        first_day = int(first_column[2:])
        active_days = len(day_columns) - day_columns.index(first_column)
        nonzero_days = int(positive.sum())
        ratio = Decimal(nonzero_days) / Decimal(active_days)
        metadata.append(
            _M5SeriesMetadata(
                row_position=row_position,
                source_id=str(row["id"]),
                stratum=_m5_stratum(first_day, ratio),
                first_day=first_day,
                nonzero_days=nonzero_days,
                active_days=active_days,
            )
        )

    normalized_exclusions = frozenset(str(value) for value in excluded_source_ids)
    selected_metadata = _select_m5_metadata(
        metadata,
        per_stratum,
        sample_seed,
        normalized_exclusions,
    )
    series: list[EvaluationSeries] = []
    profiles: list[PublicProductProfile] = []
    for item in selected_metadata:
        row = sales.iloc[item.row_position]
        if item.first_day is None:
            raise AssertionError("Selected M5 series must contain at least one positive sale")
        first_day = item.first_day
        active_columns = tuple(column for column in day_columns if int(column[2:]) >= first_day)
        points = tuple(
            EvaluationSeriesPoint(
                date=date_by_day[column],
                status=(
                    ProductDateStatus.OBSERVED
                    if Decimal(str(row[column])) > 0
                    else ProductDateStatus.CONFIRMED_ZERO
                ),
                target_units=Decimal(str(row[column])),
                included=True,
            )
            for column in active_columns
        )
        product_key = f"m5:{item.source_id}"
        prepared = EvaluationSeries(
            product_key=product_key,
            unit_of_measure="source_item",
            points=points,
        )
        series.append(prepared)
        profiles.append(
            PublicProductProfile(
                product_key=product_key,
                source_id=item.source_id,
                stratum=item.stratum,
                first_date=points[0].date,
                calendar_days=len(points),
                nonzero_days=item.nonzero_days,
                zero_target_days=len(points) - item.nonzero_days,
                observed_days=item.nonzero_days,
                confirmed_zero_days=len(points) - item.nonzero_days,
                first_source_day_number=first_day,
            )
        )

    population = Counter(item.stratum for item in metadata)
    selected = Counter(item.stratum for item in selected_metadata)
    evidence = {
        "source_day_columns": len(day_columns),
        "population_all_zero": int(population["all_zero"]),
        "excluded_source_products": len(normalized_exclusions),
        "prelaunch_zero_days_trimmed": sum(
            item.first_day - 1 for item in selected_metadata if item.first_day is not None
        ),
    }
    for stratum in M5_STRATA:
        evidence[f"population_{stratum}"] = int(population[stratum])
        evidence[f"selected_{stratum}"] = int(selected[stratum])

    return PublicDatasetPreparation(
        dataset_name="M5 Forecasting Accuracy",
        evaluation_mode="deterministic_stratified_item_store_sample",
        source_row_count=len(sales),
        source_product_count=int(sales["id"].nunique()),
        selected_source_ids=tuple(item.source_id for item in selected_metadata),
        series=tuple(series),
        profiles=tuple(profiles),
        evidence_counts=evidence,
        assumptions=(
            "Each M5 item-store id is one product series at one store.",
            "Explicit daily zeros after first sale are confirmed zero observed sales.",
            "Zeros before first sale are trimmed as pre-observation history, not treated as "
            "proof of active zero demand.",
            "The public sample uses a fixed hash seed within four descriptive strata.",
        ),
        limitations=(
            "M5 records observed unit sales, not uncensored customer demand; stockouts can make "
            "sales lower than latent demand.",
            "The project evaluates a seven-day horizon and unweighted product-level evidence, "
            "not the competition's 28-day hierarchical WRMSSE objective.",
            "The 10% and 50% nonzero-day boundaries organize the sample only; they are not "
            "production trust thresholds.",
        ),
    )


def evaluate_public_series(
    preparation: PublicDatasetPreparation,
    configuration: EvaluationConfiguration | None = None,
) -> tuple[ProductEvaluationReport, ...]:
    """Run the unchanged baseline evaluator over every prepared public series."""
    policy = configuration or EvaluationConfiguration()
    return tuple(evaluate_product_baselines(series, policy) for series in preparation.series)


def public_evaluation_evidence(
    preparation: PublicDatasetPreparation,
    reports: Iterable[ProductEvaluationReport],
) -> dict[str, object]:
    """Build JSON-ready aggregate evidence without raw transaction rows."""
    report_items = tuple(reports)
    report_by_key = {report.product_key: report for report in report_items}
    if set(report_by_key) != {series.product_key for series in preparation.series}:
        raise ValueError("Public evaluation reports must match the prepared product series")

    daily_winners = Counter(
        report.daily_winner.value for report in report_items if report.daily_winner is not None
    )
    daily_rank_one = Counter(
        report.daily_leaderboard.entries[0].candidate.value
        for report in report_items
        if report.daily_leaderboard is not None and report.daily_leaderboard.entries
    )
    weekly_winners = Counter(
        report.seven_day_winner.value
        for report in report_items
        if report.seven_day_winner is not None
    )
    selected_vs_zero = Counter(
        outcome
        for report in report_items
        for outcome in [_selected_daily_vs_zero(report)]
        if outcome is not None
    )
    candidate_evidence: dict[str, object] = {}
    for candidate in BaselineCandidate:
        evaluations = [
            evaluation
            for report in report_items
            for evaluation in report.candidate_evaluations
            if evaluation.candidate.candidate is candidate
        ]
        if not evaluations:
            continue
        evaluated = [
            item for item in evaluations if item.availability is EvaluationAvailability.EVALUATED
        ]
        candidate_evidence[candidate.value] = {
            "evaluated_products": len(evaluated),
            "unavailable_products": len(evaluations) - len(evaluated),
            "completed_folds": sum(len(item.folds) for item in evaluations),
            "skipped_folds": sum(len(item.skipped_folds) for item in evaluations),
            "unavailable_reason_counts": dict(
                sorted(
                    Counter(
                        reason.value for item in evaluations for reason in item.unavailable_reasons
                    ).items()
                )
            ),
            "daily_mae": _decimal_distribution(
                item.daily_metrics.mae for item in evaluated if item.daily_metrics is not None
            ),
            "daily_rmsse": _decimal_distribution(
                item.daily_metrics.rmsse
                for item in evaluated
                if item.daily_metrics is not None and item.daily_metrics.rmsse is not None
            ),
            "seven_day_absolute_error": _decimal_distribution(
                item.seven_day_metrics.mean_absolute_total_error
                for item in evaluated
                if item.seven_day_metrics is not None
            ),
            "mean_bias_units": _decimal_distribution(
                item.seven_day_metrics.mean_bias_units
                for item in evaluated
                if item.seven_day_metrics is not None
            ),
        }

    profiles = {profile.product_key: profile for profile in preparation.profiles}
    products = []
    for report in report_items:
        profile = profiles[report.product_key]
        rank_one = (
            report.daily_leaderboard.entries[0].candidate.value
            if report.daily_leaderboard is not None and report.daily_leaderboard.entries
            else None
        )
        products.append(
            {
                "source_id": profile.source_id,
                "stratum": profile.stratum,
                "first_date": profile.first_date.isoformat(),
                "first_source_day_number": profile.first_source_day_number,
                "calendar_days": profile.calendar_days,
                "nonzero_days": profile.nonzero_days,
                "zero_target_days": profile.zero_target_days,
                "observed_days": profile.observed_days,
                "confirmed_zero_days": profile.confirmed_zero_days,
                "daily_rank_one_including_benchmark": rank_one,
                "daily_winner": report.daily_winner.value if report.daily_winner else None,
                "selected_daily_vs_zero": _selected_daily_vs_zero(report),
                "seven_day_winner": (
                    report.seven_day_winner.value if report.seven_day_winner else None
                ),
                "unavailable_reasons": [reason.value for reason in report.unavailable_reasons],
            }
        )
    return {
        "dataset": preparation.dataset_name,
        "evaluation_mode": preparation.evaluation_mode,
        "source_row_count": preparation.source_row_count,
        "source_product_count": preparation.source_product_count,
        "selected_source_product_count": len(preparation.selected_source_ids),
        "prepared_product_count": len(preparation.series),
        "products_with_daily_winner": sum(
            report.daily_winner is not None for report in report_items
        ),
        "products_with_seven_day_winner": sum(
            report.seven_day_winner is not None for report in report_items
        ),
        "daily_rank_one_counts_including_benchmark": dict(sorted(daily_rank_one.items())),
        "daily_winner_counts": dict(sorted(daily_winners.items())),
        "selected_daily_vs_zero_counts": dict(sorted(selected_vs_zero.items())),
        "seven_day_winner_counts": dict(sorted(weekly_winners.items())),
        "evidence_counts": dict(sorted(preparation.evidence_counts.items())),
        "candidate_evidence": candidate_evidence,
        "assumptions": list(preparation.assumptions),
        "limitations": list(preparation.limitations),
        "products": products,
    }


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _top_uci_product_ids(source: pd.DataFrame, product_limit: int) -> tuple[str, ...]:
    counts = (
        source.groupby("StockCode", sort=False)
        .size()
        .rename("row_count")
        .reset_index()
        .sort_values(["row_count", "StockCode"], ascending=[False, True], kind="stable")
    )
    return tuple(str(value) for value in counts.head(product_limit)["StockCode"])


def _profile_series(series: EvaluationSeries, stratum: str) -> PublicProductProfile:
    nonzero = sum(
        point.target_units is not None and point.target_units > 0 for point in series.points
    )
    zero_target = len(series.points) - nonzero
    observed = sum(point.status is ProductDateStatus.OBSERVED for point in series.points)
    confirmed_zero = sum(
        point.status is ProductDateStatus.CONFIRMED_ZERO for point in series.points
    )
    source_id = series.product_key.split(":", maxsplit=1)[-1]
    return PublicProductProfile(
        product_key=series.product_key,
        source_id=source_id,
        stratum=stratum,
        first_date=series.points[0].date,
        calendar_days=len(series.points),
        nonzero_days=nonzero,
        zero_target_days=zero_target,
        observed_days=observed,
        confirmed_zero_days=confirmed_zero,
    )


def _m5_day_columns(columns: Iterable[str]) -> tuple[str, ...]:
    day_columns = tuple(
        sorted(
            (str(column) for column in columns if str(column).startswith("d_")),
            key=lambda value: int(value[2:]),
        )
    )
    if not day_columns:
        raise ValueError("M5 source requires d_1 ... d_n daily columns")
    expected = tuple(f"d_{index}" for index in range(1, len(day_columns) + 1))
    if day_columns != expected:
        raise ValueError("M5 daily columns must be consecutive from d_1")
    return day_columns


def _m5_date_mapping(
    calendar: pd.DataFrame,
    day_columns: tuple[str, ...],
) -> Mapping[str, date]:
    if not {"d", "date"}.issubset(calendar.columns):
        raise ValueError("M5 calendar requires d and date columns")
    source = calendar.loc[:, ["d", "date"]].copy(deep=True)
    source["d"] = source["d"].astype(str)
    source["date"] = pd.to_datetime(source["date"], errors="coerce")
    if source["d"].duplicated().any() or source["date"].isna().any():
        raise ValueError("M5 calendar day ids must be unique and dates must be valid")
    mapping = {row["d"]: row["date"].date() for _, row in source.iterrows()}
    missing = [column for column in day_columns if column not in mapping]
    if missing:
        raise ValueError(f"M5 calendar is missing daily ids: {missing[:5]}")
    dates = tuple(mapping[column] for column in day_columns)
    if dates != tuple(pd.date_range(dates[0], periods=len(dates), freq="D").date):
        raise ValueError("M5 calendar dates must be consecutive")
    return MappingProxyType({column: mapping[column] for column in day_columns})


def _m5_stratum(first_day: int, nonzero_ratio: Decimal) -> str:
    if first_day > 365:
        return "delayed_start"
    if nonzero_ratio <= Decimal("0.1"):
        return "sparse"
    if nonzero_ratio <= Decimal("0.5"):
        return "intermittent"
    return "dense"


def _select_m5_metadata(
    metadata: list[_M5SeriesMetadata],
    per_stratum: int,
    sample_seed: str,
    excluded_source_ids: frozenset[str] = frozenset(),
) -> tuple[_M5SeriesMetadata, ...]:
    selected: list[_M5SeriesMetadata] = []
    for stratum in M5_STRATA:
        candidates = [
            item
            for item in metadata
            if item.stratum == stratum and item.source_id not in excluded_source_ids
        ]
        ordered = sorted(
            candidates,
            key=lambda item: hashlib.sha256(f"{sample_seed}|{item.source_id}".encode()).hexdigest(),
        )
        selected.extend(ordered[:per_stratum])
    if not selected:
        raise ValueError("M5 sampling found no nonzero product series")
    return tuple(selected)


def _decimal_distribution(values: Iterable[Decimal]) -> dict[str, object] | None:
    ordered = sorted(value for value in values if value is not None)
    if not ordered:
        return None
    middle = len(ordered) // 2
    median = (
        ordered[middle]
        if len(ordered) % 2
        else (ordered[middle - 1] + ordered[middle]) / Decimal("2")
    )
    p90_index = max(0, (9 * len(ordered) + 9) // 10 - 1)
    return {
        "count": len(ordered),
        "minimum": str(ordered[0]),
        "median": str(median),
        "p90": str(ordered[p90_index]),
        "maximum": str(ordered[-1]),
    }


def _selected_daily_vs_zero(report: ProductEvaluationReport) -> str | None:
    if (
        report.daily_leaderboard is None
        or not report.daily_leaderboard.entries
        or report.daily_winner is None
    ):
        return None
    values = {entry.candidate: entry.primary_value for entry in report.daily_leaderboard.entries}
    zero = values.get(BaselineCandidate.ZERO)
    selected = values.get(report.daily_winner)
    if zero is None or selected is None:
        return None
    if selected < zero:
        return "selected_better_than_zero"
    if selected > zero:
        return "selected_worse_than_zero"
    return "tie"
