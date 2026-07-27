import pandas as pd

from src.models.segmentation import compute_rfm, label_segments


def make_orders(rows):
    """rows: (customer_unique_id, order_id, date, price)"""
    return pd.DataFrame(
        [
            {
                "customer_unique_id": c,
                "order_id": o,
                "order_purchase_timestamp": pd.Timestamp(d),
                "price": p,
            }
            for c, o, d, p in rows
        ]
    )


def test_frequency_counts_orders_not_line_items():
    # The joined frame is item-level: one order with 3 items is 3 rows.
    # Counting rows would report frequency 3 for a single-order customer.
    df = make_orders(
        [
            ("cust-1", "order-1", "2018-01-05", 10.0),
            ("cust-1", "order-1", "2018-01-05", 20.0),
            ("cust-1", "order-1", "2018-01-05", 30.0),
        ]
    )
    rfm = compute_rfm(df)

    assert rfm.loc["cust-1", "frequency"] == 1
    assert rfm.loc["cust-1", "monetary"] == 60.0


def test_recency_is_anchored_to_the_dataset_not_wall_clock():
    # This is 2016-2018 historical data. Anchoring recency to the real "today"
    # would make every customer look years inactive and destroy the signal.
    df = make_orders(
        [
            ("recent", "o1", "2018-08-31", 10.0),
            ("stale", "o2", "2018-06-01", 10.0),
        ]
    )
    rfm = compute_rfm(df)

    # snapshot = max order date + 1 day = 2018-09-01
    assert rfm.loc["recent", "recency"] == 1
    assert rfm.loc["stale", "recency"] == 92


def test_recency_accepts_an_explicit_snapshot_date():
    df = make_orders([("cust-1", "o1", "2018-01-01", 10.0)])
    rfm = compute_rfm(df, snapshot_date=pd.Timestamp("2018-01-11"))

    assert rfm.loc["cust-1", "recency"] == 10


def test_labels_are_derived_from_centroids_not_cluster_numbers():
    # k-means cluster ids are arbitrary -- run to run, cluster 0 could be any
    # group. Labels must come from each cluster's RFM profile.
    clustered = pd.DataFrame(
        {
            "recency": [400.0, 30.0, 60.0, 90.0],
            "frequency": [1.0, 4.0, 1.0, 1.0],
            "monetary": [50.0, 900.0, 20.0, 300.0],
            "cluster": [0, 1, 2, 3],
        }
    )
    labelled = label_segments(clustered)
    by_cluster = dict(zip(labelled["cluster"], labelled["segment_label"]))

    assert by_cluster[1] == "High Value"  # frequent + high spend
    assert by_cluster[0] == "At Risk"  # far and away the stalest
    assert by_cluster[2] == "New/Occasional"  # lowest spend and frequency
    assert len(set(by_cluster.values())) == 4  # every label used exactly once
