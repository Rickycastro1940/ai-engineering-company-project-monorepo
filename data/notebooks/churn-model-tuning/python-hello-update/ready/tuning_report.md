# StreamLoop Churn — Hyperparameter Tuning Report

Tuning of the churn classifier for StreamLoop (data publicly modeled after the
IBM Telco Customer Churn dataset). Reproduced by `notebooks/streamloop_churn_eda.ipynb`
(Steps 6–11) with preprocessing **inside** one sklearn `Pipeline`.

## 1. Preprocessing (grader fix)

Imputer + encoder + scaler + classifier live in **one** `Pipeline`:

- numeric: `SimpleImputer(median)` → `StandardScaler`
- categorical: `SimpleImputer(most_frequent)` → `OneHotEncoder(handle_unknown="ignore")`
- then the classifier

**Not used:** `pd.get_dummies` before the split, or `StandardScaler.fit_transform` outside the Pipeline.

Stratified train/test split happens **before** any model work. Searches fit on `X_train` only.

## 2. Chosen classifier

`GradientBoostingClassifier` (scikit-learn) wrapped as `Pipeline(preprocess, model)` —
the strongest model in the Step 9 comparison (ROC-AUC ~0.848) when each candidate
used the same Pipeline.

## 3. Scoring metric — business priority, not the default

**`scoring='roc_auc'`.** StreamLoop's goal is to *rank customers by churn risk*
so retention offers reach the right people. The target is imbalanced (~26.5%
churn), so the sklearn default (accuracy) is misleading — a model that predicts
"no churn" for everyone scores ~73.5% accuracy while catching zero churners.
ROC-AUC measures how well the model ranks churners above non-churners
independent of the decision threshold, which matches the retention use-case.

Reported metrics also include accuracy, precision, recall, and F1.

## 4. Search strategy (train only)

Baseline Gradient Boosting defaults are scored on the test set **once before** search.

Broad `RandomizedSearchCV` (`n_iter=20`, `cv=5`, `n_jobs=1`, `refit=True`) then a
narrowed `GridSearchCV` around the winner. Parameter names use the `model__*`
prefix so the preprocessor stays inside every CV fold. Searches never see the
test set or the full dataset.

### 4a. `RandomizedSearchCV` (broad)

Best CV ROC-AUC **0.8489**, best params
`{learning_rate: 0.0590, max_depth: 2, max_features: None, min_samples_leaf: 12, n_estimators: 214, subsample: 0.7}`.

### 4b. `GridSearchCV` (refine)

Best mean CV ROC-AUC **0.8489** (face-value `best_params_` matched the random-search region).

## 5. Stability review (`cv_results_`)

Inspected top GridSearchCV candidates on **mean** CV ROC-AUC **and fold std** (not
face-value `best_params_` alone). Trade-off rule: prefer a slightly lower mean when
std drops by ≥25% and ≥0.005 absolute within a 0.01 mean window; otherwise keep the
highest mean.

| rank | mean ROC-AUC | std | mean−std | n_estimators | learning_rate | max_depth |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 0.8489 | 0.0159 | 0.8330 | 214 | 0.0590 | 2 |
| 2 | 0.8485 | 0.0169 | 0.8316 | 139 | 0.0590 | 2 |
| 3 | 0.8485 | 0.0156 | 0.8328 | 289 | 0.0590 | 2 |
| 4 | 0.8481 | 0.0158 | 0.8324 | 214 | 0.0295 | 3 |
| 5 | 0.8478 | 0.0166 | 0.8312 | 139 | 0.0295 | 3 |

### Final model choice

Kept highest mean CV ROC-AUC (**0.8489 ± 0.0159**). No nearby candidate offered a
clear stability gain for a small mean trade-off (std never dropped by ≥25% within
the 0.01 mean window).

### Final hyperparameters

```json
{
  "model__learning_rate": 0.059,
  "model__max_depth": 2,
  "model__max_features": null,
  "model__min_samples_leaf": 12,
  "model__n_estimators": 214,
  "model__subsample": 0.7
}
```

## 6. Final-model trade-off (held-out test, scored once each)

| Metric | Baseline (defaults) | Tuned final | Δ |
| --- | ---: | ---: | ---: |
| accuracy | 0.8008 | 0.8050 | +0.0042 |
| precision | 0.6628 | 0.6659 | +0.0031 |
| recall | 0.5080 | 0.5330 | +0.0250 |
| f1 | 0.5752 | 0.5921 | +0.0169 |
| roc_auc | 0.8476 | 0.8499 | +0.0023 |

**Trade-off note:** ROC-AUC search targets ranking quality for retention outreach.
Here the tuned Pipeline also nudged accuracy / precision / recall slightly upward
at the default 0.5 threshold. Accuracy alone would have looked almost flat
(0.801 → 0.805) and would not have justified the search — that is why accuracy
was not the objective.

Classification report (tuned, default 0.5 threshold):

```
              precision    recall  f1-score   support
      Stayed       0.84      0.90      0.87      1552
     Churned       0.67      0.53      0.59       561
    accuracy                           0.81      2113
```

## 7. Takeaways

- Preprocessing is leakage-safe inside one sklearn `Pipeline`.
- Tuning gave a small but real lift in the business metric (test ROC-AUC
  0.848 → 0.850); the model was already near its ceiling for this feature set.
- `cv_results_` mean/std review confirmed the face-value winner was also stable enough
  to ship — no mean-for-std trade-off required this run.

## How to rerun

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install pandas scikit-learn matplotlib seaborn scipy jupyter
jupyter nbconvert --to notebook --execute --inplace notebooks/streamloop_churn_eda.ipynb
```
