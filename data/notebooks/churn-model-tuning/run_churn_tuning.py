"""StreamLoop — Tuning the Churn Model (headless runner).

Loads the public IBM Telco Customer Churn CSV from URL, trains a baseline
RandomForest, tunes hyperparameters with RandomizedSearchCV, and prints
comparison metrics. Mirrors streamloop_churn_tuning.ipynb.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
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


def load_and_clean(url: str = DATA_URL) -> tuple[pd.DataFrame, pd.Series]:
    df = pd.read_csv(url)
    df = df.copy()
    df["TotalCharges"] = pd.to_numeric(df["TotalCharges"], errors="coerce")
    df["TotalCharges"] = df["TotalCharges"].fillna(df["TotalCharges"].median())
    df["Churn"] = (df["Churn"] == "Yes").astype(int)
    y = df["Churn"]
    X = df.drop(columns=["Churn", "customerID"])
    return X, y


def build_pipeline(X: pd.DataFrame) -> Pipeline:
    cat_cols = X.select_dtypes(include=["object", "string", "category"]).columns.tolist()
    num_cols = [c for c in X.columns if c not in cat_cols]
    preprocess = ColumnTransformer(
        transformers=[
            ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), cat_cols),
            ("num", "passthrough", num_cols),
        ]
    )
    return Pipeline(
        steps=[
            ("preprocess", preprocess),
            (
                "model",
                RandomForestClassifier(
                    n_estimators=100,
                    random_state=RANDOM_STATE,
                    class_weight="balanced",
                    n_jobs=-1,
                ),
            ),
        ]
    )


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
    print("Loading StreamLoop / Telco churn data from URL…")
    X, y = load_and_clean()
    print(f"rows={len(X)} features={X.shape[1]} churn_rate={y.mean():.3f}")

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=RANDOM_STATE, stratify=y
    )

    baseline = build_pipeline(X_train)
    print("Fitting baseline RandomForest…")
    baseline.fit(X_train, y_train)
    baseline_metrics = evaluate(baseline, X_test, y_test)
    print("Baseline:", baseline_metrics)

    pipe = build_pipeline(X_train)
    param_distributions = {
        "model__n_estimators": [100, 200, 300],
        "model__max_depth": [None, 8, 12, 16],
        "model__min_samples_split": [2, 5, 10],
        "model__min_samples_leaf": [1, 2, 4],
        "model__max_features": ["sqrt", "log2"],
    }
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE)
    search = RandomizedSearchCV(
        pipe,
        param_distributions=param_distributions,
        n_iter=12,
        scoring="roc_auc",
        cv=cv,
        random_state=RANDOM_STATE,
        n_jobs=-1,
        verbose=1,
    )
    print("Tuning with RandomizedSearchCV (scoring=roc_auc)…")
    search.fit(X_train, y_train)
    tuned_metrics = evaluate(search.best_estimator_, X_test, y_test)
    print("Best params:", search.best_params_)
    print("Best CV ROC-AUC:", float(search.best_score_))
    print("Tuned holdout:", tuned_metrics)
    print("\nClassification report (tuned):")
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
        "baseline": baseline_metrics,
        "best_params": search.best_params_,
        "best_cv_roc_auc": float(search.best_score_),
        "tuned": tuned_metrics,
    }
    METRICS_PATH.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"Wrote {METRICS_PATH}")


if __name__ == "__main__":
    main()
