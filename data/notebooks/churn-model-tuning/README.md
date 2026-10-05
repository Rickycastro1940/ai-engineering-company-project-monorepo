# StreamLoop — Tuning the Churn Model

Customer churn notebook for **StreamLoop**, using the public IBM Telco Customer Churn dataset as the assignment stand-in (account, service, and billing attributes; target `Churn`).

## Assignment flow (grader checklist)

1. **Load** the CSV from URL (no manual download)
2. **Minimal cleaning** — blank/`TotalCharges` → NaN, encode target, drop `customerID`
3. **Train/test split** before any model work
4. **Pipeline** = imputer + `StandardScaler` + one-hot + classifier (**all inside**; nothing fit before split)
5. **Baseline** — sklearn defaults; score the test set once **before** search
6. **Search** (train folds only, `n_jobs=1`, `refit=True`):
   - `RandomizedSearchCV` over supported hyperparameters
   - Narrow the space from those results
   - `GridSearchCV` to refine
7. **Inspect** `cv_results_` top candidates (mean vs fold std); pick final model
8. **Scoring:** `roc_auc` (rank churn risk for retention — not accuracy)
9. **Final** test score once at the end; write the tuning report with the trade-off

Searches never see the test set or the full dataset. Test is touched exactly twice.

## Primary deliverable (4Geeks / python-hello)

| Path | Role |
| --- | --- |
| `streamloop_churn_eda_pipeline_fix.ipynb` | Fixed EDA + tuning notebook (Pipeline + ROC-AUC + CV stability) |
| `tuning_report_eda_pipeline.md` | Metric choice, stability review, baseline vs tuned trade-off |
| `python-hello-update/` | Ready files + script to push onto `Rickycastro1940/python-hello` main |

See `STREAMLOOP.md` for the fork apply steps.

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
jupyter nbconvert --to notebook --execute --inplace streamloop_churn_eda_pipeline_fix.ipynb
# alternate RF/recall Protocol:
python run_churn_tuning.py
```
