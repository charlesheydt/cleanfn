from __future__ import annotations

from typing import Any

from rapidfuzz import fuzz

import pandas as pd


def run_diagnostics(df: pd.DataFrame, profile: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    n_rows = len(df)

    if n_rows == 0:
        issues.append(
            {
                "id": "empty_dataset",
                "severity": "critical",
                "category": "structure",
                "message": "Dataset has no rows.",
                "columns": [],
                "count": 0,
            }
        )
        return issues

    dup_count = int(df.duplicated().sum())
    if dup_count > 0:
        issues.append(
            {
                "id": "duplicate_rows",
                "severity": "medium",
                "category": "duplicates",
                "message": f"{dup_count:,} duplicate row(s) detected.",
                "columns": [],
                "count": dup_count,
            }
        )

    for col in df.columns:
        series = df[col]
        null_count = int(series.isna().sum())
        if null_count > 0:
            issues.append(
                {
                    "id": f"missing_{col}",
                    "severity": _missing_severity(null_count, n_rows),
                    "category": "missing",
                    "message": f"Column '{col}' has {null_count:,} missing value(s) ({100 * null_count / n_rows:.1f}%).",
                    "columns": [col],
                    "count": null_count,
                }
            )

        if null_count == n_rows:
            issues.append(
                {
                    "id": f"empty_column_{col}",
                    "severity": "high",
                    "category": "structure",
                    "message": f"Column '{col}' is entirely empty.",
                    "columns": [col],
                    "count": null_count,
                }
            )

        if pd.api.types.is_numeric_dtype(series):
            issues.extend(_numeric_issues(series, col, n_rows))
        elif _is_text_column(series):
            issues.extend(_text_issues(series, col, n_rows))

    constant_cols = [c for c in df.columns if df[c].nunique(dropna=True) <= 1 and df[c].notna().any()]
    for col in constant_cols:
        issues.append(
            {
                "id": f"constant_{col}",
                "severity": "low",
                "category": "variance",
                "message": f"Column '{col}' has only one distinct non-null value.",
                "columns": [col],
                "count": 1,
            }
        )

    high_card = []

    strong_identifiers = ["id",
    "patient",
    "participant",
    "subject",
    "record",
    "case",
    "member",
    "account"]
    weak_identifiers = ["name",
    "visit",
    "encounter",
    "sample"]

    for col in df.columns:
        col_lower = col.lower().strip()
        nonnull = df[col].dropna()

        if len(nonnull) == 0:
            continue

        ur = nonnull.nunique()/len(nonnull)
        strong_match = any(keyword in col_lower 
        for keyword in strong_identifiers)
        weak_match = any(keyword in col_lower
        for keyword in weak_identifiers)
        
        
        if ur >= 0.99 or strong_match:
            high_card.append(col)
        elif ur >= 0.95 and weak_match:
            high_card.append(col)

    for col in high_card:
        issues.append(
            {
                "id": f"high_cardinality_{col}",
                "severity": "low",
                "category": "cardinality",
                "message": f"Column '{col}' has very high cardinality (possible ID column).",
                "columns": [col],
                "count": int(df[col].nunique(dropna=True)),
            }
        )

    issues.extend(collapse_columns(df))

    return issues


def _missing_severity(null_count: int, n_rows: int) -> str:
    pct = null_count / n_rows if n_rows else 0
    if pct >= 0.5:
        return "high"
    if pct >= 0.1:
        return "medium"
    return "low"


def _is_text_column(series: pd.Series) -> bool:
    return pd.api.types.is_string_dtype(series) or series.dtype == object


def _numeric_issues(series: pd.Series, col: str, n_rows: int) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    valid = series.dropna()
    if len(valid) == 0:
        return issues

    q1, q3 = valid.quantile(0.25), valid.quantile(0.75)
    iqr = q3 - q1
    if iqr > 0:
        lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        outlier_mask = (series < lower) | (series > upper)
        outlier_count = int(outlier_mask.sum())
        if outlier_count > 0:
            issues.append(
                {
                    "id": f"outliers_{col}",
                    "severity": "medium",
                    "category": "outliers",
                    "message": f"Column '{col}' has {outlier_count:,} potential outlier(s) (IQR rule).",
                    "columns": [col],
                    "count": outlier_count,
                }
            )

    if (valid == 0).all() and len(valid) > 1:
        issues.append(
            {
                "id": f"zero_variance_{col}",
                "severity": "low",
                "category": "variance",
                "message": f"Column '{col}' contains only zeros.",
                "columns": [col],
                "count": len(valid),
            }
        )

    return issues


def _text_issues(series: pd.Series, col: str, n_rows: int) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    text = series.dropna().astype(str)
    if len(text) == 0:
        return issues

    stripped = text.str.strip()
    whitespace_diff = (text != stripped).sum()
    if whitespace_diff > 0:
        issues.append(
            {
                "id": f"whitespace_{col}",
                "severity": "low",
                "category": "formatting",
                "message": f"Column '{col}' has {int(whitespace_diff):,} value(s) with leading/trailing whitespace.",
                "columns": [col],
                "count": int(whitespace_diff),
            }
        )

    lower = text.str.lower()
    dup_labels = int(lower.duplicated().sum())
    if dup_labels > 0 and text.nunique() > lower.nunique():
        issues.append(
            {
                "id": f"case_inconsistent_{col}",
                "severity": "low",
                "category": "formatting",
                "message": f"Column '{col}' may have case inconsistencies ({dup_labels:,} duplicate labels when lowercased).",
                "columns": [col],
                "count": dup_labels,
            }
        )


    return issues

def collapse_columns(df: pd.DataFrame):
    issues: list[dict[str, Any]] = []
    max_unique = 75
    threshold = 75

    COMMON_VALUE_MAPPINGS = {
    "yes": "Yes",
    "y": "Yes",
    "no": "No",
    "n": "No",
    "male": "Male",
    "m": "Male",
    "female": "Female",
    "f": "Female",
    "positive": "Positive",
    "pos": "Positive",
    "+": "Positive",
    "negative": "Negative",
    "neg": "Negative",
    "-": "Negative",
    }

    OPPOSITE_PAIRS = {
    frozenset(["male", "female"]),
    frozenset(["yes", "no"]),
    frozenset(["positive", "negative"]),
    frozenset(["pos", "neg"]),
    frozenset(["y", "n"]),
    }


    print("THRESHOLD =", threshold)


    for col in df.columns:
        counts = df[col].dropna().astype(str).str.strip().value_counts()


        if len(counts) > max_unique or len(counts) == 0:
            continue

        if pd.api.types.is_numeric_dtype(df[col]):
            continue

        values = list(counts.index)
        mapping = {}

        for value in values:

            clean_value = value.strip().casefold()
            valid_targets = []

            if clean_value in COMMON_VALUE_MAPPINGS:
                canonical = COMMON_VALUE_MAPPINGS[clean_value]
            
                if value != canonical:
                    mapping[value] = canonical
                
                continue

            for target in values:
                
                pair = frozenset([value.casefold(), target.casefold()])

                if target == value:
                    continue

                if pair in OPPOSITE_PAIRS:
                    continue

                print(value, target, fuzz.ratio(value.lower(), target.lower()))

                score = fuzz.ratio(value.lower(), target.lower())
                if score >= threshold and counts[value] < counts[target]:
                    valid_targets.append((target, counts[target], score))

            if valid_targets:
                best_target = max(valid_targets, key = lambda x: x[1])
                mapping[value] = best_target[0]
        
        if mapping:
            examples = ", ".join(
                f"{source} → {target}"
                for source, target in list(mapping.items())[:3]
            )

            issues.append(
                {
                    "id": f"fuzzy_category_matches_{col}",
                "severity": "low",
                "category": "formatting",
                "message": (
                    f"Column '{col}' has similar category values that may represent the same label "
                    f"(e.g., {examples})."
                ),
                "columns": [col],
                "count": len(mapping),
                "mapping": mapping,
                }
            )

    return issues



def identify_id_columns(df: pd.DataFrame) -> list[str]:
    id_columns = []
    strong_identifiers = ["id",
    "patient",
    "participant",
    "subject",
    "record",
    "case",
    "member",
    "account"]
    weak_identifiers = ["name",
    "visit",
    "encounter",
    "sample"]

    for col in df.columns:
        col_lower = col.lower().strip()
        nonnull = df[col].dropna()

        if len(nonnull) == 0:
            continue

        ur = nonnull.nunique()/len(nonnull)
        strong_match = any(keyword in col_lower 
        for keyword in strong_identifiers)
        weak_match = any(keyword in col_lower
        for keyword in weak_identifiers)
        
        
        if ur >= 0.99 or strong_match:
            id_columns.append(col)
        elif ur >= 0.95 and weak_match:
            id_columns.append(col)
    
    return id_columns


def severity_order() -> dict[str, int]:
    return {"critical": 0, "high": 1, "medium": 2, "low": 3}


def sort_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    order = severity_order()
    return sorted(issues, key=lambda i: (order.get(i["severity"], 9), i["category"], i["id"]))