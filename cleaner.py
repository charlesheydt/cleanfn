"""Apply approved cleaning actions to a dataframe."""

from __future__ import annotations

from copy import deepcopy
from typing import Any
from statistics import multimode

import pandas as pd
import numpy as np
import random


def apply_actions(df: pd.DataFrame, actions: list[dict[str, Any]]) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """
    Apply a list of cleaning actions in order.

    Returns the cleaned dataframe and a log of applied steps with row/column deltas.
    """
    result = df.copy()
    log: list[dict[str, Any]] = []

    for action in actions:
        before_shape = result.shape
        result = _apply_single(result, action)
        after_shape = result.shape
        log.append(
            {
                "action_id": action["id"],
                "action_type": action["action_type"],
                "label": action.get("label", action["id"]),
                "params": deepcopy(action.get("params", {})),
                "rows_before": before_shape[0],
                "rows_after": after_shape[0],
                "cols_before": before_shape[1],
                "cols_after": after_shape[1],
            }
        )

    return result, log


def _apply_single(df: pd.DataFrame, action: dict[str, Any]) -> pd.DataFrame:
    action_type = action["action_type"]
    params = action.get("params", {})

    if action_type in ["drop_duplicates_row", "drop_duplicates_ID"]:
        subset = params.get("subset")
        keep = params.get("keep", "first")
        return df.drop_duplicates(subset=subset, keep=keep).reset_index(drop=True)

    if action_type == "drop_na":
        return df.dropna(subset=params.get("subset"), how=params.get("how", "any")).reset_index(drop=True)

    if action_type == "fill_na":
        col = params["column"]
        strategy = params.get("strategy", "mode")
        out = df.copy()
        if strategy == "median":
            out[col] = out[col].fillna(out[col].median())
        elif strategy == "mean":
            out[col] = out[col].fillna(out[col].mean())
        elif strategy == "mode":
            mode_vals = out[col].mode(dropna=True)
            if len(mode_vals):
                out[col] = out[col].fillna(mode_vals.iloc[0])
        elif strategy == "stochastic":
            missing_mask = out[col].isna()
            
            observed = out.loc[~missing_mask, col]

            out.loc[missing_mask, col] = observed.sample(
                n = missing_mask.sum(),
                replace = True,
                random_state = 12309
            ).values

        return out


    if action_type == "drop_columns":
        cols = [c for c in params.get("columns", []) if c in df.columns]
        return df.drop(columns=cols)

    if action_type == "strip_whitespace":
        col = params["column"]
        out = df.copy()
        out[col] = out[col].astype(str).str.strip()
        out.loc[df[col].isna(), col] = pd.NA
        return out

    if action_type == "normalize_case":
        col = params["column"]
        case = params.get("case", "title")
        out = df.copy()
        s = out[col].astype(str)
        if case == "lower":
            out[col] = s.str.lower()
        elif case == "upper":
            out[col] = s.str.upper()
        else:
            out[col] = s.str.title()
        out.loc[df[col].isna(), col] = pd.NA
        return out

    if action_type == "clip_outliers":
        col = params["column"]
        out = df.copy()
        valid = out[col].dropna()
        if len(valid) == 0:
            return out
        q1, q3 = valid.quantile(0.25), valid.quantile(0.75)
        iqr = q3 - q1
        lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        out[col] = out[col].clip(lower=lower, upper=upper)
        return out

    if action_type in ["merge_values", "custom_mapping"]:
        col = params["column"]
        mapping = params["mapping"]
        out = df.copy()
        normalized_mapping = {
            str(k).strip().casefold():v
            for k,v in mapping.items()
        }

        out[col] = (
            out[col].apply(lambda x: x if pd.isna(x) 
            else normalized_mapping.get(str(x).strip().casefold(),x))
        )
        return out

    if action_type == "custom_bounds":
        col = params["column"]
        lower_bound = params["lower_bound"]
        lower_bound = float(lower_bound)
        upper_bound = params["upper_bound"]
        upper_bound = float(upper_bound)
        selected_action = params["selected_action"]
        out = df.copy()

        bad_set = []
        for i in out.index:
            if out.loc[i, col] < lower_bound or out.loc[i, col] > upper_bound:
                bad_set.append(i)

        valid_indices = [i for i in df.index if i not in bad_set]
        valid_datapoints = [out.loc[i, col] for i in valid_indices]

        modes = multimode(valid_datapoints)
        empt = len(modes) == 0
        replacement = random.choice(modes)
        mean_val = df.loc[valid_indices, col].mean()
        mode_val = replacement if not empt else np.nan
        median_val = df.loc[valid_indices, col].median()

        if selected_action == "Impute Mean":
            for i in bad_set:
                out.loc[i, col] = mean_val

        elif selected_action == "Impute Median":
            for i in bad_set:
                out.loc[i, col] = median_val

        elif selected_action == "Impute Mode":
            for i in bad_set:
                out.loc[i, col] = mode_val

        elif selected_action == "Impute Stochastically":
            out.loc[bad_set, col] = np.nan
            missing_mask = out[col].isna()
            
            observed = out.loc[~missing_mask, col]

            out.loc[missing_mask, col] = observed.sample(
                n = missing_mask.sum(),
                replace = True,
                random_state = 12309
            ).values

        elif selected_action == "Convert to Null Values":
            out.loc[bad_set, col] = np.nan

        elif selected_action == "Drop Rows Outside of Range":
            drop_positions = list(bad_set)

            keep_mask = np.ones(len(out), dtype=bool)
            keep_mask[drop_positions] = False

            out = out.iloc[keep_mask].reset_index(drop=True)
            
        return out
     

    raise ValueError(f"Unknown action type: {action_type}")
