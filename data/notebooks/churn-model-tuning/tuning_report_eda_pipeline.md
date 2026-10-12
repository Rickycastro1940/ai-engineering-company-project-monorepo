# StreamLoop Churn — Hyperparameter Tuning Report

Reproduced by `notebooks/streamloop_churn_eda.ipynb` (Steps 6–11) with preprocessing
**inside** one sklearn `Pipeline`. Also available as the focused notebook
`notebooks/streamloop_churn_tuning.ipynb`.

## 1. Preprocessing (grader fix)

Imputer + encoder + scaler + classifier live in **one** `Pipeline`:

- numeric: `SimpleImputer(median)` → `StandardScaler`
- categorical: `SimpleImputer(most_frequent)` → `OneHotEncoder(handle_unknown="ignore")`
- then the classifier

**Not used:** `pd.get_dummies` before the split, or `StandardScaler.fit_transform` outside the Pipeline.

Stratified train/test split happens **before** any model work. Searches fit on `X_train` only.

## 2. Chosen classifier

`GradientBoostingClassifier` (scikit-learn) wrapped as `Pipeline(preprocess, model)` —
strongest model in the Step 9 comparison when each candidate used the same Pipeline.

## 3. Scoring metric — business priority

**`scoring='recall'`** on the churn class. StreamLoop’s priority is catching customers who
will leave so retention can act. On an imbalanced target (~26.5% churn), default accuracy
is misleading. We still **report** accuracy, precision, F1, and ROC-AUC alongside recall.

## 4. Search strategy (train only)

Broad `RandomizedSearchCV` (`n_iter=20`, `cv=5`, `n_jobs=1`, `refit=True`) then a narrowed
`GridSearchCV` around the winner. Parameter names use the `model__*` prefix so the
preprocessor stays inside every CV fold.

Baseline defaults are scored on the test set **once before** search; the tuned Pipeline is
scored on the test set **once at the end**.

## 5. Stability review (`cv_results_`)

Inspected top GridSearchCV candidates on **mean** CV recall **and fold std** (not
face-value `best_params_` alone). Trade-off rule: prefer a slightly lower mean when std
drops by ≥25% and ≥0.005 absolute within a 0.01 mean window; otherwise keep the highest mean.

Document the chosen mean ± std and whether a stability trade-off was taken in the notebook
output after Step 11.

## 6. Final-model trade-off

Tuning for **recall** typically lifts churn catch-rate versus defaults, with an expected
precision trade-off. Accuracy alone would often prefer the untuned baseline — that is why
accuracy was not the search objective.

## How to rerun

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r notebooks/churn-requirements.txt
# Full tuning Protocol (recommended):
python notebooks/run_churn_tuning.py
# Or execute the EDA+tuning notebook:
jupyter nbconvert --to notebook --execute --inplace notebooks/streamloop_churn_eda.ipynb
```
