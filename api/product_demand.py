"""HTTP-boundary conversion for the product-demand preview feature."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from api.schemas import ProductDemandRequest
from src.product_demand.baselines import BASELINE_DEFINITIONS
from src.product_demand.contracts import ProductDemandAssumptions, ProductIdentitySource
from src.product_demand.service import (
    ProductDemandAnalysisResult,
    ProductDemandAnalysisStatus,
    ProductDemandCategoryAnalysis,
    ProductDemandProductAnalysis,
)
from src.product_demand.trust_policy import ProductDemandTrustState

PRODUCT_DEMAND_TARGET_DEFINITION = (
    "Units recorded as fulfilled sales for one product. This is not customer interest, "
    "lost sales, reorder quantity, or ingredient demand."
)
PRODUCT_DEMAND_PREVIEW_WARNING = (
    "Preview — not decision-ready. Use these estimates to explore planning scenarios, "
    "not to place inventory orders."
)
PRODUCT_DEMAND_UNAVAILABLE_WARNING = (
    "Product-demand forecast unavailable. Review the explanations and correct or confirm "
    "the source data before trying again."
)
CATEGORY_DEMAND_PREVIEW_WARNING = (
    "Category-level preview — not decision-ready. This predicts the combined category total and "
    "does not allocate demand to individual products."
)
CATEGORY_DEMAND_UNAVAILABLE_WARNING = (
    "Category fallback unavailable. Review the category explanation before trying again."
)


def product_demand_assumptions_from_request(
    request: ProductDemandRequest,
) -> ProductDemandAssumptions:
    """Convert explicit API inputs into domain assumptions without guessing identity."""
    stockout_dates: dict[str, set] = defaultdict(set)
    for stockout in request.stockout_dates:
        identity_value = stockout.identity_value.strip()
        if not identity_value:
            raise ValueError("Stockout identity value must not be blank")
        prefix = "id" if stockout.identity_source is ProductIdentitySource.PRODUCT_ID else "name"
        stockout_dates[f"{prefix}:{identity_value}"].update(stockout.dates)

    return ProductDemandAssumptions(
        default_unit_of_measure=request.default_unit_of_measure,
        confirm_product_names_unique=request.confirm_product_names_unique,
        confirm_product_categories=request.confirm_product_categories,
        export_covers_all_open_days=request.export_covers_all_open_days,
        stockout_tracking_complete=request.stockout_tracking_complete,
        business_closed_dates=frozenset(request.business_closed_dates),
        stockout_dates={key: frozenset(dates) for key, dates in stockout_dates.items()},
    )


def product_demand_analysis_to_response(result: ProductDemandAnalysisResult) -> dict:
    """Expose bounded evidence and forecasts while hiding internal candidate detail."""
    has_preview = result.preview_product_count > 0 or result.preview_category_count > 0
    return {
        "status": result.status.value,
        "target": "fulfilled_units",
        "target_definition": PRODUCT_DEMAND_TARGET_DEFINITION,
        "horizon_days": result.evaluation_configuration.horizon_days,
        "supported_use_approved": False,
        "preview_product_count": result.preview_product_count,
        "unavailable_product_count": result.unavailable_product_count,
        "preview_category_count": result.preview_category_count,
        "unavailable_category_count": result.unavailable_category_count,
        "unresolved_row_count": result.readiness.unresolved_rows,
        "minimum_preview_test_weeks": result.minimum_preview_folds,
        "products": [_product_response(product) for product in result.products],
        "categories": [
            _category_response(category, result.minimum_preview_folds)
            for category in result.categories
        ],
        "dataset_reason_codes": [reason.value for reason in result.readiness.reason_codes],
        "dataset_explanations": list(result.readiness.explanations),
        "category_dataset_reason_codes": [
            reason.value for reason in result.category_dataset_reason_codes
        ],
        "category_dataset_explanations": list(result.category_dataset_explanations),
        "warning": (
            PRODUCT_DEMAND_PREVIEW_WARNING if has_preview else PRODUCT_DEMAND_UNAVAILABLE_WARNING
        ),
    }


def product_demand_data_quality_unavailable_response(message: str) -> dict:
    """Do not let product forecasting bypass the existing source-quality gate."""
    return {
        "status": ProductDemandAnalysisStatus.UNAVAILABLE.value,
        "target": "fulfilled_units",
        "target_definition": PRODUCT_DEMAND_TARGET_DEFINITION,
        "horizon_days": 7,
        "supported_use_approved": False,
        "preview_product_count": 0,
        "unavailable_product_count": 0,
        "preview_category_count": 0,
        "unavailable_category_count": 0,
        "unresolved_row_count": 0,
        "minimum_preview_test_weeks": 13,
        "products": [],
        "categories": [],
        "dataset_reason_codes": ["insufficient_data_quality"],
        "dataset_explanations": [message],
        "category_dataset_reason_codes": [],
        "category_dataset_explanations": [],
        "warning": PRODUCT_DEMAND_UNAVAILABLE_WARNING,
    }


def _product_response(product: ProductDemandProductAnalysis) -> dict:
    allowed = product.trust.numeric_forecast_allowed
    selected_candidate = product.trust.selected_candidate if allowed else None
    selected_definition = (
        BASELINE_DEFINITIONS[selected_candidate] if selected_candidate is not None else None
    )
    zero_skill = product.zero_skill
    forecast = product.forecast
    return {
        "product_key": product.readiness.product_key,
        "product_id": product.readiness.product_id,
        "product_name": product.readiness.product_name,
        "identity_source": product.readiness.identity_source.value,
        "unit_of_measure": product.readiness.unit_of_measure,
        "trust_state": product.trust.state.value,
        "numeric_forecast_allowed": allowed,
        "selected_method": selected_candidate.value if selected_candidate is not None else None,
        "selected_method_name": (
            selected_definition.display_name if selected_definition is not None else None
        ),
        "selection_reason": (
            (
                f"{selected_definition.display_name} had the lowest eligible seven-day-total "
                f"error and beat forecasting zero across {product.trust.shared_fold_count} "
                "shared historical test weeks."
            )
            if selected_definition is not None
            else None
        ),
        "evidence": {
            "shared_test_weeks": product.trust.shared_fold_count,
            "minimum_required_test_weeks": product.trust.minimum_preview_folds,
            "benchmark": "zero",
            "benchmark_passed": bool(zero_skill and zero_skill.passed),
            "selected_mean_absolute_error_units": (
                _float_or_none(zero_skill.selected_mean_absolute_total_error)
                if zero_skill is not None
                else None
            ),
            "zero_mean_absolute_error_units": (
                _float_or_none(zero_skill.zero_mean_absolute_total_error)
                if zero_skill is not None
                else None
            ),
            "skill_vs_zero_percent": (
                _rounded_percent(zero_skill.skill_vs_zero) if zero_skill is not None else None
            ),
        },
        "forecast": (
            {
                "total_units": float(forecast.predicted_total_units),
                "average_daily_planning_rate": float(product.average_daily_planning_rate),
                "forecast_dates": list(forecast.forecast_dates),
                "daily_predictions_provided": False,
            }
            if forecast is not None and product.average_daily_planning_rate is not None
            else None
        ),
        "policy_reason_codes": [reason.value for reason in product.trust.policy_reasons],
        "data_reason_codes": [reason.value for reason in product.trust.data_reason_codes],
        "explanations": list(product.trust.explanations),
        "warning": product.trust.warning,
    }


def _category_response(
    category: ProductDemandCategoryAnalysis,
    minimum_preview_folds: int,
) -> dict:
    trust = category.trust
    allowed = trust is not None and trust.numeric_forecast_allowed
    selected_candidate = trust.selected_candidate if allowed and trust is not None else None
    selected_definition = (
        BASELINE_DEFINITIONS[selected_candidate] if selected_candidate is not None else None
    )
    zero_skill = category.zero_skill
    forecast = category.forecast
    return {
        "category_key": category.category_key,
        "category_name": category.category_name,
        "product_count": len(category.product_keys),
        "unit_of_measure": category.unit_of_measure,
        "trust_state": (
            trust.state.value if trust is not None else ProductDemandTrustState.UNAVAILABLE.value
        ),
        "numeric_forecast_allowed": allowed,
        "selected_method": selected_candidate.value if selected_candidate is not None else None,
        "selected_method_name": (
            selected_definition.display_name if selected_definition is not None else None
        ),
        "selection_reason": (
            (
                f"{selected_definition.display_name} had the lowest eligible category-level "
                f"seven-day-total error and beat forecasting zero across "
                f"{trust.shared_fold_count} shared historical test weeks."
            )
            if selected_definition is not None and trust is not None
            else None
        ),
        "evidence": {
            "shared_test_weeks": trust.shared_fold_count if trust is not None else 0,
            "minimum_required_test_weeks": (
                trust.minimum_preview_folds if trust is not None else minimum_preview_folds
            ),
            "benchmark": "zero",
            "benchmark_passed": bool(zero_skill and zero_skill.passed),
            "selected_mean_absolute_error_units": (
                _float_or_none(zero_skill.selected_mean_absolute_total_error)
                if zero_skill is not None
                else None
            ),
            "zero_mean_absolute_error_units": (
                _float_or_none(zero_skill.zero_mean_absolute_total_error)
                if zero_skill is not None
                else None
            ),
            "skill_vs_zero_percent": (
                _rounded_percent(zero_skill.skill_vs_zero) if zero_skill is not None else None
            ),
        },
        "forecast": (
            {
                "total_units": float(forecast.predicted_total_units),
                "average_daily_planning_rate": float(category.average_daily_planning_rate),
                "forecast_dates": list(forecast.forecast_dates),
                "daily_predictions_provided": False,
            }
            if forecast is not None and category.average_daily_planning_rate is not None
            else None
        ),
        "policy_reason_codes": (
            [reason.value for reason in trust.policy_reasons] if trust is not None else []
        ),
        "category_reason_codes": [reason.value for reason in category.reason_codes],
        "explanations": (
            list(trust.explanations) if trust is not None else list(category.explanations)
        ),
        "warning": (
            CATEGORY_DEMAND_PREVIEW_WARNING if allowed else CATEGORY_DEMAND_UNAVAILABLE_WARNING
        ),
    }


def _float_or_none(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def _rounded_percent(value: Decimal | None) -> float | None:
    return round(float(value * Decimal("100")), 1) if value is not None else None
