"""Typed, framework-independent contracts for Diagnostic Intelligence.

The diagnostic engine uses immutable dataclasses rather than API models so its
business outputs can be tested, persisted, or explained by a future LLM without
coupling the calculation path to FastAPI or a model provider.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class DiagnosticCategory(str, Enum):
    PERFORMANCE_CHANGE = "performance_change"
    ANOMALY = "anomaly"
    DATA_QUALITY = "data_quality"
    OPPORTUNITY = "opportunity"


class ConfidenceLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNAVAILABLE = "unavailable"


class Priority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class DiagnosticStatus(str, Enum):
    AVAILABLE = "available"
    NO_FINDINGS = "no_findings"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class RecommendationScore:
    """Transparent score used to rank a human-reviewed recommendation."""

    impact: int
    urgency: int
    confidence: int
    total: int

    def __post_init__(self) -> None:
        for name, value in (
            ("impact", self.impact),
            ("urgency", self.urgency),
            ("confidence", self.confidence),
        ):
            if value not in {0, 1, 2, 3}:
                raise ValueError(f"{name} score must be between 0 and 3")
        if self.total != self.impact + self.urgency + self.confidence:
            raise ValueError("Recommendation score total must equal its component scores")


@dataclass(frozen=True)
class ComparisonPeriod:
    """Exact complete periods or baseline used to support a diagnostic."""

    current_label: str
    baseline_label: str
    basis: str

    def __post_init__(self) -> None:
        _require_text("current_label", self.current_label)
        _require_text("baseline_label", self.baseline_label)
        _require_text("basis", self.basis)


@dataclass(frozen=True)
class EvidenceItem:
    """A calculated metric used to support an observation, never generated text."""

    metric: str
    current_value: float
    unit: str
    provenance: str
    baseline_value: Optional[float] = None
    absolute_change: Optional[float] = None
    percent_change: Optional[float] = None

    def __post_init__(self) -> None:
        _require_text("metric", self.metric)
        _require_text("unit", self.unit)
        _require_text("provenance", self.provenance)
        _require_number("current_value", self.current_value)
        for name, value in (
            ("baseline_value", self.baseline_value),
            ("absolute_change", self.absolute_change),
            ("percent_change", self.percent_change),
        ):
            if value is not None:
                _require_number(name, value)
        if self.baseline_value is None and any(
            value is not None for value in (self.absolute_change, self.percent_change)
        ):
            raise ValueError("Change values require a baseline_value")


@dataclass(frozen=True)
class Contributor:
    """A measurable factor contributing to a diagnostic, when calculable."""

    factor: str
    contribution_value: float
    unit: str
    explanation: str
    share_of_change_percent: Optional[float] = None

    def __post_init__(self) -> None:
        _require_text("factor", self.factor)
        _require_number("contribution_value", self.contribution_value)
        _require_text("unit", self.unit)
        _require_text("explanation", self.explanation)
        if self.share_of_change_percent is not None:
            _require_number("share_of_change_percent", self.share_of_change_percent)


@dataclass(frozen=True)
class Limitation:
    """A data or modelling constraint that qualifies an insight."""

    code: str
    message: str

    def __post_init__(self) -> None:
        _require_text("code", self.code)
        _require_text("message", self.message)


@dataclass(frozen=True)
class RecommendedAction:
    """A human-reviewed next action; the system never executes it directly."""

    id: str
    title: str
    description: str
    priority: Priority
    requires_human_review: bool = True
    estimated_impact: Optional[float] = None
    impact_unit: Optional[str] = None
    score: Optional[RecommendationScore] = None

    def __post_init__(self) -> None:
        _require_text("id", self.id)
        _require_text("title", self.title)
        _require_text("description", self.description)
        if not self.requires_human_review:
            raise ValueError("Recommended actions must require human review")
        if self.estimated_impact is not None:
            _require_number("estimated_impact", self.estimated_impact)
            if self.impact_unit is None:
                raise ValueError("estimated_impact requires an impact_unit")
        elif self.impact_unit is not None:
            raise ValueError("impact_unit requires an estimated_impact")
        if self.impact_unit is not None:
            _require_text("impact_unit", self.impact_unit)


@dataclass(frozen=True)
class DiagnosticInsight:
    """One traceable finding produced by deterministic diagnostic rules."""

    id: str
    title: str
    category: DiagnosticCategory
    observation: str
    confidence: ConfidenceLevel
    priority: Priority
    evidence: tuple[EvidenceItem, ...]
    comparison_period: Optional[ComparisonPeriod] = None
    contributors: tuple[Contributor, ...] = field(default_factory=tuple)
    limitations: tuple[Limitation, ...] = field(default_factory=tuple)
    recommended_action: Optional[RecommendedAction] = None

    def __post_init__(self) -> None:
        _require_text("id", self.id)
        _require_text("title", self.title)
        _require_text("observation", self.observation)
        if not self.evidence:
            raise ValueError("Diagnostic insights require at least one evidence item")
        if self.confidence is ConfidenceLevel.UNAVAILABLE and not self.limitations:
            raise ValueError("Unavailable insights require at least one limitation")


@dataclass(frozen=True)
class DiagnosticReport:
    """A currency-isolated collection of insights for one completed analysis."""

    contract_version: str
    currency: str
    insights: tuple[DiagnosticInsight, ...]
    unavailable_capabilities: tuple[Limitation, ...] = field(default_factory=tuple)
    status: DiagnosticStatus = DiagnosticStatus.AVAILABLE

    def __post_init__(self) -> None:
        _require_text("contract_version", self.contract_version)
        if len(self.currency) != 3 or not self.currency.isupper() or not self.currency.isalpha():
            raise ValueError("currency must be a three-letter uppercase code")
        insight_ids = [insight.id for insight in self.insights]
        if len(insight_ids) != len(set(insight_ids)):
            raise ValueError("Diagnostic report insight ids must be unique")


def _require_text(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")


def _require_number(name: str, value: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
