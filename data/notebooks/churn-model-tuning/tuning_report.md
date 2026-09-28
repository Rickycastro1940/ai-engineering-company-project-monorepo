# StreamLoop churn model — tuning report

## Metric choice

Primary search metric: **`recall`** on the churn (`Yes`) class.

StreamLoop's business priority is catching customers who will leave so retention can act. Missing a churner (false negative) is costlier than a false-positive outreach. Sklearn's default accuracy would over-reward the majority non-churn class (~73.5% of rows) and hide weak churn detection.

Reported metrics match the baseline suite: accuracy, precision, recall, F1, ROC-AUC.

## Search protocol (train only)

- Stratified 80/20 split **before** any model work.
- `RandomizedSearchCV` then narrowed `GridSearchCV` fit on **`X_train` only** (`n_jobs=1`, `refit=True`).
- Searches never see the test set or the full dataset.
- Test set touched **exactly twice**: baseline defaults, then final tuned model.

- Random search best CV recall: **0.7940**
- Grid search best mean CV recall: **0.8040** (face-value `best_params_`; see stability review below).

## Stability review (`cv_results_`)

Top GridSearchCV candidates by mean CV recall (with fold std):

| rank | mean recall | std | mean−std | max_depth | n_estimators | min_samples_leaf |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 0.8040 | 0.0244 | 0.7796 | 6 | 50 | 8 |
| 2 | 0.8040 | 0.0290 | 0.7750 | 6 | 50 | 4 |
| 3 | 0.8027 | 0.0329 | 0.7698 | 6 | 100 | 4 |
| 4 | 0.8020 | 0.0302 | 0.7718 | 6 | 200 | 4 |
| 5 | 0.8007 | 0.0325 | 0.7681 | 6 | 200 | 8 |

### Final model choice

Highest mean CV recall (0.8040 ± 0.0244). No nearby candidate offered a clear stability gain for a small mean trade-off.

### Final hyperparameters

```json
{
  "model__bootstrap": true,
  "model__class_weight": "balanced",
  "model__criterion": "log_loss",
  "model__max_depth": 6,
  "model__max_features": "log2",
  "model__min_samples_leaf": 8,
  "model__min_samples_split": 10,
  "model__n_estimators": 50
}
```

## Baseline vs tuned (held-out test, scored once each)

| Metric | Baseline (defaults) | Tuned final | Δ |
| --- | ---: | ---: | ---: |
| accuracy | 0.7779 | 0.7367 | -0.0412 |
| precision | 0.6034 | 0.5025 | -0.1009 |
| recall | 0.4759 | 0.7995 | +0.3235 |
| f1 | 0.5321 | 0.6171 | +0.0850 |
| roc_auc | 0.8170 | 0.8389 | +0.0220 |

## Takeaway

Tuning for **recall** lifted churn catch-rate on the holdout from **0.476** to **0.799**, with the expected precision trade-off from `class_weight='balanced'` and shallower trees. Accuracy alone would have preferred the baseline; that is why it was not the search objective.
