import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

DEFAULT_N_CLUSTERS = 4


def compute_rfm(df: pd.DataFrame, snapshot_date: pd.Timestamp = None) -> pd.DataFrame:
    if snapshot_date is None:
        snapshot_date = df["order_purchase_timestamp"].max() + pd.Timedelta(days=1)

    grouped = df.groupby("customer_unique_id").agg(
        last_order_date=("order_purchase_timestamp", "max"),
        frequency=("order_id", "nunique"),
        monetary=("price", "sum"),
    )
    grouped["recency"] = (snapshot_date - grouped["last_order_date"]).dt.days

    return grouped[["recency", "frequency", "monetary"]]


def cluster_customers(rfm: pd.DataFrame, n_clusters: int = DEFAULT_N_CLUSTERS, random_state: int = 42) -> pd.DataFrame:
    features = pd.DataFrame(
        {
            "recency": rfm["recency"],
            "frequency": rfm["frequency"],
            "log_monetary": np.log1p(rfm["monetary"]),
        }
    )
    scaled = StandardScaler().fit_transform(features)

    kmeans = KMeans(n_clusters=n_clusters, random_state=random_state, n_init=10)
    clusters = kmeans.fit_predict(scaled)

    result = rfm.copy()
    result["cluster"] = clusters
    return result


def label_segments(clustered: pd.DataFrame) -> pd.DataFrame:
    centroids = clustered.groupby("cluster")[["recency", "frequency", "monetary"]].mean()

    recency_rank = centroids["recency"].rank(ascending=True)
    frequency_rank = centroids["frequency"].rank(ascending=False)
    monetary_rank = centroids["monetary"].rank(ascending=False)

    labels = {}

    combined_score = recency_rank + frequency_rank + monetary_rank
    high_value_cluster = combined_score.idxmin()
    labels[high_value_cluster] = "High Value"

    remaining = [c for c in centroids.index if c != high_value_cluster]
    new_score = frequency_rank[remaining] + monetary_rank[remaining]
    new_cluster = new_score.idxmax()
    labels[new_cluster] = "New/Occasional"

    remaining = [c for c in remaining if c != new_cluster]
    at_risk_cluster = recency_rank[remaining].idxmax()
    labels[at_risk_cluster] = "At Risk"

    remaining = [c for c in remaining if c != at_risk_cluster]
    for c in remaining:
        labels[c] = "Regular"

    result = clustered.copy()
    result["segment_label"] = result["cluster"].map(labels)
    return result


def segment_customers(df: pd.DataFrame, n_clusters: int = DEFAULT_N_CLUSTERS) -> pd.DataFrame:
    rfm = compute_rfm(df)
    clustered = cluster_customers(rfm, n_clusters=n_clusters)
    labeled = label_segments(clustered)
    return labeled.reset_index()


def segment_customers_as_records(df: pd.DataFrame, n_clusters: int = DEFAULT_N_CLUSTERS) -> list:
    labeled = segment_customers(df, n_clusters=n_clusters)
    return [
        {
            "customer_unique_id": row["customer_unique_id"],
            "segment_label": row["segment_label"],
            "recency": float(row["recency"]),
            "frequency": float(row["frequency"]),
            "monetary": float(row["monetary"]),
        }
        for _, row in labeled.iterrows()
    ]
