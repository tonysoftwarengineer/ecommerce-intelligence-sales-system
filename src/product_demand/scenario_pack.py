"""Deterministic synthetic scenarios for product-demand evaluation behavior."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from enum import Enum

from src.product_demand.baselines import BASELINE_DEFINITIONS
from src.product_demand.contracts import ProductDateStatus
from src.product_demand.evaluation_contracts import (
    BaselineCandidate,
    EvaluationAvailability,
    EvaluationConfiguration,
    EvaluationSeries,
    EvaluationSeriesPoint,
    EvaluationUnavailableReason,
    ProductEvaluationReport,
)
from src.product_demand.metrics import evaluate_product_baselines


class ScenarioProductStatus(str, Enum):
    EVALUATED = "evaluated"
    UNAVAILABLE = "unavailable"
    INVALID = "invalid"


@dataclass(frozen=True)
class ScenarioStatusOverride:
    index: int
    status: ProductDateStatus

    def __post_init__(self) -> None:
        if isinstance(self.index, bool) or not isinstance(self.index, int) or self.index < 0:
            raise ValueError("Scenario status override index must not be negative")


@dataclass(frozen=True)
class ScenarioProductSpec:
    product_key: str
    values: tuple[Decimal, ...]
    unit_of_measure: str = "piece"
    status_overrides: tuple[ScenarioStatusOverride, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.product_key.strip():
            raise ValueError("Scenario product key must not be blank")
        if not self.values:
            raise ValueError("Scenario product requires at least one value")
        overrides = tuple(self.status_overrides)
        indexes = [override.index for override in overrides]
        if len(indexes) != len(set(indexes)):
            raise ValueError("Scenario status override indexes must be unique")
        if any(index >= len(self.values) for index in indexes):
            raise ValueError("Scenario status override index is outside the product history")
        object.__setattr__(self, "status_overrides", overrides)


@dataclass(frozen=True)
class ScenarioProductExpectation:
    product_key: str
    status: ScenarioProductStatus
    evaluated_candidates: frozenset[BaselineCandidate]
    required_reasons: frozenset[EvaluationUnavailableReason] = field(default_factory=frozenset)
    check_daily_winner: bool = False
    daily_winner: BaselineCandidate | None = None
    check_seven_day_winner: bool = False
    seven_day_winner: BaselineCandidate | None = None


@dataclass(frozen=True)
class ProductDemandScenario:
    name: str
    description: str
    products: tuple[ScenarioProductSpec, ...]
    expectations: tuple[ScenarioProductExpectation, ...]
    configuration: EvaluationConfiguration = field(default_factory=EvaluationConfiguration)

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.description.strip():
            raise ValueError("Scenario name and description must not be blank")
        products = tuple(self.products)
        expectations = tuple(self.expectations)
        product_keys = [product.product_key for product in products]
        expectation_keys = [expectation.product_key for expectation in expectations]
        if len(product_keys) != len(set(product_keys)):
            raise ValueError("Scenario product keys must be unique")
        if len(expectation_keys) != len(set(expectation_keys)):
            raise ValueError("Scenario expectation product keys must be unique")
        if set(product_keys) != set(expectation_keys):
            raise ValueError("Every scenario product requires exactly one expectation")
        object.__setattr__(self, "products", products)
        object.__setattr__(self, "expectations", expectations)


@dataclass(frozen=True)
class ScenarioProductResult:
    product_key: str
    status: ScenarioProductStatus
    evaluated_candidates: frozenset[BaselineCandidate]
    evidence_reasons: frozenset[EvaluationUnavailableReason]
    report: ProductEvaluationReport | None = None
    error_reason: EvaluationUnavailableReason | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class ProductDemandScenarioResult:
    scenario_name: str
    products: tuple[ScenarioProductResult, ...]


@dataclass(frozen=True)
class ScenarioExpectationCheck:
    scenario_name: str
    passed: bool
    failures: tuple[str, ...]


@dataclass(frozen=True)
class ProductDemandScenarioPackResult:
    results: tuple[ProductDemandScenarioResult, ...]
    checks: tuple[ScenarioExpectationCheck, ...]

    def result(self, scenario_name: str) -> ProductDemandScenarioResult:
        matching = [result for result in self.results if result.scenario_name == scenario_name]
        if not matching:
            raise KeyError(f"Unknown product-demand scenario: {scenario_name}")
        return matching[0]


@dataclass(frozen=True)
class NonzeroAverageInflationEvidence:
    nonzero_day_average: Decimal
    implied_seven_day_total: Decimal
    observed_mean_seven_day_total: Decimal
    inflation_units: Decimal


ALL_BASELINE_CANDIDATES = frozenset(BASELINE_DEFINITIONS)
STOCKOUT_EVALUATED_CANDIDATES = frozenset(
    {
        BaselineCandidate.ZERO,
        BaselineCandidate.LATEST_VALUE,
        BaselineCandidate.SEASONAL_NAIVE_7,
        BaselineCandidate.MOVING_AVERAGE_7,
        BaselineCandidate.LAST_WEEK_TOTAL,
    }
)


def _decimals(values: list[int]) -> tuple[Decimal, ...]:
    return tuple(Decimal(value) for value in values)


def _product(
    product_key: str,
    values: list[int],
    *,
    overrides: tuple[ScenarioStatusOverride, ...] = (),
) -> ScenarioProductSpec:
    return ScenarioProductSpec(
        product_key=product_key,
        values=_decimals(values),
        status_overrides=overrides,
    )


def _expect_evaluated(
    product_key: str,
    *,
    candidates: frozenset[BaselineCandidate] = ALL_BASELINE_CANDIDATES,
    reasons: frozenset[EvaluationUnavailableReason] = frozenset(),
    daily_winner: BaselineCandidate | None = None,
    check_daily_winner: bool = False,
    seven_day_winner: BaselineCandidate | None = None,
    check_seven_day_winner: bool = False,
) -> ScenarioProductExpectation:
    return ScenarioProductExpectation(
        product_key=product_key,
        status=ScenarioProductStatus.EVALUATED,
        evaluated_candidates=candidates,
        required_reasons=reasons,
        daily_winner=daily_winner,
        check_daily_winner=check_daily_winner,
        seven_day_winner=seven_day_winner,
        check_seven_day_winner=check_seven_day_winner,
    )


PRODUCT_DEMAND_SCENARIOS = (
    ProductDemandScenario(
        name="stable_daily_level",
        description="A constant active product with complete daily evidence.",
        products=(_product("id:STABLE", [5] * 70),),
        expectations=(
            _expect_evaluated(
                "id:STABLE",
                daily_winner=BaselineCandidate.LATEST_VALUE,
                check_daily_winner=True,
                seven_day_winner=BaselineCandidate.LAST_WEEK_TOTAL,
                check_seven_day_winner=True,
            ),
        ),
    ),
    ProductDemandScenario(
        name="strong_weekday_seasonality",
        description="A repeated seven-day demand shape with strong weekday differences.",
        products=(_product("id:SEASONAL", [2, 3, 4, 5, 6, 10, 8] * 10),),
        expectations=(
            _expect_evaluated(
                "id:SEASONAL",
                daily_winner=BaselineCandidate.SEASONAL_NAIVE_7,
                check_daily_winner=True,
                seven_day_winner=BaselineCandidate.LAST_WEEK_TOTAL,
                check_seven_day_winner=True,
            ),
        ),
    ),
    ProductDemandScenario(
        name="recent_upward_level_shift",
        description="Demand moves from a stable low level to a sustained higher level.",
        products=(_product("id:SHIFT", ([5] * 42) + ([10] * 28)),),
        expectations=(_expect_evaluated("id:SHIFT"),),
    ),
    ProductDemandScenario(
        name="intermittent_confirmed_zero_demand",
        description="A sparse product with explicit zero-sale days and a weekly occurrence.",
        products=(_product("id:INTERMITTENT", [0, 0, 0, 6, 0, 0, 0] * 10),),
        expectations=(
            _expect_evaluated(
                "id:INTERMITTENT",
                daily_winner=BaselineCandidate.SEASONAL_NAIVE_7,
                check_daily_winner=True,
                seven_day_winner=BaselineCandidate.LAST_WEEK_TOTAL,
                check_seven_day_winner=True,
            ),
        ),
    ),
    ProductDemandScenario(
        name="all_zero_active_product",
        description="An active product has confirmed zero fulfilled units throughout history.",
        products=(_product("id:ZERO", [0] * 70),),
        expectations=(
            _expect_evaluated(
                "id:ZERO",
                daily_winner=BaselineCandidate.LATEST_VALUE,
                check_daily_winner=True,
                seven_day_winner=BaselineCandidate.LAST_WEEK_TOTAL,
                check_seven_day_winner=True,
            ),
        ),
    ),
    ProductDemandScenario(
        name="short_history",
        description="The product cannot create one complete 28-day-train plus 7-day-test fold.",
        products=(_product("id:SHORT", [2] * 34),),
        expectations=(
            ScenarioProductExpectation(
                product_key="id:SHORT",
                status=ScenarioProductStatus.UNAVAILABLE,
                evaluated_candidates=frozenset(),
                required_reasons=frozenset({EvaluationUnavailableReason.SHORT_HISTORY}),
                check_daily_winner=True,
                check_seven_day_winner=True,
            ),
        ),
    ),
    ProductDemandScenario(
        name="unknown_internal_gap",
        description="An internal date is unknown and must not be converted to zero.",
        products=(
            _product(
                "id:UNKNOWN",
                [3] * 70,
                overrides=(ScenarioStatusOverride(23, ProductDateStatus.MISSING_UNKNOWN),),
            ),
        ),
        expectations=(
            _expect_evaluated(
                "id:UNKNOWN",
                candidates=ALL_BASELINE_CANDIDATES - {BaselineCandidate.SBA_CROSTON},
                reasons=frozenset({EvaluationUnavailableReason.UNKNOWN_TARGET_GAP}),
                daily_winner=BaselineCandidate.LATEST_VALUE,
                check_daily_winner=True,
                seven_day_winner=BaselineCandidate.LAST_WEEK_TOTAL,
                check_seven_day_winner=True,
            ),
        ),
        configuration=EvaluationConfiguration(minimum_folds=2),
    ),
    ProductDemandScenario(
        name="stockout_censored_period",
        description="A stockout-limited date is censored fulfilled demand, not a true zero.",
        products=(
            _product(
                "id:STOCKOUT",
                [4] * 70,
                overrides=(ScenarioStatusOverride(30, ProductDateStatus.STOCKOUT_LIMITED),),
            ),
        ),
        expectations=(
            _expect_evaluated(
                "id:STOCKOUT",
                candidates=STOCKOUT_EVALUATED_CANDIDATES,
                reasons=frozenset({EvaluationUnavailableReason.CENSORED_TARGET}),
                daily_winner=BaselineCandidate.LATEST_VALUE,
                check_daily_winner=True,
                seven_day_winner=BaselineCandidate.LAST_WEEK_TOTAL,
                check_seven_day_winner=True,
            ),
        ),
    ),
    ProductDemandScenario(
        name="unconfirmed_active_period",
        description="A closure near the boundary is excluded pending explicit activity evidence.",
        products=(
            _product(
                "id:ACTIVITY",
                [4] * 70,
                overrides=(ScenarioStatusOverride(69, ProductDateStatus.BUSINESS_CLOSED),),
            ),
        ),
        expectations=(
            _expect_evaluated(
                "id:ACTIVITY",
                reasons=frozenset({EvaluationUnavailableReason.PRODUCT_ACTIVITY_UNCONFIRMED}),
                daily_winner=BaselineCandidate.LATEST_VALUE,
                check_daily_winner=True,
                seven_day_winner=BaselineCandidate.LAST_WEEK_TOTAL,
                check_seven_day_winner=True,
            ),
        ),
    ),
    ProductDemandScenario(
        name="invalid_product_isolated_from_valid_product",
        description="One negative target is rejected without blocking a valid sibling product.",
        products=(
            _product("id:VALID", [3] * 70),
            _product("id:INVALID", ([3] * 69) + [-1]),
        ),
        expectations=(
            _expect_evaluated(
                "id:VALID",
                daily_winner=BaselineCandidate.LATEST_VALUE,
                check_daily_winner=True,
                seven_day_winner=BaselineCandidate.LAST_WEEK_TOTAL,
                check_seven_day_winner=True,
            ),
            ScenarioProductExpectation(
                product_key="id:INVALID",
                status=ScenarioProductStatus.INVALID,
                evaluated_candidates=frozenset(),
                required_reasons=frozenset({EvaluationUnavailableReason.INVALID_TARGET}),
            ),
        ),
    ),
    ProductDemandScenario(
        name="nonzero_day_average_inflation",
        description="A nonzero-day mean wrongly implies more weekly demand than was observed.",
        products=(_product("id:INFLATION", [6, 0, 0, 9, 0, 0, 3] * 10),),
        expectations=(
            _expect_evaluated(
                "id:INFLATION",
                daily_winner=BaselineCandidate.SEASONAL_NAIVE_7,
                check_daily_winner=True,
                seven_day_winner=BaselineCandidate.LAST_WEEK_TOTAL,
                check_seven_day_winner=True,
            ),
        ),
    ),
    ProductDemandScenario(
        name="equal_error_opposite_bias",
        description="Latest value and moving-average 7 have equal MAE but opposite bias.",
        products=(
            _product(
                "id:BIAS",
                ([8] * 21) + [0, 0, 0, 0, 0, 0, 14] + ([8] * 7),
            ),
        ),
        expectations=(_expect_evaluated("id:BIAS"),),
        configuration=EvaluationConfiguration(minimum_folds=1),
    ),
)


def run_product_demand_scenario_pack() -> ProductDemandScenarioPackResult:
    results = tuple(_run_scenario(scenario) for scenario in PRODUCT_DEMAND_SCENARIOS)
    checks = tuple(
        _check_expectations(scenario, result)
        for scenario, result in zip(PRODUCT_DEMAND_SCENARIOS, results)
    )
    return ProductDemandScenarioPackResult(results=results, checks=checks)


def calculate_nonzero_average_inflation(
    product: ScenarioProductSpec,
) -> NonzeroAverageInflationEvidence:
    if len(product.values) % 7 != 0:
        raise ValueError("Nonzero-average evidence requires complete seven-day blocks")
    nonzero = tuple(value for value in product.values if value > 0)
    if not nonzero:
        raise ValueError("Nonzero-average evidence requires at least one positive value")
    nonzero_average = sum(nonzero, Decimal("0")) / Decimal(len(nonzero))
    week_count = Decimal(len(product.values) // 7)
    observed_mean = sum(product.values, Decimal("0")) / week_count
    implied = nonzero_average * Decimal("7")
    return NonzeroAverageInflationEvidence(
        nonzero_day_average=nonzero_average,
        implied_seven_day_total=implied,
        observed_mean_seven_day_total=observed_mean,
        inflation_units=implied - observed_mean,
    )


def _run_scenario(scenario: ProductDemandScenario) -> ProductDemandScenarioResult:
    return ProductDemandScenarioResult(
        scenario_name=scenario.name,
        products=tuple(
            _run_product(product, scenario.configuration) for product in scenario.products
        ),
    )


def _run_product(
    product: ScenarioProductSpec,
    configuration: EvaluationConfiguration,
) -> ScenarioProductResult:
    try:
        series = _build_series(product)
    except ValueError as error:
        return ScenarioProductResult(
            product_key=product.product_key,
            status=ScenarioProductStatus.INVALID,
            evaluated_candidates=frozenset(),
            evidence_reasons=frozenset({EvaluationUnavailableReason.INVALID_TARGET}),
            error_reason=EvaluationUnavailableReason.INVALID_TARGET,
            error_message=str(error),
        )

    report = evaluate_product_baselines(series, configuration)
    evaluated_candidates = frozenset(
        evaluation.candidate.candidate
        for evaluation in report.candidate_evaluations
        if evaluation.availability is EvaluationAvailability.EVALUATED
    )
    evidence_reasons = frozenset(
        {
            *report.unavailable_reasons,
            *(
                reason
                for evaluation in report.candidate_evaluations
                for reason in evaluation.unavailable_reasons
            ),
            *(
                skipped.reason
                for evaluation in report.candidate_evaluations
                for skipped in evaluation.skipped_folds
            ),
        }
    )
    status = (
        ScenarioProductStatus.EVALUATED
        if evaluated_candidates
        else ScenarioProductStatus.UNAVAILABLE
    )
    return ScenarioProductResult(
        product_key=product.product_key,
        status=status,
        evaluated_candidates=evaluated_candidates,
        evidence_reasons=evidence_reasons,
        report=report,
    )


def _build_series(product: ScenarioProductSpec) -> EvaluationSeries:
    start = date(2025, 1, 1)
    overrides = {override.index: override.status for override in product.status_overrides}
    points = []
    for index, value in enumerate(product.values):
        status = overrides.get(
            index,
            ProductDateStatus.CONFIRMED_ZERO if value == 0 else ProductDateStatus.OBSERVED,
        )
        included = status in {
            ProductDateStatus.OBSERVED,
            ProductDateStatus.CONFIRMED_ZERO,
        }
        points.append(
            EvaluationSeriesPoint(
                date=start + timedelta(days=index),
                status=status,
                target_units=value if included else None,
                included=included,
            )
        )
    return EvaluationSeries(
        product_key=product.product_key,
        unit_of_measure=product.unit_of_measure,
        points=tuple(points),
    )


def _check_expectations(
    scenario: ProductDemandScenario,
    result: ProductDemandScenarioResult,
) -> ScenarioExpectationCheck:
    failures: list[str] = []
    products = {product.product_key: product for product in result.products}
    for expectation in scenario.expectations:
        actual = products[expectation.product_key]
        if actual.status is not expectation.status:
            failures.append(
                f"{expectation.product_key}: expected status {expectation.status.value}, "
                f"received {actual.status.value}"
            )
        if actual.evaluated_candidates != expectation.evaluated_candidates:
            failures.append(f"{expectation.product_key}: evaluated candidate set did not match")
        if not expectation.required_reasons.issubset(actual.evidence_reasons):
            failures.append(f"{expectation.product_key}: required evidence reasons were missing")
        daily_winner = actual.report.daily_winner if actual.report is not None else None
        weekly_winner = actual.report.seven_day_winner if actual.report is not None else None
        if expectation.check_daily_winner and daily_winner is not expectation.daily_winner:
            failures.append(f"{expectation.product_key}: daily winner did not match")
        if expectation.check_seven_day_winner and weekly_winner is not expectation.seven_day_winner:
            failures.append(f"{expectation.product_key}: seven-day winner did not match")
    return ScenarioExpectationCheck(
        scenario_name=scenario.name,
        passed=not failures,
        failures=tuple(failures),
    )
