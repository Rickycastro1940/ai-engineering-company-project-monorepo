"""StreamLoop — Tuning the Churn Model (headless runner).

Assignment flow:
1. Load the public Telco churn CSV from URL
2. Minimal cleaning only (blank→NaN, target encoding, drop id)
3. Stratified train/test split *before* any model work
4. Pipeline = preprocessing (impute + encode) + classifier (defaults)
5. Fit on train; score the test set once for the baseline
6. Hyperparameter search uses training data + CV only
7. Final holdout score is evaluated only at the very end
"""

from __future__ import annotations

import json
from pathlib import Path

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
from sklearn.model_selection import RandomizedSearchCV, StratifiedKFold, train_test_split
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
    # Empty strings in object columns → NaN so SimpleImputer can handle them
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

    numeric = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
        ]
    )
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
    # Default hyperparameters unless the caller overrides (tuning / search).
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
    baseline = build_pipeline(X_train)  # sklearn defaults (+ random_state only)
    print("5) Fit on train; score test once → baseline…")
    baseline.fit(X_train, y_train)
    baseline_metrics = evaluate(baseline, X_test, y_test)
    print("   Baseline (test):", baseline_metrics)
    BASELINE_PATH.write_text(json.dumps(baseline_metrics, indent=2) + "\n")
    print(f"   Wrote {BASELINE_PATH}")

    # --- Tuning uses training folds only; test is untouched until the end ---
    print("6) Hyperparameter search on training data only (CV)…")
    search = RandomizedSearchCV(
        build_pipeline(X_train),
        param_distributions={
            "model__n_estimators": [100, 200, 300],
            "model__max_depth": [None, 8, 12, 16],
            "model__min_samples_split": [2, 5, 10],
            "model__min_samples_leaf": [1, 2, 4],
            "model__max_features": ["sqrt", "log2"],
        },
        n_iter=12,
        scoring="roc_auc",
        cv=StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE),
        random_state=RANDOM_STATE,
        n_jobs=-1,
        verbose=1,
        refit=True,
    )
    search.fit(X_train, y_train)
    print("   Best params:", search.best_params_)
    print("   Best CV ROC-AUC:", float(search.best_score_))

    print("7) Final test evaluation (only other time we touch the test set)…")
    tuned_metrics = evaluate(search.best_estimator_, X_test, y_test)
    print("   Tuned (test):", tuned_metrics)
    print("\nClassification report (tuned, final test):")
    print(
        classification_report(
            y_test,
            search.best_estimator_.predict(X_test),
            target_names=["No", "Yes"],
        )
    )

    payload = {
        "data_url": DATA_URL,
        "n_rows": int(len(X)),
        "n_features": int(X.shape[1]),
        "churn_rate": float(y.mean()),
        "split": {"train": int(len(X_train)), "test": int(len(X_test)), "test_size": 0.2},
        "baseline_notes": (
            "RandomForestClassifier defaults (+ random_state=42). "
            "Preprocessing (median/most_frequent impute + one-hot) is inside the Pipeline. "
            "Test set scored only here and in tuned_final."
        ),
        "baseline": baseline_metrics,
        "best_params": search.best_params_,
        "best_cv_roc_auc": float(search.best_score_),
        "tuned_final": tuned_metrics,
    }
    METRICS_PATH.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"Wrote {METRICS_PATH}")


if __name__ == "__main__":
    main()
