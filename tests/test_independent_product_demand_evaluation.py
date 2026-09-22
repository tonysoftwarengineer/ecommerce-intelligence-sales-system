from __future__ import annotations

import json
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from scripts.evaluate_independent_product_demand import _is_private_path
from src.product_demand.independent_evaluation import (
    IndependentEvaluationConfigError,
    independent_evaluation_config_from_dict,
    render_independent_evaluation_markdown,
    run_independent_evaluation,
    sanitize_independent_evaluation,
)


def _config(**product_demand_overrides: object):
    product_demand = {
        "default_unit_of_measure": None,
        "confirm_product_names_unique": False,
        "confirm_product_categories": False,
        "export_covers_all_open_days": True,
        "stockout_tracking_complete": True,
        "business_closed_dates": [],
        "stockout_dates": [],
    }
    product_demand.update(product_demand_overrides)
    return independent_evaluation_config_from_dict(
        {
            "mapping": {
                "order_id": "Order ID",
                "order_date": "Order Date",
                "customer_id": "Customer ID",
                "unit_price": "Unit Price",
                "quantity": "Quantity",
                "product_id": "SKU",
                "unit_of_measure": "Unit",
                "order_status": "Status",
            },
            "revenue_mode": "unit_price_times_quantity",
            "negative_revenue_policy": "invalid",
            "date_format": "%Y-%m-%d",
            "currency": "NGN",
            "assume_all_completed": False,
            "status_mapping": {"completed": "completed"},
            "discount_type": "none",
            "confirm_quarantine": True,
            "product_demand": product_demand,
        }
    )


def _sales(values: list[int], *, sku: str = "SECRET-SKU") -> pd.DataFrame:
    start = date(2024, 1, 1)
    return pd.DataFrame(
        [
            {
                "Order ID": f"ORDER-{index:03d}",
                "Order Date": (start + timedelta(days=index)).isoformat(),
                "Customer ID": f"CUSTOMER-{index:03d}",
                "Unit Price": "9.99",
                "Quantity": str(quantity),
                "SKU": sku,
                "Unit": "piece",
                "Status": "completed",
            }
            for index, quantity in enumerate(values)
        ]
    )


def test_constant_complete_history_scores_frozen_product_preview() -> None:
    report = run_independent_evaluation(_sales([1] * 245), _config())

    assert report["outcome"]["classification"] == "consistent_external_evidence"
    products = report["products"]
    assert products["previews_shown"] == 13
    assert products["coverage_percent"] == 100.0
    assert products["metrics_on_shown_previews"]["skill_vs_zero"] == "1"


def test_final_holdout_values_do_not_change_first_prediction() -> None:
    original = run_independent_evaluation(_sales([1] * 245), _config())
    changed = run_independent_evaluation(_sales(([1] * 154) + ([20] * 91)), _config())

    first_original = original["products"]["scopes"][0]["outcomes"][0]
    first_changed = changed["products"]["scopes"][0]["outcomes"][0]
    assert first_original["predicted_total_units"] == first_changed["predicted_total_units"]
    assert first_original["actual_total_units"] != first_changed["actual_total_units"]


def test_sanitized_report_and_markdown_do_not_retain_business_identifiers() -> None:
    report = run_independent_evaluation(_sales([1] * 245), _config())

    sanitized = sanitize_independent_evaluation(report)
    serialized = str(sanitized)
    markdown = render_independent_evaluation_markdown(report)

    assert "SECRET-SKU" not in serialized
    assert "2024-01-01" not in serialized
    assert "9.99" not in serialized
    assert "SECRET-SKU" not in markdown
    assert "2024-01-01" not in markdown


def test_quarantine_requires_explicit_confirmation_before_scoring() -> None:
    source = _sales([1] * 245)
    source.loc[0, "Order Date"] = "not a date"
    config = _config()
    object.__setattr__(config, "confirm_quarantine", False)

    report = run_independent_evaluation(source, config)

    assert report["outcome"]["classification"] == "inconclusive"
    assert report["products"]["forecast_opportunities"] == 0
    assert "quarantine confirmation" in report["outcome"]["message"]


