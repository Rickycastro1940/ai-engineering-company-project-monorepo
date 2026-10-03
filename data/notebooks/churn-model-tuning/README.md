# StreamLoop — Tuning the Churn Model

Customer churn notebook for **StreamLoop**, using the public IBM Telco Customer Churn dataset as the assignment stand-in (account, service, and billing attributes; target `Churn`).

## Assignment flow

1. **Load** the CSV from URL (no manual download)
2. **Minimal cleaning** — blank/`TotalCharges` → NaN, encode target, drop `customerID`
3. **Train/test split** before any model work
4. **Pipeline** = imputer + `StandardScaler` + one-hot + classifier (**all inside**; nothing fit before split)
5. **Baseline** — sklearn defaults; score the test set once
6. **Search** (train folds only, `n_jobs=1`, `refit=True`):
   - `RandomizedSearchCV` over RF-supported hyperparameters
   - Narrow the space from those results
   - `GridSearchCV` to refine
7. **Inspect** `cv_results_` top candidates (mean vs fold std); pick final model
8. **Scoring:** `recall` (catch churners for retention — not accuracy)
9. **Final** test score once at the end; write `tuning_report.md`

Searches never see the test set or the full dataset. Test is touched exactly twice.

## Data

`https://raw.githubusercontent.com/IBM/telco-customer-churn-on-icp4d/master/data/Telco-Customer-Churn.csv`

## Setup

```bash
cd data/notebooks/churn-model-tuning
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
source .venv/bin/activate
python run_churn_tuning.py
# or
jupyter notebook streamloop_churn_tuning.ipynb
```

Artifacts: `baseline_metrics.json`, `tuning_metrics.json`, `cv_top_candidates.json`, `tuning_report.md`.
