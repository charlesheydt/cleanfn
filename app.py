from __future__ import annotations

import io
from datetime import datetime

import pandas as pd
import streamlit as st

from cleaner import apply_actions
from codegen import generate_script
from diagnostics import run_diagnostics, sort_issues
from profiler import profile_dataframe
from recommender import filter_enabled, recommend_actions
from collections import defaultdict

st.set_page_config(
    page_title="CleanFN",
    page_icon="🧹",
    layout="wide",
)

SEVERITY_COLORS = {
    "critical": "#b91c1c",
    "high": "#c2410c",
    "medium": "#ca8a04",
    "low": "#2563eb",
}


def init_session_state() -> None:
    defaults = {
        "raw_df": None,
        "cleaned_df": None,
        "filename": None,
        "profile": None,
        "issues": [],
        "recommendations": [],
        "approved_ids": set(),
        "apply_log": [],
        "script": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def load_csv(uploaded_file) -> pd.DataFrame:
    return pd.read_csv(uploaded_file)


def render_quality_report(profile: dict, issues: list[dict]) -> None:
    st.subheader("Data quality report")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Rows", f"{profile['n_rows']:,}")
    c2.metric("Columns", profile["n_cols"])
    c3.metric("Duplicate rows", f"{profile['duplicate_rows']:,}", f"{profile['duplicate_pct']}%")
    c4.metric("Memory", f"{profile['memory_mb']} MB")

    if profile["completely_empty_cols"]:
        st.warning(f"Empty columns: {', '.join(profile['completely_empty_cols'])}")

    st.markdown("#### Column profile")
    col_df = pd.DataFrame(profile["columns"])
    display_cols = ["name", "dtype", "null_count", "null_pct", "unique_count"]
    extra = [c for c in col_df.columns if c not in display_cols and c != "is_numeric"]
    st.dataframe(col_df[display_cols + extra], use_container_width=True, hide_index=True)

    st.markdown("#### Diagnostics")
    if not issues:
        st.success("No data quality issues detected.")
        return

    unique_descriptors = st.session_state.profile["unique_descriptors"]

    print(st.session_state.profile)

    if unique_descriptors:
    
        records = []

        for col_name, entries in unique_descriptors.items():
            records.append({
                "name": col_name,
                "entries": ", ".join(sorted(str(x) for x in entries))
            })

        dataf = pd.DataFrame(records)
        st.dataframe(dataf)

    for issue in issues:
        color = SEVERITY_COLORS.get(issue["severity"], "#64748b")
        st.markdown(
            f'<span style="color:{color};font-weight:600">[{issue["severity"].upper()}]</span> '
            f'**{issue["category"]}** — {issue["message"]}',
            unsafe_allow_html=True,
        )



def render_recommendations(recommendations: list[dict], group_name: str) -> set[str]:
    st.subheader("Recommended cleaning actions")
    st.caption("Recommended low-risk cleaning actions are selected by default")
    groups = {
        "Formatting": ["strip_whitespace", "normalize_case", "merge_values",
        "custom_mapping"],
        "Missing Values": ["drop_na", "fill_na"],
        "Outliers": ["clip_outliers", "custom_bounds"],
        "Duplicates": ["drop_duplicates_ID", "drop_duplicates_row"],
    }

    action_types = groups[group_name]

    group_recs = [
        rec for rec in recommendations
        if rec["action_type"] in action_types
    ]

    approved = set(st.session_state.approved_ids)

    for rec in group_recs:
        checked = st.checkbox(
            f"**{rec['label']}** — {rec['description']}",
            value=rec["id"] in approved,
            key=f"rec_{rec['id']}",
        )

        if checked:
            approved.add(rec["id"])
        else:
            approved.discard(rec["id"])

    st.session_state.approved_ids = approved
    return approved


def main() -> None:
    init_session_state()

    st.title("CleanFN")
    st.caption("Upload a CSV, review data quality, approve cleaning actions, and export results.")

    uploaded = st.file_uploader("Upload CSV", type=["csv"])

    if uploaded is not None:
        if st.session_state.filename != uploaded.name:
            df = load_csv(uploaded)
            st.session_state.raw_df = df
            st.session_state.cleaned_df = None
            st.session_state.filename = uploaded.name
            st.session_state.profile = profile_dataframe(df)
            st.session_state.issues = sort_issues(run_diagnostics(df, st.session_state.profile))
            st.session_state.recommendations = filter_enabled(
                recommend_actions(df, st.session_state.issues)
            )
            st.session_state.approved_ids = {
                r["id"] for r in st.session_state.recommendations
                if r.get("default_selected", False)

            }
            st.session_state.apply_log = []
            st.session_state.script = None

    df = st.session_state.raw_df
    if df is None:
        st.info("Upload a CSV file to begin.")
        with st.expander("Try with sample data"):
            st.code(
                "name,age,city,salary\n"
                " Alice ,25, NYC ,50000\n"
                "Bob,30,,60000\n"
                "Alice,25,NYC,50000\n"
                ",40,LA,70000\n"
                "Carol,35,LA,80000",
                language="csv",
            )
        return

    tab_report, tab_preview, tab_clean = st.tabs(["Quality report", "Data preview", "Clean & export"])

    with tab_report:
        render_quality_report(st.session_state.profile, st.session_state.issues)

    with tab_preview:
        st.subheader("Original data")
        st.dataframe(df.head(100), use_container_width=True)
        if len(df) > 100:
            st.caption(f"Showing first 100 of {len(df):,} rows.")


    with tab_clean:

        tab_formatting, tab_missing, tab_outliers, tab_duplicate = st.tabs(
            ["Formatting", "Missing Values", "Outliers", "Duplicates"]
        )

        with tab_formatting:

            approved_ids = render_recommendations(st.session_state.recommendations, "Formatting")
            approved_actions = [r for r in st.session_state.recommendations if r["id"] in approved_ids]

            with st.expander("Add custom value mapping"):

                map_col = st.selectbox("Column", df.columns)
                unique_values = sorted(df[map_col].dropna().astype(str).str.strip().unique())
                old_value = st.selectbox("Value to replace:", unique_values, key = "custom_old")
                new_value = st.text_input("Replace with", key = "custom new")

                if st.button("Add mapping"):
                    action = make_custom_mapping_action(map_col, old_value, new_value)
                    st.session_state.recommendations.append(action)
                    st.session_state.approved_ids.add(action["id"])
                    st.rerun()


        with tab_missing:
            approved_ids = render_recommendations(st.session_state.recommendations, "Missing Values")
            approved_actions = [r for r in st.session_state.recommendations if r["id"] in approved_ids]


        with tab_outliers:
            approved_ids = render_recommendations(st.session_state.recommendations, "Outliers")
            approved_actions = [r for r in st.session_state.recommendations if r["id"] in approved_ids]
            with st.expander("Add custom bounds"):
                num_cols = []
                for coll in df.columns:
                    if pd.api.types.is_numeric_dtype(df[coll]):
                            num_cols.append(coll)

                col = st.selectbox("Column", num_cols , key = "selected")
                lower_bound = st.text_input("Enter the lower bound for feasible datapoints")
                upper_bound = st.text_input("Enter the upper bound for feasible datapoints")
                selected_action = st.selectbox("Action for rows outside of bounds",
                            options = ["Impute Median", 
                                        "Impute Mean",
                                        "Impute Mode",
                                        "Impute Stochastically", 
                                        "Convert to Null Values", 
                                        "Drop Rows Outside of Range"]
                )

                if st.button("Add custom bounds"):
                    action = custom_bounds(col, lower_bound, upper_bound, selected_action)
                    st.session_state.recommendations.append(action)
                    st.session_state.approved_ids.add(action["id"])
                    st.rerun()

            conflicts = validate_recommendations(approved_actions)

            if conflicts:
                print("THERE IS A CONFLICT")
                for col, recs in conflicts:
                    actions = [r["params"]["selected_action"] for r in recs]
                    st.error(
                        f"Multiple custom bounds actions selected for `{col}`: "
                        f"{', '.join(actions)}. Choose only one. Otherwise, the first selected action will be prioritized."
                    )


        with tab_duplicate:
            approved_ids = render_recommendations(st.session_state.recommendations, "Duplicates")
            approved_actions = [r for r in st.session_state.recommendations if r["id"] in approved_ids]


        col_apply, col_reset = st.columns([1, 1])
        with col_apply:
            apply_clicked = st.button(
                "Apply selected actions",
                type="primary",
                disabled=len(approved_actions) == 0,
            )
        with col_reset:
            if st.button("Reset to original"):
                st.session_state.cleaned_df = None
                st.session_state.apply_log = []
                st.session_state.script = None
                st.rerun()


        if apply_clicked and approved_actions:
            cleaned, log = apply_actions(df, approved_actions)
            st.session_state.cleaned_df = cleaned
            st.session_state.apply_log = log
            st.session_state.script = generate_script(
                source_path=st.session_state.filename or "input.csv",
                output_path="cleaned_output.csv",
                actions=approved_actions,
                log=log,
            )
            st.success(f"Applied {len(log)} action(s). {len(df):,} → {len(cleaned):,} rows.")

        cleaned = st.session_state.cleaned_df
        if cleaned is not None:
            st.subheader("Cleaned preview")
            st.dataframe(cleaned.head(100), use_container_width=True)

            if st.session_state.apply_log:
                st.markdown("#### Applied steps")
                log_df = pd.DataFrame(st.session_state.apply_log)
                st.dataframe(
                    log_df[
                        ["label", "rows_before", "rows_after", "cols_before", "cols_after"]
                    ],
                    use_container_width=True,
                    hide_index=True,
                )

            st.subheader("Export")
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            base = (st.session_state.filename or "data").replace(".csv", "")

            csv_buf = io.StringIO()
            cleaned.to_csv(csv_buf, index=False)
            st.download_button(
                label="Download cleaned CSV",
                data=csv_buf.getvalue(),
                file_name=f"{base}_cleaned_{ts}.csv",
                mime="text/csv",
            )

            if st.session_state.script:
                st.download_button(
                    label="Download reproducible Python script",
                    data=st.session_state.script,
                    file_name=f"{base}_cleaning_script_{ts}.py",
                    mime="text/x-python",
                )
                with st.expander("Preview generated script"):
                    st.code(st.session_state.script, language="python")

        

def make_custom_mapping_action(map_col: str, old_value: str, new_value: str) -> dict:
    return {
        "id": f"custom_mapping_{map_col}_{old_value}_{new_value}",
        "label": f"Map '{old_value}' to '{new_value}' in '{map_col}'",
        "description": f"Replace '{old_value}' with '{new_value}' in column '{map_col}'",
        "action_type": "custom_mapping",
        "params": {
            "column": map_col,
            "mapping": {old_value: new_value}
        },
        "priority": 100,
    }

def custom_bounds(col, lower_bound: float, upper_bound: float, selected_action: str) -> dict:

    safe_action = selected_action.replace(" ", "_")
    safe_col = col.replace(" ", "_")

    return {
        "id": f"custom_bounds_{safe_col}_{lower_bound}_{upper_bound}_{safe_action}",
        "label": f"Restrict below '{lower_bound}' and above '{upper_bound}'",
        "description": f"Apply custom bounds in '{col}' for values that are unusual or not permitted using '{selected_action}'",
        "action_type": "custom_bounds",
        "params":{
            "column": col,
            "lower_bound": lower_bound,
            "upper_bound": upper_bound,
            "selected_action": selected_action
        },
        "priority": 100
    }

def validate_recommendations(recommendations):

    selected_by_column = defaultdict(list)

    for rec in recommendations:
        if rec["action_type"] != "custom_bounds":
            continue

        col = rec["params"]["column"]
        selected_by_column[col].append(rec)

    conflicts = []

    for col, recs in selected_by_column.items():
        if len(recs) > 1:
            conflicts.append((col, recs))

    return conflicts

    print("VALIDATING")

        

    

#when custom bounds is selected, we should add a selection menu that says:
#convert to null values, impute median, impute mode, impute mean, impute stochastically
#drop row

if __name__ == "__main__":
    main()
