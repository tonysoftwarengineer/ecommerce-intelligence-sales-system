"""Process-local, privacy-safe metrics for completed sales analyses.

The product does not yet have authentication or durable storage. These metrics
are therefore intended for local development and controlled evaluation only;
they reset when the API process restarts and deliberately retain no CSV data
or business identifiers.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from math import ceil
from statistics import mean, median
from threading import RLock
from typing import Any


class AnalysisObservability:
    """Collect bounded aggregate metrics for successfully completed analyses."""

    def __init__(self, max_latency_samples: int = 1_000) -> None:
        if max_latency_samples < 1:
            raise ValueError("max_latency_samples must be at least 1")
        self._max_latency_samples = max_latency_samples
        self._lock = RLock()
        self.clear()

    def record_completed(
        self,
        duration_seconds: float,
        currency_reports: dict[str, dict[str, Any]],
    ) -> None:
        """Record aggregate output states without retaining report content."""
        duration_milliseconds = max(0.0, duration_seconds * 1_000)
        with self._lock:
            self._analysis_runs += 1
            self._latency_milliseconds.append(duration_milliseconds)
            if len(self._latency_milliseconds) > self._max_latency_samples:
                self._latency_milliseconds.pop(0)

            for report in currency_reports.values():
                self._currency_reports += 1
                diagnostics = report.get("diagnostics", {})
                for section_name in ("comparison", "anomalies"):
                    section = diagnostics.get(section_name, {})
                    status = str(section.get("status", "unavailable"))
                    self._diagnostic_statuses[section_name][status] += 1
                    if _has_processing_error(section.get("unavailable_capabilities", [])):
                        self._diagnostic_processing_errors[section_name] += 1

                forecast_status = str(report.get("forecast", {}).get("status", "unavailable"))
                self._forecast_statuses[forecast_status] += 1

    def snapshot(self) -> dict[str, Any]:
        """Return aggregate metrics suitable for a development-only endpoint."""
        with self._lock:
            return {
                "scope": (
                    "Process-local development metrics. They reset when the API restarts "
                    "and retain no CSV contents, filenames, or business identifiers."
                ),
                "analysis_runs": self._analysis_runs,
                "currency_reports": self._currency_reports,
                "latency_ms": _latency_summary(self._latency_milliseconds),
                "diagnostics": {
                    section_name: _diagnostic_summary(
                        statuses,
                        self._diagnostic_processing_errors[section_name],
                    )
                    for section_name, statuses in self._diagnostic_statuses.items()
                },
                "forecast_status_counts": dict(sorted(self._forecast_statuses.items())),
            }

    def clear(self) -> None:
        """Reset aggregate development metrics."""
        with self._lock:
            self._analysis_runs = 0
            self._currency_reports = 0
            self._latency_milliseconds: list[float] = []
            self._diagnostic_statuses: dict[str, Counter[str]] = {
                "comparison": Counter(),
                "anomalies": Counter(),
            }
            self._diagnostic_processing_errors: Counter[str] = Counter()
            self._forecast_statuses: Counter[str] = Counter()


def _has_processing_error(limitations: Iterable[object]) -> bool:
    return any(
        isinstance(limitation, dict) and limitation.get("code") == "diagnostic_processing_error"
        for limitation in limitations
    )


def _latency_summary(samples: list[float]) -> dict[str, float | int | None]:
    if not samples:
        return {
            "sample_count": 0,
            "average": None,
            "p50": None,
            "p95": None,
            "maximum": None,
        }
    ordered = sorted(samples)
    return {
        "sample_count": len(samples),
        "average": round(mean(samples), 3),
        "p50": round(median(samples), 3),
        "p95": round(_nearest_rank(ordered, 0.95), 3),
        "maximum": round(max(samples), 3),
    }


def _nearest_rank(ordered_values: list[float], quantile: float) -> float:
    rank = max(1, ceil(quantile * len(ordered_values)))
    return ordered_values[min(rank - 1, len(ordered_values) - 1)]


def _diagnostic_summary(
    statuses: Counter[str],
    processing_error_count: int,
) -> dict[str, Any]:
    status_counts = dict(sorted(statuses.items()))
    total = sum(status_counts.values())
    assessed = status_counts.get("available", 0) + status_counts.get("no_findings", 0)
    return {
        "section_reports": total,
        "assessed_reports": assessed,
        "unavailable_reports": status_counts.get("unavailable", 0),
        "assessed_percent": round((assessed / total) * 100, 1) if total else None,
        "processing_error_count": processing_error_count,
        "status_counts": status_counts,
    }
