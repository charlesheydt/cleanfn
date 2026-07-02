import pandas as pd
from diagnostics import identify_id_columns

df = pd.read_csv("messy_hiv_data.csv")
print(identify_id_columns(df))