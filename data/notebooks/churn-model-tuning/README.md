# StreamLoop — Tuning the Churn Model

Customer churn notebook for **StreamLoop**, using the public IBM Telco Customer Churn dataset as the assignment stand-in (account, service, and billing attributes; target `Churn`).

## Assignment flow

1. **Load** the CSV from URL (no manual download)
2. **Minimal cleaning** — blank/`TotalCharges` → NaN, encode target, drop `customerID`
3. **Train/test split** before any model work
4. **Pipeline** = impute + one-hot + classifier (**preprocessing inside the pipeline**)
5. **Baseline** — sklearn default hyperparameters; score the test set once
6. **Tune** on training folds only (`RandomizedSearchCV`)
7. **Final** test score only at the end

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

Artifacts: `baseline_metrics.json`, `tuning_metrics.json`.
