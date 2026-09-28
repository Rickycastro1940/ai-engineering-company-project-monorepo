"""StreamLoop — Tuning the Churn Model (headless runner).

Assignment flow:
1. Load the public Telco churn CSV from URL
2. Minimal cleaning only (blank→NaN, target encoding, drop id)
3. Stratified train/test split *before* any model work
4. Pipeline = preprocessing (impute + encode) + classifier (defaults)
5. Fit on train; score the test set once for the baseline
6. RandomizedSearchCV (n_jobs=1) → narrow → GridSearchCV (n_jobs=1)
7. Scoring = recall (catch churners for retention); refit=True
8. Final holdout score only at the end — never manually refit best_estimator_
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import (
    GridSearchCV,
    RandomizedSearchCV,
    StratifiedKFold,
    train_test_split,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

DATA_URL = (
    "https://raw.githubusercontent.com/IBM/telco-customer-churn-on-icp4d/"
    "master/data/Telco-Customer-Churn.csv"
)
RANDOM_STATE = 42
OUT_DIR = Path(__file__).resolve().parent
METRICS_PATH = OUT_DIR / "tuning_metrics.json"
BASELINE_PATH = OUT_DIR / "baseline_metrics.json"

# Business priority: miss fewer churners so retention can act (not sklearn accuracy).
SCORING = "recall"

# Broad search over RandomForestClassifier knobs the model actually supports.
RANDOM_PARAM_DISTRIBUTIONS: dict[str, list[Any]] = {
    "model__n_estimators": [50, 100, 200, 300],
    "model__max_depth": [None, 6, 8, 12, 16, 20],
    "model__min_samples_split": [2, 5, 10, 20],
    "model__min_samples_leaf": [1, 2, 4, 8],
    "model__max_features": ["sqrt", "log2", None],
    "model__criterion": ["gini", "entropy", "log_loss"],
    "model__class_weight": [None, "balanced"],
    "model__bootstrap": [True, False],
}


def load_raw(url: str = DATA_URL) -> pd.DataFrame:
    return pd.read_csv(url)


def minimal_clean(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """Make the frame usable without learning from feature values.

    - Blank / non-numeric TotalCharges → NaN (imputed *inside* the pipeline)
    - Churn Yes/No → 0/1
    - Drop customerID (identifier, not a feature)
    Categorical encoding and numeric imputation stay in the sklearn Pipeline.
    """
    clean = df.copy()
    clean["TotalCharges"] = pd.to_numeric(clean["TotalCharges"], errors="coerce")
    obj_cols = clean.select_dtypes(include=["object", "string"]).columns
    for col in obj_cols:
        if col == "Churn":
            continue
        clean[col] = clean[col].replace(r"^\s*$", pd.NA, regex=True)

    y = (clean["Churn"] == "Yes").astype(int)
    X = clean.drop(columns=["Churn", "customerID"])
    return X, y


def feature_columns(X: pd.DataFrame) -> tuple[list[str], list[str]]:
    cat_cols = X.select_dtypes(include=["object", "string", "category"]).columns.tolist()
    num_cols = [c for c in X.columns if c not in cat_cols]
    return cat_cols, num_cols


def build_pipeline(X: pd.DataFrame, **model_kwargs) -> Pipeline:
    """Preprocessing lives inside the Pipeline — never fit on X_test beforehand."""
    cat_cols, num_cols = feature_columns(X)

    numeric = Pipeline(steps=[("imputer", SimpleImputer(strategy="median"))])
    categorical = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
        ]
    )
    preprocess = ColumnTransformer(
        transformers=[
            ("num", numeric, num_cols),
            ("cat", categorical, cat_cols),
        ]
    )
    model = RandomForestClassifier(random_state=RANDOM_STATE, **model_kwargs)
    return Pipeline(steps=[("preprocess", preprocess), ("model", model)])


def evaluate(pipe: Pipeline, X_test: pd.DataFrame, y_test: pd.Series) -> dict:
    y_pred = pipe.predict(X_test)
    y_proba = pipe.predict_proba(X_test)[:, 1]
    return {
        "accuracy": float(accuracy_score(y_test, y_pred)),
        "precision": float(precision_score(y_test, y_pred)),
        "recall": float(recall_score(y_test, y_pred)),
        "f1": float(f1_score(y_test, y_pred)),
        "roc_auc": float(roc_auc_score(y_test, y_proba)),
    }


def _neighbors_int(value: int, choices: list[int], k: int = 1) -> list[int]:
    ordered = sorted(choices)
    idx = ordered.index(value) if value in ordered else min(
        range(len(ordered)), key=lambda i: abs(ordered[i] - value)
    )
    lo = max(0, idx - k)
    hi = min(len(ordered), idx + k + 1)
    return ordered[lo:hi]


def narrow_param_grid(
    best_params: dict[str, Any],
    broad: dict[str, list[Any]] | None = None,
) -> dict[str, list[Any]]:
    """Shrink the RandomForest search space around RandomizedSearchCV winners.

    Lock categorical / discrete winners; vary a local neighborhood on the
    tree-complexity knobs that usually move recall most.
    """
    broad = broad or RANDOM_PARAM_DISTRIBUTIONS
    # Always pin these to the random-search winner.
    grid: dict[str, list[Any]] = {
        "model__criterion": [best_params["model__criterion"]],
        "model__class_weight": [best_params["model__class_weight"]],
        "model__bootstrap": [best_params["model__bootstrap"]],
        "model__max_features": [best_params["model__max_features"]],
        "model__min_samples_split": [best_params["model__min_samples_split"]],
    }

    depth_choices = [c for c in broad["model__max_depth"] if c is not None]
    best_depth = best_params["model__max_depth"]
    if best_depth is None:
        grid["model__max_depth"] = [None, depth_choices[-1]]
    else:
        grid["model__max_depth"] = _neighbors_int(int(best_depth), depth_choices, k=1)

    grid["model__n_estimators"] = _neighbors_int(
        int(best_params["model__n_estimators"]),
        [int(c) for c in broad["model__n_estimators"]],
        k=1,
    )
    grid["model__min_samples_leaf"] = _neighbors_int(
        int(best_params["model__min_samples_leaf"]),
        [int(c) for c in broad["model__min_samples_leaf"]],
        k=1,
    )
    return grid


def main() -> None:
    print("1) Load dataset from URL…")
    raw = load_raw()
    print(f"   shape={raw.shape}")

    print("2) Minimal cleaning (blanks→NaN, target encode, drop id)…")
    X, y = minimal_clean(raw)
    print(
        f"   features={X.shape[1]} churn_rate={y.mean():.3f} "
        f"TotalCharges_na={int(X['TotalCharges'].isna().sum())}"
    )

    print("3) Train/test split *before* any model work…")
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=RANDOM_STATE, stratify=y
    )
    print(f"   train={len(X_train)} test={len(X_test)}")

    print("4) Build pipeline (impute+encode inside) + default RandomForest…")
    baseline = build_pipeline(X_train)
    print("5) Fit on train; score test once → baseline…")
    baseline.fit(X_train, y_train)
    baseline_metrics = evaluate(baseline, X_test, y_test)
    print("   Baseline (test):", baseline_metrics)
    BASELINE_PATH.write_text(json.dumps(baseline_metrics, indent=2) + "\n")
    print(f"   Wrote {BASELINE_PATH}")

    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE)

    print(
        f"6a) RandomizedSearchCV over RF-supported params "
        f"(scoring={SCORING!r}, n_jobs=1, refit=True)…"
    )
    random_search = RandomizedSearchCV(
        build_pipeline(X_train),
        param_distributions=RANDOM_PARAM_DISTRIBUTIONS,
        n_iter=16,
        scoring=SCORING,
        cv=cv,
        random_state=RANDOM_STATE,
        n_jobs=1,
        verbose=1,
        refit=True,  # default; sklearn refits the best estimator on full train
    )
    random_search.fit(X_train, y_train)
    print("   Random best params:", random_search.best_params_)
    print(f"   Random best CV {SCORING}:", float(random_search.best_score_))

    narrowed = narrow_param_grid(random_search.best_params_)
    print("6b) Narrowed GridSearchCV space:", narrowed)
    print(
        f"6c) GridSearchCV refine (scoring={SCORING!r}, n_jobs=1, refit=True)…"
    )
    grid_search = GridSearchCV(
        build_pipeline(X_train),
        param_grid=narrowed,
        scoring=SCORING,
        cv=cv,
        n_jobs=1,
        verbose=1,
        refit=True,  # use grid_search.best_estimator_ as-is — do not .fit() again
    )
    grid_search.fit(X_train, y_train)
    print("   Grid best params:", grid_search.best_params_)
    print(f"   Grid best CV {SCORING}:", float(grid_search.best_score_))

    # best_estimator_ is already refit on the full training set by GridSearchCV.
    final_model = grid_search.best_estimator_

    print("7) Final test evaluation (only other time we touch the test set)…")
    tuned_metrics = evaluate(final_model, X_test, y_test)
    print("   Tuned final (test):", tuned_metrics)
    print("\nClassification report (tuned, final test):")
    print(
        classification_report(
            y_test,
            final_model.predict(X_test),
            target_names=["No", "Yes"],
        )
    )

    payload = {
        "data_url": DATA_URL,
        "n_rows": int(len(X)),
        "n_features": int(X.shape[1]),
        "churn_rate": float(y.mean()),
        "split": {"train": int(len(X_train)), "test": int(len(X_test)), "test_size": 0.2},
        "scoring": SCORING,
        "scoring_rationale": (
            "Maximize recall on the churn class so retention outreach misses fewer leavers; "
            "accuracy is the wrong default for an imbalanced churn problem."
        ),
        "baseline": baseline_metrics,
        "random_search": {
            "n_iter": 16,
            "n_jobs": 1,
            "best_params": random_search.best_params_,
            "best_cv_score": float(random_search.best_score_),
        },
        "narrowed_param_grid": narrowed,
        "grid_search": {
            "n_jobs": 1,
            "best_params": grid_search.best_params_,
            "best_cv_score": float(grid_search.best_score_),
            "refit": True,
            "manual_refit": False,
        },
        "tuned_final": tuned_metrics,
    }
    METRICS_PATH.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"Wrote {METRICS_PATH}")


if __name__ == "__main__":
    main()
