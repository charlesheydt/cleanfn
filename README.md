# CleanFN: The CSV Data Cleaning Assistant

CleanFN is a Streamlti app that profiles uploaded CSVs, identifies data quality issues, and recommends cleaning actions. Once the cleaning actions are recommend, you can approve actions of your choice and preview/download both the cleaned CSV and a reproducible python script.

## Project structure


| Module           | Role                                                 |
| ---------------- | ---------------------------------------------------- |
| `app.py`         | Streamlit UI: upload, report, approve, apply, export |
| `profiler.py`    | Dataset summary (shape, nulls, dtypes, stats)        |
| `diagnostics.py` | Data quality issue detection                         |
| `recommender.py` | Converts issues to cleaning actions                  |
| `cleaner.py`     | Applies approved actions to a DataFrame              |
| `codegen.py`     | Generates a reproducible python script               |


## Setup

```bash
cd csv-cleaning-assistant
python -m venv .venv
source .venv/bin/activate   # for windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Run

```bash
streamlit run app.py
```

## Workflow

1. Upload a CSV.
2. Review the quality report (profile + diagnostics).
3. Open "clean & export", check recommended actions, and click "apply selected actions".
4. Download the cleaned CSV and/or the generated Python script.

## The Quality Report

-When you upload your CSV, you will see a list of all rows and various summary statistics such as mean, median (numerical columns), percent missing and others. 

## Supported cleaning actions


| Action                | Purpose                                              |
| --------------------- | ---------------------------------------------------- |
| Remove Duplicate Rows | Streamlit UI: upload, report, approve, apply, export |
| `profiler.py`         | Dataset summary (shape, nulls, dtypes, stats)        |
| `diagnostics.py`      | Data quality issue detection                         |
| `recommender.py`      | Converts issues to cleaning actions                  |
| `cleaner.py`          | Applies approved actions to a DataFrame              |
| `codegen.py`          | Generates a reproducible python script               |


- Remove duplicate rows
- Drop rows with missing values (per column)
- Fill missing values: Can be done with mode, median or stochastic imputation. 
- Drop empty or constant columns
- Strip whitespace
- Normalize text case
- Clip numeric outliers (data that falls 1.5 IQR above the 3rd quartile or 1.5 IQR below the first quartile will be clipped)
- Custom value mappings: Normalize values within columns by replacing inconsistent/incorrect/incomplete values with values of your choice
- Custom bounds for numerical values: For collected data that does not seem feasible, the user has the option to replace,
drop, or ignore all data outside of a user-specified range. To replace, you may choose among mean, median, mode, and stochastic imputation.

