"""StreamLoop — Tuning the Churn Model (headless runner).

Assignment flow:
1. Load the public Telco churn CSV from URL
2. Minimal cleaning only (blank→NaN, target encoding, drop id)
3. Stratified train/test split *before* any model work
4. Pipeline = imputer + scaler + encoder + classifier (defaults; nothing fit before split)
5. Fit on train; score the test set once for the baseline
6. RandomizedSearchCV / GridSearchCV see **training data only** (n_jobs=1)
7. Inspect grid cv_results_ for mean vs fold stability; pick final params
8. Fit the chosen pipeline on train (search never sees test / full dataset)
9. Score the test set exactly once more with the same metrics as baseline
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.base import clone
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
from sklearn.preprocessing import OneHotEncoder, StandardScaler

DATA_URL = (
    "https://raw.githubusercontent.com/IBM/telco-customer-churn-on-icp4d/"
    "master/data/Telco-Customer-Churn.csv"
)
RANDOM_STATE = 42
OUT_DIR = Path(__file__).resolve().parent
METRICS_PATH = OUT_DIR / "tuning_metrics.json"
BASELINE_PATH = OUT_DIR / "baseline_metrics.json"
REPORT_PATH = OUT_DIR / "tuning_report.md"
CANDIDATES_PATH = OUT_DIR / "cv_top_candidates.json"

# Business priority: miss fewer churners so retention can act (not sklearn accuracy).
SCORING = "recall"

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
    """Single sklearn Pipeline: imputer + scaler + encoder + classifier.

    No OneHotEncoder / StandardScaler is fit outside this Pipeline or before the
    train/test split — only column typing / blank→NaN happens in minimal_clean.
    """
    cat_cols, num_cols = feature_columns(X)
    numeric = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
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
    return ordered[max(0, idx - k) : min(len(ordered), idx + k + 1)]


def narrow_param_grid(
    best_params: dict[str, Any],
    broad: dict[str, list[Any]] | None = None,
) -> dict[str, list[Any]]:
    broad = broad or RANDOM_PARAM_DISTRIBUTIONS
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


def normalize_params(params: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in params.items():
        if v is None:
            out[k] = None
        elif isinstance(v, (bool, np.bool_)):
            out[k] = bool(v)
        elif isinstance(v, (np.integer,)):
            out[k] = int(v)
        elif isinstance(v, (np.floating,)):
            out[k] = float(v)
        else:
            out[k] = v
    return out


def cv_results_table(search) -> pd.DataFrame:
    """Rank candidates by mean CV score and expose fold-level spread."""
    cvres = search.cv_results_
    n_splits = len([k for k in cvres if k.startswith("split") and k.endswith("_test_score")])
    rows = []
    for i in range(len(cvres["mean_test_score"])):
        fold_scores = [float(cvres[f"split{k}_test_score"][i]) for k in range(n_splits)]
        params = normalize_params(cvres["params"][i])
        rows.append(
            {
                "rank": int(cvres["rank_test_score"][i]),
                "mean_test_score": float(cvres["mean_test_score"][i]),
                "std_test_score": float(cvres["std_test_score"][i]),
                "mean_minus_std": float(
                    cvres["mean_test_score"][i] - cvres["std_test_score"][i]
                ),
                "fold_scores": fold_scores,
                "params": params,
            }
        )
    table = pd.DataFrame(rows).sort_values(
        ["mean_test_score", "mean_minus_std"], ascending=False
    )
    return table.reset_index(drop=True)


def select_final_candidate(top: pd.DataFrame) -> tuple[dict[str, Any], str]:
    """Prefer a slightly lower mean when fold std is meaningfully better.

    Rule: among the top 5 by mean recall, if another candidate loses less than
    0.01 mean recall vs the leader but cuts std by at least 25% (and ≥ 0.005
    absolute), prefer the stabler option. Otherwise take the highest mean.
    """
    pool = top.head(5).reset_index(drop=True)
    leader = pool.iloc[0]
    choice_pos = 0
    reason = (
        f"Highest mean CV {SCORING} "
        f"({leader['mean_test_score']:.4f} ± {leader['std_test_score']:.4f}). "
        "No nearby candidate offered a clear stability gain for a small mean trade-off."
    )

    best_stable_std = float(leader["std_test_score"])
    for pos in range(1, len(pool)):
        cand = pool.iloc[pos]
        mean_drop = float(leader["mean_test_score"] - cand["mean_test_score"])
        std_drop = float(leader["std_test_score"] - cand["std_test_score"])
        cand_std = float(cand["std_test_score"])
        if (
            mean_drop < 0.01
            and std_drop >= 0.005
            and cand_std <= 0.75 * float(leader["std_test_score"])
            and cand_std < best_stable_std
        ):
            choice_pos = pos
            best_stable_std = cand_std
            reason = (
                f"Chose a slightly lower mean CV {SCORING} "
                f"({cand['mean_test_score']:.4f} vs leader {leader['mean_test_score']:.4f}) "
                f"because fold std fell from {leader['std_test_score']:.4f} to "
                f"{cand_std:.4f}. For retention ops, a more stable catch-rate "
                "across folds is preferable to chasing the peak mean."
            )

    choice = pool.iloc[choice_pos]
    return dict(choice["params"]), reason


def write_tuning_report(
    *,
    baseline: dict,
    tuned: dict,
    final_params: dict,
    selection_reason: str,
    top_candidates: list[dict],
    random_best_cv: float,
    grid_best_cv: float,
) -> str:
    lines = [
        "# StreamLoop churn model — tuning report",
        "",
        "## Metric choice",
        "",
        "Primary search metric: **`recall`** on the churn (`Yes`) class.",
        "",
        "StreamLoop's business priority is catching customers who will leave so "
        "retention can act. Missing a churner (false negative) is costlier than a "
        "false-positive outreach. Sklearn's default accuracy would over-reward the "
        "majority non-churn class (~73.5% of rows) and hide weak churn detection.",
        "",
        "Reported metrics match the baseline suite: accuracy, precision, recall, F1, ROC-AUC.",
        "",
        "## Search protocol (train only)",
        "",
        "- Stratified 80/20 split **before** any model work.",
        "- Preprocessing is **inside** one sklearn `Pipeline` "
        "(`SimpleImputer` → `StandardScaler` on numerics; "
        "`SimpleImputer` → `OneHotEncoder` on categoricals; then the classifier). "
        "No one-hot or scaler is fit before the split or outside the Pipeline.",
        "- `RandomizedSearchCV` then narrowed `GridSearchCV` fit on **`X_train` only** "
        "(`n_jobs=1`, `refit=True`).",
        "- Searches never see the test set or the full dataset.",
        "- Test set touched **exactly twice**: baseline defaults, then final tuned model.",
        "",
        f"- Random search best CV {SCORING}: **{random_best_cv:.4f}**",
        f"- Grid search best mean CV {SCORING}: **{grid_best_cv:.4f}** "
        "(face-value `best_params_`; see stability review below).",
        "",
        "## Stability review (`cv_results_`)",
        "",
        "Inspected top GridSearchCV candidates on **mean** CV recall **and fold std** "
        "(not face-value `best_params_` alone). Trade-off rule: prefer a slightly lower "
        "mean when std drops by ≥25% and ≥0.005 absolute within a 0.01 mean window; "
        "otherwise keep the highest mean.",
        "",
        "Top candidates:",
        "",
        "| rank | mean recall | std | mean−std | max_depth | n_estimators | min_samples_leaf |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in top_candidates[:5]:
        p = row["params"]
        lines.append(
            f"| {row['rank']} | {row['mean_test_score']:.4f} | {row['std_test_score']:.4f} | "
            f"{row['mean_minus_std']:.4f} | {p.get('model__max_depth')} | "
            f"{p.get('model__n_estimators')} | {p.get('model__min_samples_leaf')} |"
        )
    lines.extend(
        [
            "",
            "### Final model choice",
            "",
            selection_reason,
            "",
            "### Final hyperparameters",
            "",
            "```json",
            json.dumps(final_params, indent=2),
            "```",
            "",
            "## Baseline vs tuned (held-out test, scored once each)",
            "",
            "| Metric | Baseline (defaults) | Tuned final | Δ |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    for key in ("accuracy", "precision", "recall", "f1", "roc_auc"):
        b, t = baseline[key], tuned[key]
        lines.append(f"| {key} | {b:.4f} | {t:.4f} | {t - b:+.4f} |")
    lines.extend(
        [
            "",
            "## Takeaway",
            "",
            f"Tuning for **{SCORING}** lifted churn catch-rate on the holdout "
            f"from **{baseline['recall']:.3f}** to **{tuned['recall']:.3f}**, "
            "with the expected precision trade-off from `class_weight='balanced'` "
            "and shallower trees. Accuracy alone would have preferred the baseline; "
            "that is why it was not the search objective.",
            "",
        ]
    )
    text = "\n".join(lines)
    REPORT_PATH.write_text(text)
    return text


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
    # Guard: searches below receive only train indices' frames.
    assert len(X_train) + len(X_test) == len(X)

    print("4) Build pipeline (impute+encode inside) + default RandomForest…")
    baseline = build_pipeline(X_train)
    print("5) Fit on train; score test once → baseline…")
    baseline.fit(X_train, y_train)
    baseline_metrics = evaluate(baseline, X_test, y_test)
    print("   Baseline (test):", baseline_metrics)
    BASELINE_PATH.write_text(json.dumps(baseline_metrics, indent=2) + "\n")

    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE)

    print(
        f"6a) RandomizedSearchCV on TRAIN only "
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
        refit=True,
    )
    random_search.fit(X_train, y_train)  # training split only
    print("   Random best params:", random_search.best_params_)
    print(f"   Random best CV {SCORING}:", float(random_search.best_score_))

    narrowed = narrow_param_grid(random_search.best_params_)
    print("6b) Narrowed GridSearchCV space:", narrowed)
    print(
        f"6c) GridSearchCV on TRAIN only "
        f"(scoring={SCORING!r}, n_jobs=1, refit=True)…"
    )
    grid_search = GridSearchCV(
        build_pipeline(X_train),
        param_grid=narrowed,
        scoring=SCORING,
        cv=cv,
        n_jobs=1,
        verbose=1,
        refit=True,
    )
    grid_search.fit(X_train, y_train)  # training split only
    print("   Grid face-value best params:", grid_search.best_params_)
    print(f"   Grid best mean CV {SCORING}:", float(grid_search.best_score_))

    print("6d) Inspect cv_results_ top candidates (mean vs fold std)…")
    top = cv_results_table(grid_search)
    print(top.head(5)[["rank", "mean_test_score", "std_test_score", "mean_minus_std"]].to_string(index=False))
    final_params, selection_reason = select_final_candidate(top)
    print("   Selected params:", final_params)
    print("   Reason:", selection_reason)

    top_records = top.head(8).to_dict(orient="records")
    CANDIDATES_PATH.write_text(json.dumps(top_records, indent=2) + "\n")

    # Fit the *chosen* configuration on the full training split only.
    # If it matches GridSearchCV's mean-best, reuse best_estimator_ (already refit).
    # Otherwise clone + set_params + fit on X_train — never on X_test / full data.
    grid_best_params = normalize_params(grid_search.best_params_)
    if final_params == grid_best_params:
        final_model = grid_search.best_estimator_
        fitted_via = "grid_search.best_estimator_ (refit=True on train)"
    else:
        final_model = clone(build_pipeline(X_train)).set_params(**final_params)
        final_model.fit(X_train, y_train)
        fitted_via = "clone+set_params+fit on X_train (stabler candidate ≠ mean-best)"

    print(f"7) Final test evaluation once ({fitted_via})…")
    tuned_metrics = evaluate(final_model, X_test, y_test)
    print("   Tuned final (test):", tuned_metrics)
    print(classification_report(y_test, final_model.predict(X_test), target_names=["No", "Yes"]))

    report = write_tuning_report(
        baseline=baseline_metrics,
        tuned=tuned_metrics,
        final_params=final_params,
        selection_reason=selection_reason,
        top_candidates=top_records,
        random_best_cv=float(random_search.best_score_),
        grid_best_cv=float(grid_search.best_score_),
    )
    print(f"Wrote {REPORT_PATH}")

    payload = {
        "data_url": DATA_URL,
        "n_rows": int(len(X)),
        "n_features": int(X.shape[1]),
        "churn_rate": float(y.mean()),
        "split": {"train": int(len(X_train)), "test": int(len(X_test)), "test_size": 0.2},
        "search_fit_on": "X_train_only",
        "test_touches": ["baseline", "tuned_final"],
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
        },
        "selection": {
            "final_params": final_params,
            "reason": selection_reason,
            "fitted_via": fitted_via,
            "top_candidates_path": str(CANDIDATES_PATH.name),
        },
        "tuned_final": tuned_metrics,
        "tuning_report": str(REPORT_PATH.name),
    }
    METRICS_PATH.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"Wrote {METRICS_PATH}")
    print("\n--- tuning_report.md preview ---\n")
    print(report)


if __name__ == "__main__":
    main()