def test_unconfirmed_stockout_tracking_prevents_numeric_preview() -> None:
    report = run_independent_evaluation(
        _sales([1] * 245), _config(stockout_tracking_complete=False)
    )

    assert report["outcome"]["classification"] == "inconclusive"
    assert report["products"]["previews_shown"] == 0
    assert report["products"]["abstentions"] == 13


def test_short_history_is_inconclusive_instead_of_forcing_a_preview() -> None:
    report = run_independent_evaluation(_sales([1] * 100), _config())

    assert report["outcome"]["classification"] == "inconclusive"
    assert report["products"]["previews_shown"] == 0
    assert report["products"]["abstentions"] == 13


def test_unknown_calendar_gap_prevents_numeric_preview() -> None:
    source = _sales([1] * 245).drop(index=20).reset_index(drop=True)
    report = run_independent_evaluation(
        source,
        _config(export_covers_all_open_days=False),
    )

    assert report["outcome"]["classification"] == "inconclusive"
    assert report["products"]["previews_shown"] == 0


def test_mixed_units_for_one_product_are_skipped_safely() -> None:
    source = _sales([1] * 245)
    source.loc[30, "Unit"] = "pack"
    report = run_independent_evaluation(source, _config())

    assert report["outcome"]["classification"] == "inconclusive"
    assert report["products"]["previews_shown"] == 0
    assert report["products"]["skipped_reason_counts"]["full_holdout_series_unavailable"] == 1


def test_invalid_mapping_configuration_is_rejected_before_source_processing() -> None:
    config_payload = {
        "mapping": {"order_id": "Order ID"},
        "revenue_mode": "row_total",
        "negative_revenue_policy": "invalid",
        "date_format": "%Y-%m-%d",
        "currency": "NGN",
        "assume_all_completed": True,
        "confirm_quarantine": True,
        "product_demand": {},
    }

    config = independent_evaluation_config_from_dict(config_payload)
    with pytest.raises(IndependentEvaluationConfigError, match="Missing required mappings"):
        run_independent_evaluation(_sales([1] * 245), config)


def test_cli_writes_private_detail_and_sanitized_markdown(tmp_path: Path) -> None:
    private_dir = tmp_path / "data" / "private"
    private_dir.mkdir(parents=True)
    source_path = private_dir / "business_sales.csv"
    config_path = private_dir / "business_mapping.json"
    detail_path = private_dir / "business_evaluation.json"
    summary_path = tmp_path / "docs" / "independent_business_forecasting.md"
    _sales([1] * 245).to_csv(source_path, index=False)
    config_path.write_text(
        json.dumps(
            {
                "mapping": {
                    "order_id": "Order ID",
                    "order_date": "Order Date",
                    "customer_id": "Customer ID",
                    "unit_price": "Unit Price",
                    "quantity": "Quantity",
                    "product_id": "SKU",
                    "unit_of_measure": "Unit",
                    "order_status": "Status",
                },
                "revenue_mode": "unit_price_times_quantity",
                "negative_revenue_policy": "invalid",
                "date_format": "%Y-%m-%d",
                "currency": "NGN",
                "assume_all_completed": False,
                "status_mapping": {"completed": "completed"},
                "discount_type": "none",
                "confirm_quarantine": True,
                "product_demand": {
                    "confirm_product_names_unique": False,
                    "confirm_product_categories": False,
                    "export_covers_all_open_days": True,
                    "stockout_tracking_complete": True,
                    "business_closed_dates": [],
                    "stockout_dates": [],
                },
            }
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.evaluate_independent_product_demand",
            "--csv",
            str(source_path),
            "--config",
            str(config_path),
            "--private-output",
            str(detail_path),
            "--summary-output",
            str(summary_path),
        ],
        cwd=Path(__file__).parents[1],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "consistent_external_evidence" in completed.stdout
    assert "SECRET-SKU" in detail_path.read_text(encoding="utf-8")
    assert "SECRET-SKU" not in summary_path.read_text(encoding="utf-8")


def test_detailed_output_path_requires_the_private_data_directory(tmp_path: Path) -> None:
    assert _is_private_path(tmp_path / "data" / "private" / "evaluation.json")
    assert not _is_private_path(tmp_path / "docs" / "evaluation.json")
