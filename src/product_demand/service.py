"""End-to-end product-demand domain orchestration without API concerns."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

import pandas as pd

from src.generic_sales.contracts import RevenueMode
from src.product_demand.baselines import BaselineUnavailableError, forecast_baseline
from src.product_demand.calendar import build_product_demand_calendar
from src.product_demand.category_fallback import (
    CategoryFallbackAvailability,
    CategoryFallbackCandidate,
    CategoryFallbackPreparation,
    CategoryFallbackReasonCode,
    prepare_category_fallback_candidates,
)
from src.product_demand.contracts import (
    ProductDemandAssumptions,
    ProductDemandAvailability,
    ProductDemandProductReadiness,
    ProductDemandReadinessReport,
    ProductIdentitySource,
)
from src.product_demand.evaluation_contracts import (
    BaselineForecast,
    EvaluationConfiguration,
    EvaluationSeries,
    ForecastGranularity,
    ProductEvaluationReport,
)
from src.product_demand.evaluation_series import prepare_evaluation_series
from src.product_demand.metrics import evaluate_product_baselines
from src.product_demand.trust_gate import WeeklyZeroSkillEvidence, assess_weekly_zero_skill
from src.product_demand.trust_policy import (
    MINIMUM_PREVIEW_FOLDS,
    ProductDemandTrustDecision,
    assess_product_demand_trust,
    block_final_product_demand_forecast,
)


class ProductDemandAnalysisStatus(str, Enum):
    UNAVAILABLE = "unavailable"
    PARTIAL_PREVIEW = "partial_preview"
    PREVIEW_AVAILABLE = "preview_available"


@dataclass(frozen=True)
class ProductDemandProductAnalysis:
    """One isolated product result with evidence retained behind its decision."""

    readiness: ProductDemandProductReadiness
    trust: ProductDemandTrustDecision
    evaluation: ProductEvaluationReport | None = None
    zero_skill: WeeklyZeroSkillEvidence | None = None
    forecast: BaselineForecast | None = None

    def __post_init__(self) -> None:
        keys = {self.readiness.product_key, self.trust.product_key}
        if self.evaluation is not None:
            keys.add(self.evaluation.product_key)
        if self.zero_skill is not None:
            keys.add(self.zero_skill.product_key)
        if len(keys) != 1:
            raise ValueError("Product-demand analysis evidence must belong to one product")

        if self.trust.numeric_forecast_allowed:
            if self.forecast is None:
                raise ValueError("Allowed product-demand previews require a final forecast")
            if self.forecast.candidate is not self.trust.selected_candidate:
                raise ValueError("Final forecast must use the policy-selected candidate")
            if self.forecast.granularity is not ForecastGranularity.SEVEN_DAY_TOTAL:
                raise ValueError("Product-demand previews must contain one seven-day total")
            if self.forecast.predicted_daily_units is not None:
                raise ValueError("Product-demand previews cannot contain date-specific predictions")
        elif self.forecast is not None:
            raise ValueError("Unavailable products cannot retain a numeric forecast")

    @property
    def average_daily_planning_rate(self) -> Decimal | None:
        """A labelled average, never seven date-specific predictions."""
        return (
            self.forecast.predicted_total_units / Decimal("7")
            if self.forecast is not None
            else None
        )


@dataclass(frozen=True)
class ProductDemandCategoryAnalysis:
    """One fallback-only category outcome; it never allocates totals to products."""

    category_key: str
    category_name: str
    product_keys: tuple[str, ...]
    unit_of_measure: str | None
    reason_codes: tuple[CategoryFallbackReasonCode, ...]
    explanations: tuple[str, ...]
    trust: ProductDemandTrustDecision | None = None
    evaluation: ProductEvaluationReport | None = None
    zero_skill: WeeklyZeroSkillEvidence | None = None
    forecast: BaselineForecast | None = None

    def __post_init__(self) -> None:
        if not self.category_key.strip() or not self.category_name.strip():
            raise ValueError("Category-demand analysis requires identity")
        if tuple(sorted(set(self.product_keys))) != self.product_keys:
            raise ValueError("Category-demand product keys must be unique and sorted")
        if self.trust is None:
            if self.forecast is not None or not self.reason_codes:
                raise ValueError("Unevaluated categories require reasons and no forecast")
            return
        if self.trust.product_key != self.category_key:
            raise ValueError("Category trust evidence must match the category")
        if self.trust.numeric_forecast_allowed:
            if self.forecast is None or self.reason_codes:
                raise ValueError("Allowed category previews require one forecast and no blockers")
        elif self.forecast is not None:
            raise ValueError("Unavailable category outcomes cannot retain a forecast")

    @property
    def average_daily_planning_rate(self) -> Decimal | None:
        return (
            self.forecast.predicted_total_units / Decimal("7")
            if self.forecast is not None
            else None
        )


@dataclass(frozen=True)
class ProductDemandAnalysisResult:
    status: ProductDemandAnalysisStatus
    readiness: ProductDemandReadinessReport
    products: tuple[ProductDemandProductAnalysis, ...]
    categories: tuple[ProductDemandCategoryAnalysis, ...]
    category_dataset_reason_codes: tuple[CategoryFallbackReasonCode, ...]
    category_dataset_explanations: tuple[str, ...]
    evaluation_configuration: EvaluationConfiguration
    minimum_preview_folds: int

    def __post_init__(self) -> None:
        products = tuple(self.products)
        keys = [item.readiness.product_key for item in products]
        if keys != sorted(keys) or len(keys) != len(set(keys)):
            raise ValueError("Product-demand results must be unique and sorted by product key")
        expected_keys = sorted(item.product_key for item in self.readiness.products)
        if keys != expected_keys:
            raise ValueError("Every identified readiness product requires one analysis result")
        category_keys = [item.category_key for item in self.categories]
        if category_keys != sorted(category_keys) or len(category_keys) != len(set(category_keys)):
            raise ValueError("Category-demand results must be unique and sorted by category key")
        preview_product_keys = {
            item.readiness.product_key for item in products if item.trust.numeric_forecast_allowed
        }
        if any(
            category.forecast is not None
            and preview_product_keys.intersection(category.product_keys)
            for category in self.categories
        ):
            raise ValueError("Category fallback cannot overlap an eligible product forecast")
        if self.minimum_preview_folds <= 0:
            raise ValueError("minimum_preview_folds must be positive")
        product_preview_count = sum(item.trust.numeric_forecast_allowed for item in products)
        category_preview_count = sum(item.forecast is not None for item in self.categories)
        preview_count = product_preview_count + category_preview_count
        expected_status = (
            ProductDemandAnalysisStatus.UNAVAILABLE
            if preview_count == 0
            else ProductDemandAnalysisStatus.PREVIEW_AVAILABLE
            if product_preview_count == len(products)
            and category_preview_count == 0
            and self.readiness.unresolved_rows == 0
            else ProductDemandAnalysisStatus.PARTIAL_PREVIEW
        )
        if self.status is not expected_status:
            raise ValueError("Product-demand analysis status must reflect product outcomes")
        object.__setattr__(self, "products", products)

    @property
    def preview_product_count(self) -> int:
        return sum(item.trust.numeric_forecast_allowed for item in self.products)

    @property
    def unavailable_product_count(self) -> int:
        return len(self.products) - self.preview_product_count

    @property
    def preview_category_count(self) -> int:
        return sum(item.forecast is not None for item in self.categories)

    @property
    def unavailable_category_count(self) -> int:
        return len(self.categories) - self.preview_category_count


def analyze_product_demand(
    canonical_data: pd.DataFrame,
    revenue_mode: RevenueMode,
    assumptions: ProductDemandAssumptions,
    evaluation_configuration: EvaluationConfiguration | None = None,
    minimum_preview_folds: int = MINIMUM_PREVIEW_FOLDS,
) -> ProductDemandAnalysisResult:
    """Run the accepted product-demand flow and isolate decisions per product."""
    configuration = evaluation_configuration or EvaluationConfiguration()
    calendar_result = build_product_demand_calendar(canonical_data, revenue_mode, assumptions)
    series_by_product = {
        series.product_key: series for series in prepare_evaluation_series(calendar_result.calendar)
    }

    products = tuple(
        _analyze_product(
            readiness,
            series_by_product.get(readiness.product_key),
            configuration,
            minimum_preview_folds,
        )
        for readiness in sorted(
            calendar_result.readiness.products,
            key=lambda item: item.product_key,
        )
    )
    eligible_product_keys = frozenset(
        item.readiness.product_key for item in products if item.trust.numeric_forecast_allowed
    )
    category_preparation = (
        CategoryFallbackPreparation(candidates=(), dataset_reason_codes=(), dataset_explanations=())
        if products and len(eligible_product_keys) == len(products)
        else prepare_category_fallback_candidates(
            canonical_data,
            calendar_result.calendar,
            calendar_result.readiness,
            eligible_product_keys,
            assumptions,
        )
    )
    categories = tuple(
        _analyze_category(candidate, configuration, minimum_preview_folds)
        for candidate in category_preparation.candidates
    )
    product_preview_count = len(eligible_product_keys)
    category_preview_count = sum(item.forecast is not None for item in categories)
    preview_count = product_preview_count + category_preview_count
    status = (
        ProductDemandAnalysisStatus.UNAVAILABLE
        if preview_count == 0
        else ProductDemandAnalysisStatus.PREVIEW_AVAILABLE
        if product_preview_count == len(products)
        and category_preview_count == 0
        and calendar_result.readiness.unresolved_rows == 0
        else ProductDemandAnalysisStatus.PARTIAL_PREVIEW
    )
    return ProductDemandAnalysisResult(
        status=status,
        readiness=calendar_result.readiness,
        products=products,
        categories=categories,
        category_dataset_reason_codes=category_preparation.dataset_reason_codes,
        category_dataset_explanations=category_preparation.dataset_explanations,
        evaluation_configuration=configuration,
        minimum_preview_folds=minimum_preview_folds,
    )


def _analyze_product(
    readiness: ProductDemandProductReadiness,
    series: EvaluationSeries | None,
    configuration: EvaluationConfiguration,
    minimum_preview_folds: int,
) -> ProductDemandProductAnalysis:
    if series is None:
        trust = assess_product_demand_trust(
            readiness,
            report=None,
            zero_skill=None,
            minimum_preview_folds=minimum_preview_folds,
        )
        return ProductDemandProductAnalysis(readiness=readiness, trust=trust)

    evaluation = evaluate_product_baselines(series, configuration)
    zero_skill = assess_weekly_zero_skill(evaluation)
    trust = assess_product_demand_trust(
        readiness,
        evaluation,
        zero_skill,
        minimum_preview_folds,
    )
    if not trust.numeric_forecast_allowed:
        return ProductDemandProductAnalysis(
            readiness=readiness,
            trust=trust,
            evaluation=evaluation,
            zero_skill=zero_skill,
        )

    if trust.selected_candidate is None:
        raise AssertionError("Allowed preview is missing the selected candidate")
    try:
        forecast = forecast_baseline(series, trust.selected_candidate)
    except BaselineUnavailableError as error:
        trust = block_final_product_demand_forecast(
            trust,
            f"The selected method could not use the latest product history: {error}",
        )
        return ProductDemandProductAnalysis(
            readiness=readiness,
            trust=trust,
            evaluation=evaluation,
            zero_skill=zero_skill,
        )

    return ProductDemandProductAnalysis(
        readiness=readiness,
        trust=trust,
        evaluation=evaluation,
        zero_skill=zero_skill,
        forecast=forecast,
    )


def _analyze_category(
    candidate: CategoryFallbackCandidate,
    configuration: EvaluationConfiguration,
    minimum_preview_folds: int,
) -> ProductDemandCategoryAnalysis:
    if candidate.availability is CategoryFallbackAvailability.UNAVAILABLE:
        return ProductDemandCategoryAnalysis(
            category_key=candidate.category_key,
            category_name=candidate.category_name,
            product_keys=candidate.product_keys,
            unit_of_measure=candidate.unit_of_measure,
            reason_codes=candidate.reason_codes,
            explanations=candidate.explanations,
        )
    if candidate.series is None or candidate.unit_of_measure is None:
        raise AssertionError("Ready category candidate is missing its evaluation series")

    readiness = ProductDemandProductReadiness(
        product_key=candidate.category_key,
        product_id=None,
        product_name=candidate.category_name,
        identity_source=ProductIdentitySource.PRODUCT_NAME,
        unit_of_measure=candidate.unit_of_measure,
        status=ProductDemandAvailability.READY,
        reason_codes=(),
        explanations=(),
    )
    evaluation = evaluate_product_baselines(candidate.series, configuration)
    zero_skill = assess_weekly_zero_skill(evaluation)
    trust = assess_product_demand_trust(
        readiness,
        evaluation,
        zero_skill,
        minimum_preview_folds,
        scope_label="category",
    )
    forecast = None
    if trust.numeric_forecast_allowed:
        if trust.selected_candidate is None:
            raise AssertionError("Allowed category preview is missing the selected candidate")
        try:
            forecast = forecast_baseline(candidate.series, trust.selected_candidate)
        except BaselineUnavailableError as error:
            trust = block_final_product_demand_forecast(
                trust,
                f"The selected method could not use the latest category history: {error}",
            )
    return ProductDemandCategoryAnalysis(
        category_key=candidate.category_key,
        category_name=candidate.category_name,
        product_keys=candidate.product_keys,
        unit_of_measure=candidate.unit_of_measure,
        reason_codes=(),
        explanations=(),
        trust=trust,
        evaluation=evaluation,
        zero_skill=zero_skill,
        forecast=forecast,
    )
