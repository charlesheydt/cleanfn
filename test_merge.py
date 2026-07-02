import pandas as pd
from diagnostics import run_diagnostics
from recommender import recommend_actions
from cleaner import apply_actions

print("TEST FILE STARTED")
df = pd.read_csv("messy_hiv_data.csv")

issues = run_diagnostics(df)
recommendations = recommend_actions(df, issues)

print("Recommendations:")
for r in recommendations:
    print(r["label"])

approved_actions = [
    r for r in recommendations
    if r["action_type"] == "merge_values"
]

cleaned_df = apply_actions(df, approved_actions)

print(cleaned_df.head())