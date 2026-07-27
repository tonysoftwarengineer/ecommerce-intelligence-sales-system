import pandas as pd

from api.serializers import (
    category_series_to_records,
    segment_summary_records,
    state_series_to_records,
)


def test_segment_summary_aggregates_per_label():
    segments = [
        {"customer_unique_id": "a", "segment_label": "High Value", "recency": 10.0, "frequency": 3.0, "monetary": 300.0},
        {"customer_unique_id": "b", "segment_label": "High Value", "recency": 20.0, "frequency": 1.0, "monetary": 100.0},
        {"customer_unique_id": "c", "segment_label": "At Risk", "recency": 400.0, "frequency": 1.0, "monetary": 50.0},
    ]
    summary = {row["segment_label"]: row for row in segment_summary_records(segments)}

    assert summary["High Value"]["customer_count"] == 2
    assert summary["High Value"]["avg_recency"] == 15.0
    assert summary["High Value"]["avg_frequency"] == 2.0
    assert summary["High Value"]["avg_monetary"] == 200.0
    assert summary["At Risk"]["customer_count"] == 1


def test_category_records_preserve_rank_order_and_relabel_unknown():
    # Ranking order must survive serialization, and an untranslated (NaN)
    # category must surface as "Unknown" rather than a null the UI can't render.
    series = pd.Series([30.0, 20.0, 10.0], index=["health_beauty", None, "auto"])
    records = category_series_to_records(series)

    assert [r["category"] for r in records] == ["health_beauty", "Unknown", "auto"]
    assert records[0]["revenue"] == 30.0


def test_state_records_carry_both_code_and_display_name():
    # The frontend keys on the code but displays the full name; two-letter
    # codes alone are meaningless to anyone outside Brazil.
    series = pd.Series([100.0, 50.0], index=["SP", "RJ"])
    records = state_series_to_records(series)

    assert records[0] == {"state_code": "SP", "state_name": "São Paulo", "revenue": 100.0}
    assert records[1]["state_name"] == "Rio de Janeiro"
