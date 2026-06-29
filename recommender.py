"""Cleaning action recommendations based on diagnostics."""

from __future__ import annotations

from typing import Any

import pandas as pd


def recommend_actions(df: pd.DataFrame, issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Map diagnostics to actionable cleaning recommendations."""
    actions: list[dict[str, Any]] = []
    seen: set[str] = set()

    for issue in issues:
        for action in _actions_for_issue(df, issue):
            if action["id"] not in seen:
                seen.add(action["id"])
                actions.append(action)

    return _prioritize(actions)


def _actions_for_issue(df: pd.DataFrame, issue: dict[str, Any]) -> list[dict[str, Any]]:
    issue_id = issue["id"]
    category = issue["category"]
    columns = issue.get("columns", [])

    if issue_id == "duplicate_rows":
        return [
            {
                "id": "drop_duplicate_rows",
                "label": "Remove duplicate rows",
                "description": "Keep the first occurrence of each duplicate row.",
                "action_type": "drop_duplicates_row",
                "params": {"subset": None, "keep": "first"},
                "related_issues": [issue_id],
                "priority": 10,
            }
        ]

    if category == "missing" and columns:
        col = columns[0]
        number_missing = int(df[col].isna().sum())

        fraction_missing = number_missing/len(col)

        if fraction_missing >= 0.05 or number_missing > 5:
            return [
                {
                    "id": f"drop_rows_missing_{col}",
                    "label": f"Drop rows with missing '{col}'",
                    "description": f"Remove rows where '{col}' is null ({issue['count']:,} rows).",
                    "action_type": "drop_na",
                    "params": {"subset": [col], "how": "any"},
                    "related_issues": [issue_id],
                    "priority": 30,
                },
                {
                    "id": f"fill_missing_{col}_median",
                    "label": f"Fill missing '{col}' with median",
                    "description": f"Impute nulls in '{col}' using the column median (numeric only).",
                    "action_type": "fill_na_median",
                    "params": {"column": col, "strategy": "median"},
                    "related_issues": [issue_id],
                    "priority": 40,
                    "enabled": pd.api.types.is_numeric_dtype(df[col]),
                },
                {
                    "id": f"fill_missing_{col}_mode",
                    "label": f"Fill missing '{col}' with mode",
                    "description": f"Impute nulls in '{col}' using the most frequent value.",
                    "action_type": "fill_na_mode",
                    "params": {"column": col, "strategy": "mode"},
                    "related_issues": [issue_id],
                    "priority": 41,
                },

                {
                    "id": f"fill_missing_{col}_stochastically",
                    "label": f"Fill missing '{col}' with stochastic imputation",
                    "description": f"Impute nulls in '{col}' by bootstrapping from the empirical "
                    "distribution (numerical columns only)",
                    "action_type": "fill_na",
                    "params": {"column": col, "strategy": "stochastic"},
                    "related_issues": [issue_id],
                    "priority": 39,
                    "enabled": pd.api.types.is_numeric_dtype(df[col]),
                }
            ]


        return [
            {
                "id": f"drop_rows_missing_{col}",
                "label": f"Drop rows with missing '{col}'",
                "description": f"Remove rows where '{col}' is null ({issue['count']:,} rows).",
                "action_type": "drop_na",
                "params": {"subset": [col], "how": "any"},
                "related_issues": [issue_id],
                "priority": 30,
            },
            {
                "id": f"fill_missing_{col}_median",
                "label": f"Fill missing '{col}' with median",
                "description": f"Impute nulls in '{col}' using the column median (numeric only).",
                "action_type": "fill_na_median",
                "params": {"column": col, "strategy": "median"},
                "related_issues": [issue_id],
                "priority": 40,
                "enabled": pd.api.types.is_numeric_dtype(df[col]),
            },
            {
                "id": f"fill_missing_{col}_mode",
                "label": f"Fill missing '{col}' with mode",
                "description": f"Impute nulls in '{col}' using the most frequent value.",
                "action_type": "fill_na_mode",
                "params": {"column": col, "strategy": "mode"},
                "related_issues": [issue_id],
                "priority": 41,
            }
        ]
    
    if category == "cardinality" and columns:
        col = columns[0]
    
        return [
            {
                "id": f"drop_duplicate_records_by_{col}",
                "label": f"Remove duplicate records based on '{col}'",
                "description": (
                    f"Keep only the first row for each repeated value of '{col}'. "
                    "Use only if this column should uniquely identify one observation; "
                    "do not use for repeated visits, time series data, etc."
                ),
                    "action_type": "drop_duplicates_ID",
                    "params": {"subset": [col], "keep": "first"},
                    "related_issues": [issue_id],
                    "priority": 25,
            }
        ]

    if issue_id.startswith("empty_column_") and columns:
        col = columns[0]
        return [
            {
                "id": f"drop_column_{col}",
                "label": f"Drop empty column '{col}'",
                "description": f"Remove column '{col}' because it has no data.",
                "action_type": "drop_columns",
                "params": {"columns": [col]},
                "related_issues": [issue_id],
                "priority": 5,
            }
        ]

    if issue_id.startswith("whitespace_") and columns:
        col = columns[0]
        return [
            {
                "id": f"strip_whitespace_{col}",
                "label": f"Strip whitespace in '{col}'",
                "description": f"Trim leading and trailing spaces in '{col}'.",
                "action_type": "strip_whitespace",
                "params": {"column": col},
                "related_issues": [issue_id],
                "priority": 20,
            }
        ]

    if issue_id.startswith("case_inconsistent_") and columns:
        col = columns[0]
        return [
            {
                "id": f"normalize_case_{col}",
                "label": f"Normalize case in '{col}'",
                "description": f"Convert '{col}' to title case for consistent labels.",
                "action_type": "normalize_case",
                "params": {"column": col, "case": "title"},
                "related_issues": [issue_id],
                "priority": 25,
                "default_selected": True,
            }
        ]

    if issue_id.startswith("fuzzy") and columns:
        col = columns[0]
        mapping = issue.get("mapping", {})

        examples = ", ".join(
        f"{source} → {target}"
        for source, target in list(mapping.items())[:3]
        )

        return [
            {
                "id": f"merge_values_{col}",
                "label": f"Combine similar values in '{col}'",
                "description": (
                    f"Apply {len(mapping)} suggested '{col}' mergers ",
                    f"eg {(examples)}"
                ),
                "action_type": "merge_values",
                "params": {"column": col, "mapping": mapping},
                "related_issues": [issue_id],
                "priority": 25
            }
        ]

    if issue_id.startswith("outliers_") and columns:
        col = columns[0]
        return [
            {
                "id": f"clip_outliers_{col}",
                "label": f"Clip outliers in '{col}' (IQR)",
                "description": f"Winsorize '{col}' to 1.5×IQR fence bounds.",
                "action_type": "clip_outliers",
                "params": {"column": col},
                "related_issues": [issue_id],
                "priority": 50,
                "enabled": pd.api.types.is_numeric_dtype(df[col]),
            }
        ]

    if issue_id.startswith("constant_") and columns:
        col = columns[0]
        return [
            {
                "id": f"drop_constant_{col}",
                "label": f"Drop constant column '{col}'",
                "description": f"Remove '{col}' because it adds no variation.",
                "action_type": "drop_columns",
                "params": {"columns": [col]},
                "related_issues": [issue_id],
                "priority": 60,
            }
        ]

    return []


def _prioritize(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(actions, key=lambda a: a.get("priority", 99))


def filter_enabled(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [a for a in actions if a.get("enabled", True)]
