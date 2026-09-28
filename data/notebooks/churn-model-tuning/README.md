# StreamLoop — Tuning the Churn Model

Customer churn notebook for **StreamLoop**, using the public IBM Telco Customer Churn dataset as the assignment stand-in (account, service, and billing attributes; target `Churn`).

This lives under `data/notebooks/` inside the Brasaland monorepo so the work stays on the existing Git remote (no separate fork of `4GeeksAcademy/python-hello` required in this environment).

## Data

Loaded **directly from URL** (no manual download):

`https://raw.githubusercontent.com/IBM/telco-customer-churn-on-icp4d/master/data/Telco-Customer-Churn.csv`

- Target: `Churn` (`Yes` / `No`)
- Features: demographics, services, contract, billing

## Setup

```bash
cd data/notebooks/churn-model-tuning
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

**Headless verification** (recommended for CI / agents):

```bash
source .venv/bin/activate
python run_churn_tuning.py
```

**Interactive notebook:**

```bash
source .venv/bin/activate
jupyter notebook streamloop_churn_tuning.ipynb
```

## What the notebook does

1. Load the CSV from the public URL into pandas
2. Clean `TotalCharges`, encode `Churn`, drop `customerID`
3. Stratified train/test split
4. Baseline `RandomForestClassifier` inside a preprocessing `Pipeline`
5. Hyperparameter tuning with `RandomizedSearchCV` (5-fold stratified CV)
6. Compare baseline vs tuned metrics (accuracy, precision, recall, F1, ROC-AUC)
