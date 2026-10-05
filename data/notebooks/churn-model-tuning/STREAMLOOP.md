# StreamLoop — Tuning the Churn Model

4Geeks deliverable for **StreamLoop** customer churn tuning.

Template: [4GeeksAcademy/python-hello](https://github.com/4GeeksAcademy/python-hello)  
Submission fork: [Rickycastro1940/python-hello](https://github.com/Rickycastro1940/python-hello)

## Setup (matches the assignment)

```bash
# 1. Use this GitHub repository (already created from the python-hello template)
git clone https://github.com/Rickycastro1940/python-hello.git
cd python-hello

# 2. Install required libraries (scikit-learn and pandas at minimum)
python3 -m venv .venv
source .venv/bin/activate
pip install -r notebooks/churn-requirements.txt
# or: pip install pandas scikit-learn matplotlib seaborn scipy jupyter

# 3. Start the notebook
jupyter notebook notebooks/streamloop_churn_eda.ipynb
```

## What the notebook does (grader checklist)

1. Load IBM Telco Customer Churn CSV from URL (StreamLoop stand-in)
2. Minimal cleaning only (blank → NaN, encode target, drop `customerID`)
3. Stratified train/test split **before** any model work
4. One sklearn `Pipeline`: numeric imputer → `StandardScaler`; categorical imputer → `OneHotEncoder`; then classifier
5. Default baseline logged on the test set **before** search
6. `RandomizedSearchCV` → narrowed `GridSearchCV` on **train only** (`scoring=roc_auc`, `n_jobs=1`)
7. Inspect `cv_results_` mean **and** fold std; justify the final model
8. Final test score once; write `tuning_report.md` with the trade-off

## Apply the fix to `python-hello` main

Cloud Agent cannot push `Rickycastro1940/python-hello` (403). From this monorepo:

```bash
bash data/notebooks/churn-model-tuning/python-hello-update/update-python-hello-main.sh
```

## Anti-patterns avoided

- One-hot / scaler fit before the split — **no** (inside Pipeline only)
- Search seeing the test set — **no**
- Face-value `best_params_` without `cv_results_` mean/std review — **no**
- Missing final-model trade-off in the report — **no**
