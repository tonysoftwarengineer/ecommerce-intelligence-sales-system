"""Step 7 review evidence for product-demand evaluation-only reports."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from src.product_demand.evaluation_contracts import (
    BaselineCandidate,
    CandidateEvaluation,
    EvaluationAvailability,
    ForecastGranularity,
    ProductEvaluationReport,
    RollingOriginFold,
)
from src.product_demand.public_data_evaluation import PublicDatasetPreparation


@dataclass(frozen=True)
class ProductEvaluationReview:
    """Comparable skill, direction, and stability evidence for one product."""

    product_key: str
    source_id: str
    stratum: str
    daily_winner: BaselineCandidate
    weekly_winner: BaselineCandidate
    daily_leaderboard_metric: str
    shared_daily_folds: int
    shared_weekly_folds: int
    daily_mae: Decimal
    daily_rmsse: Decimal | None
    daily_mean_bias_units: Decimal
    daily_bias_fraction_of_mean_actual: Decimal | None
    daily_skill_vs_zero: Decimal | None
    daily_skill_vs_latest_value: Decimal | None
    selected_daily_fold_win_rate: Decimal
    selected_daily_fold_win_rate_including_zero: Decimal
    zero_fold_win_rate: Decimal
    daily_first_half_winner: BaselineCandidate
    daily_second_half_winner: BaselineCandidate
    daily_subperiod_stable: bool
    selected_daily_ever_varied_within_week: bool
    weekly_mean_absolute_total_error: Decimal
    weekly_mean_bias_units: Decimal
    weekly_bias_fraction_of_mean_actual: Decimal | None
    weekly_skill_vs_zero: Decimal | None
    weekly_skill_vs_last_week_total: Decimal | None
    selected_weekly_fold_win_rate: Decimal
    weekly_first_half_winner: BaselineCandidate
    weekly_second_half_winner: BaselineCandidate
    weekly_subperiod_stable: bool
    selected_daily_mean_absolute_total_error: Decimal
    daily_total_vs_weekly: str

    def __post_init__(self) -> None:
        if not self.product_key.strip() or not self.source_id.strip() or not self.stratum.strip():
            raise ValueError("Review product identity fields must not be blank")
        if self.shared_daily_folds <= 0 or self.shared_weekly_folds <= 0:
            raise ValueError("Review evidence requires shared daily and weekly folds")
        for field_name in (
            "selected_daily_fold_win_rate",
            "selected_daily_fold_win_rate_including_zero",
            "zero_fold_win_rate",
            "selected_weekly_fold_win_rate",
        ):
            value = getattr(self, field_name)
            if value < 0 or value > 1:
                raise ValueError(f"{field_name} must be between zero and one")
        if self.daily_total_vs_weekly not in {
            "daily_lower_error",
            "equal_error",
            "weekly_lower_error",
        }:
            raise ValueError("Unknown daily-total versus weekly comparison")


@dataclass(frozen=True)
class DatasetEvaluationReview:
    dataset_name: str
    products: tuple[ProductEvaluationReview, ...]

    def __post_init__(self) -> None:
        if not self.dataset_name.strip():
            raise ValueError("Review dataset name must not be blank")
        products = tuple(self.products)
        if not products:
            raise ValueError("Dataset review requires at least one evaluated product")
        keys = [product.product_key for product in products]
        if len(keys) != len(set(keys)):
            raise ValueError("Dataset review product keys must be unique")
        object.__setattr__(self, "products", products)


def review_public_evaluations(
    preparation: PublicDatasetPreparation,
    reports: Iterable[ProductEvaluationReport],
) -> DatasetEvaluationReview:
    """Review already-evaluated public products without changing model results."""
    report_items = tuple(reports)
    expected = {series.product_key for series in preparation.series}
    if {report.product_key for report in report_items} != expected:
        raise ValueError("Review reports must match the prepared public series")
    profiles = {profile.product_key: profile for profile in preparation.profiles}
    products = tuple(
        _review_product(
            report, profiles[report.product_key].source_id, profiles[report.product_key].stratum
        )
        for report in sorted(report_items, key=lambda item: item.product_key)
    )
    return DatasetEvaluationReview(dataset_name=preparation.dataset_name, products=products)


def review_evidence_to_dict(review: DatasetEvaluationReview) -> dict[str, object]:
    """Serialize aggregate review evidence without accepting policy thresholds."""
    products = review.products
    rmsse_states = Counter(
        "undefined"
        if product.daily_rmsse is None
        else "below_one"
        if product.daily_rmsse < 1
        else "equal_one"
        if product.daily_rmsse == 1
        else "above_one"
        for product in products
    )
    total_comparisons = Counter(product.daily_total_vs_weekly for product in products)
    first_half = Counter(product.daily_first_half_winner.value for product in products)
    second_half = Counter(product.daily_second_half_winner.value for product in products)
    strata: dict[str, dict[str, object]] = {}
    for stratum in sorted({product.stratum for product in products}):
        members = tuple(product for product in products if product.stratum == stratum)
        strata[stratum] = {
            "product_count": len(members),
            "daily_rmsse": _distribution(
                product.daily_rmsse for product in members if product.daily_rmsse is not None
            ),
            "daily_skill_vs_zero": _distribution(
                product.daily_skill_vs_zero
                for product in members
                if product.daily_skill_vs_zero is not None
            ),
            "absolute_daily_bias_fraction": _distribution(
                abs(product.daily_bias_fraction_of_mean_actual)
                for product in members
                if product.daily_bias_fraction_of_mean_actual is not None
            ),
            "selected_daily_fold_win_rate": _distribution(
                product.selected_daily_fold_win_rate for product in members
            ),
            "zero_fold_win_rate": _distribution(product.zero_fold_win_rate for product in members),
            "weekly_skill_vs_zero": _distribution(
                product.weekly_skill_vs_zero
                for product in members
                if product.weekly_skill_vs_zero is not None
            ),
            "absolute_weekly_bias_fraction": _distribution(
                abs(product.weekly_bias_fraction_of_mean_actual)
                for product in members
                if product.weekly_bias_fraction_of_mean_actual is not None
            ),
            "subperiod_stable_products": sum(product.daily_subperiod_stable for product in members),
            "weekly_subperiod_stable_products": sum(
                product.weekly_subperiod_stable for product in members
            ),
            "date_varying_daily_winner_products": sum(
                product.selected_daily_ever_varied_within_week for product in members
            ),
        }
    return {
        "dataset": review.dataset_name,
        "scope": (
            "Review evidence only. No trust threshold, model, or user-facing granularity "
            "is accepted by this report."
        ),
        "product_count": len(products),
        "daily_rmsse_state_counts": dict(sorted(rmsse_states.items())),
        "daily_skill_vs_zero": _distribution(
            product.daily_skill_vs_zero
            for product in products
            if product.daily_skill_vs_zero is not None
        ),
        "daily_skill_vs_latest_value": _distribution(
            product.daily_skill_vs_latest_value
            for product in products
            if product.daily_skill_vs_latest_value is not None
        ),
        "absolute_daily_bias_fraction": _distribution(
            abs(product.daily_bias_fraction_of_mean_actual)
            for product in products
            if product.daily_bias_fraction_of_mean_actual is not None
        ),
        "selected_daily_fold_win_rate": _distribution(
            product.selected_daily_fold_win_rate for product in products
        ),
        "selected_daily_fold_win_rate_including_zero": _distribution(
            product.selected_daily_fold_win_rate_including_zero for product in products
        ),
        "zero_fold_win_rate": _distribution(product.zero_fold_win_rate for product in products),
        "weekly_skill_vs_zero": _distribution(
            product.weekly_skill_vs_zero
            for product in products
            if product.weekly_skill_vs_zero is not None
        ),
        "weekly_skill_vs_last_week_total": _distribution(
            product.weekly_skill_vs_last_week_total
            for product in products
            if product.weekly_skill_vs_last_week_total is not None
        ),
        "absolute_weekly_bias_fraction": _distribution(
            abs(product.weekly_bias_fraction_of_mean_actual)
            for product in products
            if product.weekly_bias_fraction_of_mean_actual is not None
        ),
        "daily_subperiod_stable_products": sum(
            product.daily_subperiod_stable for product in products
        ),
        "weekly_subperiod_stable_products": sum(
            product.weekly_subperiod_stable for product in products
        ),
        "date_varying_daily_winner_products": sum(
            product.selected_daily_ever_varied_within_week for product in products
        ),
        "daily_first_half_winner_counts": dict(sorted(first_half.items())),
        "daily_second_half_winner_counts": dict(sorted(second_half.items())),
        "daily_total_vs_weekly_counts": dict(sorted(total_comparisons.items())),
        "strata": strata,
        "products": [_product_to_dict(product) for product in products],
    }


def _review_product(
    report: ProductEvaluationReport,
    source_id: str,
    stratum: str,
) -> ProductEvaluationReview:
    if (
        report.daily_winner is None
        or report.seven_day_winner is None
        or report.daily_leaderboard is None
        or report.seven_day_leaderboard is None
    ):
        raise ValueError(f"Product {report.product_key!r} lacks reviewable leaderboards")
    daily = _candidate(report, report.daily_winner)
    weekly = _candidate(report, report.seven_day_winner)
    if daily.daily_metrics is None or daily.seven_day_metrics is None:
        raise ValueError("Selected daily candidate lacks required metrics")
    if weekly.seven_day_metrics is None:
        raise ValueError("Selected weekly candidate lacks required metrics")

    daily_candidates = tuple(
        evaluation
        for evaluation in report.candidate_evaluations
        if evaluation.availability is EvaluationAvailability.EVALUATED
        and evaluation.candidate.granularity is ForecastGranularity.DAILY
    )
    weekly_candidates = tuple(
        evaluation
        for evaluation in report.candidate_evaluations
        if evaluation.availability is EvaluationAvailability.EVALUATED
        and evaluation.candidate.granularity is ForecastGranularity.SEVEN_DAY_TOTAL
    )
    daily_common = _common_fold_keys(daily_candidates)
    weekly_common = _common_fold_keys(weekly_candidates)
    nonbenchmark_daily = tuple(
        evaluation for evaluation in daily_candidates if not evaluation.candidate.benchmark_only
    )
    selected_fold_win_rate = _fold_win_rate(
        daily,
        nonbenchmark_daily,
        daily_common,
        daily=True,
    )
    selected_including_zero = _fold_win_rate(
        daily,
        daily_candidates,
        daily_common,
        daily=True,
    )
    zero = _candidate(report, BaselineCandidate.ZERO)
    zero_fold_win_rate = _fold_win_rate(
        zero,
        daily_candidates,
        daily_common,
        daily=True,
    )
    first_keys, second_keys = _split_fold_keys(daily_common)
    first_winner = _subperiod_winner(nonbenchmark_daily, first_keys, daily=True)
    second_winner = _subperiod_winner(nonbenchmark_daily, second_keys, daily=True)
    weekly_first_keys, weekly_second_keys = _split_fold_keys(weekly_common)
    weekly_first_winner = _subperiod_winner(
        weekly_candidates,
        weekly_first_keys,
        daily=False,
    )
    weekly_second_winner = _subperiod_winner(
        weekly_candidates,
        weekly_second_keys,
        daily=False,
    )
    selected_daily_total_error, weekly_total_error = _fair_total_errors(
        daily,
        weekly,
    )
    return ProductEvaluationReview(
        product_key=report.product_key,
        source_id=source_id,
        stratum=stratum,
        daily_winner=report.daily_winner,
        weekly_winner=report.seven_day_winner,
        daily_leaderboard_metric=report.daily_leaderboard.metric.value,
        shared_daily_folds=len(daily_common),
        shared_weekly_folds=len(weekly_common),
        daily_mae=daily.daily_metrics.mae,
        daily_rmsse=daily.daily_metrics.rmsse,
        daily_mean_bias_units=daily.daily_metrics.mean_bias_units,
        daily_bias_fraction_of_mean_actual=_bias_fraction(daily),
        daily_skill_vs_zero=_leaderboard_skill(report, report.daily_winner, BaselineCandidate.ZERO),
        daily_skill_vs_latest_value=_leaderboard_skill(
            report,
            report.daily_winner,
            BaselineCandidate.LATEST_VALUE,
        ),
        selected_daily_fold_win_rate=selected_fold_win_rate,
        selected_daily_fold_win_rate_including_zero=selected_including_zero,
        zero_fold_win_rate=zero_fold_win_rate,
        daily_first_half_winner=first_winner,
        daily_second_half_winner=second_winner,
        daily_subperiod_stable=first_winner is second_winner,
        selected_daily_ever_varied_within_week=any(
            fold.predicted_daily_units is not None and len(set(fold.predicted_daily_units)) > 1
            for fold in daily.folds
        ),
        weekly_mean_absolute_total_error=weekly.seven_day_metrics.mean_absolute_total_error,
        weekly_mean_bias_units=weekly.seven_day_metrics.mean_bias_units,
        weekly_bias_fraction_of_mean_actual=_weekly_bias_fraction(weekly),
        weekly_skill_vs_zero=_total_skill(weekly, zero),
        weekly_skill_vs_last_week_total=_total_skill(
            weekly,
            _candidate(report, BaselineCandidate.LAST_WEEK_TOTAL),
        ),
        selected_weekly_fold_win_rate=_fold_win_rate(
            weekly,
            weekly_candidates,
            weekly_common,
            daily=False,
        ),
        weekly_first_half_winner=weekly_first_winner,
        weekly_second_half_winner=weekly_second_winner,
        weekly_subperiod_stable=weekly_first_winner is weekly_second_winner,
        selected_daily_mean_absolute_total_error=selected_daily_total_error,
        daily_total_vs_weekly=(
            "daily_lower_error"
            if selected_daily_total_error < weekly_total_error
            else "weekly_lower_error"
            if selected_daily_total_error > weekly_total_error
            else "equal_error"
        ),
    )


def _candidate(
    report: ProductEvaluationReport,
    candidate: BaselineCandidate,
) -> CandidateEvaluation:
    matches = [
        evaluation
        for evaluation in report.candidate_evaluations
        if evaluation.candidate.candidate is candidate
    ]
    if len(matches) != 1 or matches[0].availability is not EvaluationAvailability.EVALUATED:
        raise ValueError(f"Candidate {candidate.value!r} is not evaluated for {report.product_key}")
    return matches[0]


def _common_fold_keys(
    candidates: tuple[CandidateEvaluation, ...],
) -> tuple[tuple[object, ...], ...]:
    if not candidates:
        raise ValueError("Fold comparison requires evaluated candidates")
    shared = set(_fold_map(candidates[0]))
    for candidate in candidates[1:]:
        shared &= set(_fold_map(candidate))
    if not shared:
        raise ValueError("Fold comparison requires shared historical weeks")
    return tuple(sorted(shared))


def _fold_map(evaluation: CandidateEvaluation) -> dict[tuple[object, ...], RollingOriginFold]:
    return {tuple(fold.forecast_dates): fold for fold in evaluation.folds}


def _fold_win_rate(
    selected: CandidateEvaluation,
    candidates: tuple[CandidateEvaluation, ...],
    keys: tuple[tuple[object, ...], ...],
    *,
    daily: bool,
) -> Decimal:
    selected_folds = _fold_map(selected)
    candidate_maps = tuple(_fold_map(candidate) for candidate in candidates)
    wins = 0
    for key in keys:
        selected_error = _fold_error(selected_folds[key], daily=daily)
        best_error = min(_fold_error(folds[key], daily=daily) for folds in candidate_maps)
        if selected_error == best_error:
            wins += 1
    return Decimal(wins) / Decimal(len(keys))


def _subperiod_winner(
    candidates: tuple[CandidateEvaluation, ...],
    keys: tuple[tuple[object, ...], ...],
    *,
    daily: bool,
) -> BaselineCandidate:
    if not keys:
        raise ValueError("Subperiod comparison requires at least one fold")
    ranked = []
    for candidate in candidates:
        folds = _fold_map(candidate)
        mean_error = sum(
            (_fold_error(folds[key], daily=daily) for key in keys),
            Decimal("0"),
        ) / Decimal(len(keys))
        ranked.append(
            (
                mean_error,
                candidate.candidate.complexity_rank,
                candidate.candidate.candidate.value,
                candidate.candidate.candidate,
            )
        )
    return min(ranked)[-1]


def _split_fold_keys(
    keys: tuple[tuple[object, ...], ...],
) -> tuple[tuple[tuple[object, ...], ...], tuple[tuple[object, ...], ...]]:
    if len(keys) < 2:
        raise ValueError("Subperiod stability requires at least two shared folds")
    middle = len(keys) // 2
    return keys[:middle], keys[middle:]


def _fold_error(fold: RollingOriginFold, *, daily: bool) -> Decimal:
    if daily:
        if fold.predicted_daily_units is None:
            raise ValueError("Daily fold comparison requires daily predictions")
        return sum(
            (
                abs(predicted - actual)
                for predicted, actual in zip(
                    fold.predicted_daily_units,
                    fold.actual_daily_units,
                )
            ),
            Decimal("0"),
        ) / Decimal(len(fold.actual_daily_units))
    return abs(fold.predicted_total_units - sum(fold.actual_daily_units, Decimal("0")))


def _leaderboard_skill(
    report: ProductEvaluationReport,
    selected: BaselineCandidate,
    benchmark: BaselineCandidate,
) -> Decimal | None:
    if report.daily_leaderboard is None:
        return None
    values = {entry.candidate: entry.primary_value for entry in report.daily_leaderboard.entries}
    selected_value = values.get(selected)
    benchmark_value = values.get(benchmark)
    if selected_value is None or benchmark_value is None or benchmark_value == 0:
        return None
    return (benchmark_value - selected_value) / benchmark_value


def _bias_fraction(evaluation: CandidateEvaluation) -> Decimal | None:
    if evaluation.daily_metrics is None:
        return None
    actuals = tuple(actual for fold in evaluation.folds for actual in fold.actual_daily_units)
    mean_actual = sum(actuals, Decimal("0")) / Decimal(len(actuals))
    if mean_actual == 0:
        return None
    return evaluation.daily_metrics.mean_bias_units / mean_actual


def _fair_total_errors(
    daily: CandidateEvaluation,
    weekly: CandidateEvaluation,
) -> tuple[Decimal, Decimal]:
    daily_folds = _fold_map(daily)
    weekly_folds = _fold_map(weekly)
    keys = tuple(sorted(set(daily_folds) & set(weekly_folds)))
    if not keys:
        raise ValueError("Daily and weekly candidates require shared folds")
    daily_error = sum(
        (_fold_error(daily_folds[key], daily=False) for key in keys),
        Decimal("0"),
    ) / Decimal(len(keys))
    weekly_error = sum(
        (_fold_error(weekly_folds[key], daily=False) for key in keys),
        Decimal("0"),
    ) / Decimal(len(keys))
    return daily_error, weekly_error


def _total_skill(
    selected: CandidateEvaluation,
    benchmark: CandidateEvaluation,
) -> Decimal | None:
    selected_error, benchmark_error = _fair_total_errors(selected, benchmark)
    if benchmark_error == 0:
        return None
    return (benchmark_error - selected_error) / benchmark_error


def _weekly_bias_fraction(evaluation: CandidateEvaluation) -> Decimal | None:
    if evaluation.seven_day_metrics is None:
        return None
    actual_totals = tuple(sum(fold.actual_daily_units, Decimal("0")) for fold in evaluation.folds)
    mean_actual = sum(actual_totals, Decimal("0")) / Decimal(len(actual_totals))
    if mean_actual == 0:
        return None
    return evaluation.seven_day_metrics.mean_bias_units / mean_actual


def _distribution(values: Iterable[Decimal]) -> dict[str, object] | None:
    ordered = sorted(values)
    if not ordered:
        return None
    middle = len(ordered) // 2
    median = (
        ordered[middle]
        if len(ordered) % 2
        else (ordered[middle - 1] + ordered[middle]) / Decimal("2")
    )
    p10_index = max(0, (len(ordered) + 9) // 10 - 1)
    p90_index = max(0, (9 * len(ordered) + 9) // 10 - 1)
    return {
        "count": len(ordered),
        "minimum": str(ordered[0]),
        "p10": str(ordered[p10_index]),
        "median": str(median),
        "p90": str(ordered[p90_index]),
        "maximum": str(ordered[-1]),
    }


def _product_to_dict(product: ProductEvaluationReview) -> dict[str, object]:
    return {
        "source_id": product.source_id,
        "stratum": product.stratum,
        "daily_winner": product.daily_winner.value,
        "weekly_winner": product.weekly_winner.value,
        "daily_leaderboard_metric": product.daily_leaderboard_metric,
        "shared_daily_folds": product.shared_daily_folds,
        "shared_weekly_folds": product.shared_weekly_folds,
        "daily_mae": str(product.daily_mae),
        "daily_rmsse": str(product.daily_rmsse) if product.daily_rmsse is not None else None,
        "daily_mean_bias_units": str(product.daily_mean_bias_units),
        "daily_bias_fraction_of_mean_actual": (
            str(product.daily_bias_fraction_of_mean_actual)
            if product.daily_bias_fraction_of_mean_actual is not None
            else None
        ),
        "daily_skill_vs_zero": (
            str(product.daily_skill_vs_zero) if product.daily_skill_vs_zero is not None else None
        ),
        "daily_skill_vs_latest_value": (
            str(product.daily_skill_vs_latest_value)
            if product.daily_skill_vs_latest_value is not None
            else None
        ),
        "selected_daily_fold_win_rate": str(product.selected_daily_fold_win_rate),
        "selected_daily_fold_win_rate_including_zero": str(
            product.selected_daily_fold_win_rate_including_zero
        ),
        "zero_fold_win_rate": str(product.zero_fold_win_rate),
        "daily_first_half_winner": product.daily_first_half_winner.value,
        "daily_second_half_winner": product.daily_second_half_winner.value,
        "daily_subperiod_stable": product.daily_subperiod_stable,
        "selected_daily_ever_varied_within_week": (product.selected_daily_ever_varied_within_week),
        "weekly_mean_absolute_total_error": str(product.weekly_mean_absolute_total_error),
        "weekly_mean_bias_units": str(product.weekly_mean_bias_units),
        "weekly_bias_fraction_of_mean_actual": (
            str(product.weekly_bias_fraction_of_mean_actual)
            if product.weekly_bias_fraction_of_mean_actual is not None
            else None
        ),
        "weekly_skill_vs_zero": (
            str(product.weekly_skill_vs_zero) if product.weekly_skill_vs_zero is not None else None
        ),
        "weekly_skill_vs_last_week_total": (
            str(product.weekly_skill_vs_last_week_total)
            if product.weekly_skill_vs_last_week_total is not None
            else None
        ),
        "selected_weekly_fold_win_rate": str(product.selected_weekly_fold_win_rate),
        "weekly_first_half_winner": product.weekly_first_half_winner.value,
        "weekly_second_half_winner": product.weekly_second_half_winner.value,
        "weekly_subperiod_stable": product.weekly_subperiod_stable,
        "selected_daily_mean_absolute_total_error": str(
            product.selected_daily_mean_absolute_total_error
        ),
        "daily_total_vs_weekly": product.daily_total_vs_weekly,
    }
