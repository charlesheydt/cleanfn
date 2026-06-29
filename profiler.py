"""Dataset profiling for the CSV Data Cleaning Assistant."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def profile_dataframe(df: pd.DataFrame) -> dict[str, Any]:
    """Build a summary profile of the uploaded dataframe."""
    n_rows, n_cols = df.shape
    memory_bytes = int(df.memory_usage(deep=True).sum())
    low_card = list()
    card_list = {}

    columns: list[dict[str, Any]] = []
    for col in df.columns:
        series = df[col]
        dtype = str(series.dtype)
        non_null = int(series.notna().sum())
        null_count = int(series.isna().sum())
        null_pct = round(100.0 * null_count / n_rows, 2) if n_rows else 0.0
        unique_count = int(series.nunique(dropna=True))
        card = unique_count/len(df[col])
        card_list[col] = card

        col_info: dict[str, Any] = {
            "name": col,
            "dtype": dtype,
            "non_null": non_null,
            "null_count": null_count,
            "null_pct": null_pct,
            "unique_count": unique_count,
            "is_numeric": pd.api.types.is_numeric_dtype(series),
            "is_datetime": pd.api.types.is_datetime64_any_dtype(series),
            "card": card
        }
        if card < 0.1:
            low_card.append(col)

        if col_info["is_numeric"]:
            valid = series.dropna()
            if len(valid):
                col_info["min"] = _safe_scalar(valid.min())
                col_info["max"] = _safe_scalar(valid.max())
                col_info["mean"] = round(float(valid.mean()), 4)
                col_info["std"] = round(float(valid.std()), 4) if len(valid) > 1 else 0.0
        elif pd.api.types.is_string_dtype(series) or series.dtype == object:
            lengths = series.dropna().astype(str).str.len()
            if len(lengths):
                col_info["min_length"] = int(lengths.min())
                col_info["max_length"] = int(lengths.max())
                col_info["avg_length"] = round(float(lengths.mean()), 1)

        columns.append(col_info)

    duplicate_rows = int(df.duplicated().sum())
    completely_empty_cols = [c["name"] for c in columns if c["null_count"] == n_rows and n_rows > 0]

    unique_descriptors = {
        col: frozenset(df[col].dropna().unique())
        for col in low_card
    }

    return {
        "n_rows": n_rows,
        "n_cols": n_cols,
        "memory_bytes": memory_bytes,
        "memory_mb": round(memory_bytes / (1024 * 1024), 2),
        "duplicate_rows": duplicate_rows,
        "duplicate_pct": round(100.0 * duplicate_rows / n_rows, 2) if n_rows else 0.0,
        "completely_empty_cols": completely_empty_cols,
        "columns": columns,
        "unique_descriptors": unique_descriptors,
        "low_card": low_card,
        "card_list": card_list
    }



def _safe_scalar(value: Any) -> Any:
    if isinstance(value, (np.integer, np.floating)):
        return float(value) if isinstance(value, np.floating) else int(value)
    if hasattr(value, "item"):
        return value.item()
    return value
