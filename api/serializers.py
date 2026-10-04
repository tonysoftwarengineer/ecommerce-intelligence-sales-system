import json
import re

import pandas as pd


def dataframe_sample_records(df: pd.DataFrame, limit: int = 5) -> list[dict]:
    """Return JSON-safe records without leaking more rows than requested."""
    return json.loads(df.head(limit).to_json(orient="records", date_format="iso"))


def privacy_safe_preview_records(df: pd.DataFrame, limit: int = 5) -> list[dict]:
    """Mask direct identifiers in the browser preview; source bytes stay private in memory."""
    records = dataframe_sample_records(df, limit)
    for record in records:
        for column, value in record.items():
            if value is None or not _is_direct_identifier_column(column):
                continue
            record[column] = _mask_preview_value(str(value), column)
    return records


def _is_direct_identifier_column(column: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", column.casefold())
    return (
        "email" in normalized
        or "phone" in normalized
        or "mobile" in normalized
        or normalized in {"customername", "clientname", "fullname", "contactname"}
    )


def _mask_preview_value(value: str, column: str) -> str:
    normalized = re.sub(r"[^a-z0-9]", "", column.casefold())
    if "email" in normalized and "@" in value:
        local, domain = value.split("@", 1)
        return f"{local[:1]}***@{domain}"
    if "name" in normalized:
        return " ".join(f"{part[:1]}***" for part in value.split() if part) or "***"
    return f"{value[:2]}***"


def dataframe_to_csv_bytes(df: pd.DataFrame) -> bytes:
    """Serialize a dataframe for download, encoding collection cells as JSON."""
    export = df.copy()
    for column in export.columns:
        if export[column].map(lambda value: isinstance(value, (list, tuple))).any():
            export[column] = export[column].map(
                lambda value: json.dumps(value) if isinstance(value, (list, tuple)) else value
            )
    return export.to_csv(index=False).encode("utf-8")
