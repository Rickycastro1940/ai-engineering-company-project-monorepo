# StreamLoop — Tuning the Churn Model

4Geeks deliverable for **StreamLoop** customer churn tuning.

Template: [4GeeksAcademy/python-hello](https://github.com/4GeeksAcademy/python-hello)  
This repo: fork of that template with the completed notebook.

## Setup (matches the assignment)

```bash
# 1. Use this GitHub repository (already created from the python-hello template)
git clone https://github.com/Rickycastro1940/python-hello.git
cd python-hello

# 2. Install required libraries (scikit-learn and pandas at minimum)
python3 -m venv .venv
source .venv/bin/activate
pip install -r notebooks/churn-requirements.txt
# or: pip install pandas scikit-learn matplotlib seaborn jupyter

# 3. Start the notebook
jupyter notebook notebooks/streamloop_churn_tuning.ipynb
```

Headless rerun (same Protocol as the notebook):

```bash
source .venv/bin/activate
python notebooks/run_churn_tuning.py
```

## What the notebook does

1. Load IBM Telco Customer Churn CSV from URL (StreamLoop stand-in)
2. Minimal cleaning only (blank → NaN, encode target, drop `customerID`)
3. Stratified train/test split **before** any model work
4. One sklearn `Pipeline`: numeric imputer → `StandardScaler`; categorical imputer → `OneHotEncoder`; then classifier
5. Default baseline; score the test set once
6. `RandomizedSearchCV` → narrowed `GridSearchCV` on **train only** (`scoring=recall`, `n_jobs=1`)
7. Inspect `cv_results_` mean **and** fold std; justify the final model
8. Final test score once; write `tuning_report.md`

## Key files

| Path | Role |
| --- | --- |
| `notebooks/streamloop_churn_tuning.ipynb` | **Primary deliverable** |
| `notebooks/run_churn_tuning.py` | Headless reproduction |
| `tuning_report.md` | Metric choice, stability review, baseline vs tuned |
| `notebooks/streamloop_churn_eda.ipynb` | Earlier EDA (kept for history) |

## Anti-patterns avoided

- One-hot / scaler fit before the split — **no** (inside Pipeline only)
- Search seeing the test set — **no**
- Test set scored more than twice — **no** (baseline + final)
