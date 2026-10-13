"""Temporal evaluation of the Brasaland monthly sales forest.

The check uses only the first 8 years (2016–2023). 2024–2025 stay held out.
Each fold is chronological. Lag and rolling features for a fold are built
from months before that fold's validation window, then from the fold's own
predictions — never from the validation month's actual revenue.

Underestimating a peak month is the costlier error (CONTEXT-company.md):
Felipe's kitchens stock out. RMSE is the primary metric because a December
miss is larger than a typical month.
"""

from __future__ import annotations

import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.model_selection import TimeSeriesSplit

from data.process.sales_forecast import (
    FEATURE_COLUMNS,
    SEED,
    SERIES_START,
    TARGET_COLUMN,
    TRAIN_YEARS,
    build_features,
    drop_warmup,
    load_sales,
    scale_features,
)

N_SPLITS = 5
PRIMARY_METRIC = "rmse"


def new_forest() -> RandomForestRegressor:
    """Same scikit-learn forest as scripts/train_sales_forecast.py."""

    return RandomForestRegressor(
        n_estimators=300,
        max_depth=4,
        min_samples_leaf=2,
        random_state=SEED,
        n_jobs=1,
    )


def training_history():
    """Months before the 2-year holdout, in calendar order."""

    sales = load_sales()
    cutoff = SERIES_START.year + TRAIN_YEARS
    history = sales.loc[sales["month"].dt.year < cutoff].reset_index(drop=True)
    if history.empty:
        raise ValueError("training history is empty")
    return history


def temporal_folds(n_rows: int, n_splits: int = N_SPLITS):
    """Yield ``(train_idx, val_idx)`` from ``TimeSeriesSplit``. No shuffle."""

    if n_rows < n_splits + 1:
        raise ValueError(f"need at least {n_splits + 1} rows for {n_splits} folds")
    # 12-month validation windows. The first training block stays long enough
    # for the 12-month lag (default test size would leave only 16 months).
    splitter = TimeSeriesSplit(n_splits=n_splits, test_size=12)
    for train_idx, val_idx in splitter.split(range(n_rows)):
        yield train_idx, val_idx


def fold_is_chronological(train_idx, val_idx) -> bool:
    train_list = [int(i) for i in train_idx]
    val_list = [int(i) for i in val_idx]
    if train_list != sorted(train_list) or val_list != sorted(val_list):
        return False
    if not train_list or not val_list:
        return False
    return max(train_list) < min(val_list)


def _predict_revenue(model, scaler, featured_row) -> float:
    features = pd.DataFrame([featured_row[list(FEATURE_COLUMNS)]])
    factor = float(model.predict(scaler.transform(features))[0])
    lag_12 = float(featured_row["revenue_lag_12"])
    return max(factor * lag_12, 0.0)


def fit_on_prefix(prefix):
    """One-step fit on a contiguous history. Returns model, scaler, train frame."""

    featured = drop_warmup(build_features(prefix))
    if len(featured) < 8:
        raise ValueError("prefix is too short to fit the 12-month lag")
    x_train, _, scaler = scale_features(featured, featured, FEATURE_COLUMNS)
    model = new_forest()
    yoy = featured[TARGET_COLUMN].to_numpy(dtype=float) / featured["revenue_lag_12"].to_numpy(dtype=float)
    model.fit(x_train, yoy)
    return model, scaler, featured


def training_errors(model, scaler, featured) -> tuple[float, float]:
    preds = []
    for _, row in featured.iterrows():
        preds.append(_predict_revenue(model, scaler, row))
    actual = featured[TARGET_COLUMN].to_numpy(dtype=float)
    return (
        float(mean_absolute_error(actual, preds)),
        float(mean_squared_error(actual, preds) ** 0.5),
    )


def recursive_forecast(model, scaler, history, horizon_rows) -> list[float]:
    """Forecast ``horizon_rows`` without using their actual revenue.

    Covers and average ticket stay at the last month already in ``history``.
    Those fields are not known for a future month, and reading them from the
    validation window would leak.
    """

    prefix = history.copy().reset_index(drop=True)
    last_covers = float(prefix["covers_served"].iloc[-1])
    last_ticket = float(prefix["avg_ticket_usd"].iloc[-1])
    predictions: list[float] = []
    for _, upcoming in horizon_rows.iterrows():
        placeholder = {
            "month": upcoming["month"],
            TARGET_COLUMN: float("nan"),
            "covers_served": last_covers,
            "avg_ticket_usd": last_ticket,
            "market": "consolidated",
        }
        step = pd.concat([prefix, pd.DataFrame([placeholder])], ignore_index=True)
        featured = build_features(step).iloc[-1]
        if featured[list(FEATURE_COLUMNS)].isna().any():
            raise ValueError(f"cannot featurize {upcoming['month']} without future actuals")
        predicted = _predict_revenue(model, scaler, featured)
        predictions.append(predicted)
        placeholder[TARGET_COLUMN] = predicted
        prefix = pd.concat([prefix, pd.DataFrame([placeholder])], ignore_index=True)
    return predictions


def evaluate_folds(history=None, n_splits: int = N_SPLITS) -> list[dict]:
    """Fit each chronological fold and score the following months recursively."""

    if history is None:
        history = training_history()
    reports = []
    for fold_id, (train_idx, val_idx) in enumerate(temporal_folds(len(history), n_splits), start=1):
        if not fold_is_chronological(train_idx, val_idx):
            raise ValueError(f"fold {fold_id} is not chronological")
        prefix = history.iloc[list(train_idx)].reset_index(drop=True)
        horizon = history.iloc[list(val_idx)].reset_index(drop=True)
        if prefix["month"].max() >= horizon["month"].min():
            raise ValueError(f"fold {fold_id} mixes training and validation months")
        model, scaler, featured = fit_on_prefix(prefix)
        train_mae, train_rmse = training_errors(model, scaler, featured)
        predicted = recursive_forecast(model, scaler, prefix, horizon)
        actual = horizon[TARGET_COLUMN].to_numpy(dtype=float)
        reports.append(
            {
                "fold": fold_id,
                "train_end": str(prefix["month"].iloc[-1].date()),
                "val_start": str(horizon["month"].iloc[0].date()),
                "val_end": str(horizon["month"].iloc[-1].date()),
                "train_rows": int(len(featured)),
                "val_rows": int(len(horizon)),
                "train_mae": train_mae,
                "train_rmse": train_rmse,
                "val_mae": float(mean_absolute_error(actual, predicted)),
                "val_rmse": float(mean_squared_error(actual, predicted) ** 0.5),
            }
        )
    return reports


def learning_curve_points(history=None) -> list[dict]:
    """Grow the training prefix. Each point validates the next 12 months."""

    if history is None:
        history = training_history()
    horizon = 12
    points = []
    for size in (36, 48, 60, 72, 84):
        if size + horizon > len(history):
            continue
        prefix = history.iloc[:size].reset_index(drop=True)
        upcoming = history.iloc[size : size + horizon].reset_index(drop=True)
        model, scaler, featured = fit_on_prefix(prefix)
        train_mae, train_rmse = training_errors(model, scaler, featured)
        predicted = recursive_forecast(model, scaler, prefix, upcoming)
        actual = upcoming[TARGET_COLUMN].to_numpy(dtype=float)
        points.append(
            {
                "train_rows": int(len(featured)),
                "prefix_months": size,
                "train_mae": train_mae,
                "train_rmse": train_rmse,
                "val_mae": float(mean_absolute_error(actual, predicted)),
                "val_rmse": float(mean_squared_error(actual, predicted) ** 0.5),
            }
        )
    return points


def summarize(folds: list[dict]) -> dict:
    import numpy as np

    def _stat(name: str) -> tuple[float, float]:
        values = np.array([fold[name] for fold in folds], dtype=float)
        return float(values.mean()), float(values.std(ddof=0))

    summary = {}
    for name in ("train_mae", "train_rmse", "val_mae", "val_rmse"):
        mean, std = _stat(name)
        summary[name] = {"mean": mean, "std": std, "text": f"{mean:,.0f} ± {std:,.0f}"}
    return summary


def diagnose(curve: list[dict], summary: dict) -> dict:
    """Read the learning curve. A wide gap is overfitting; both high is underfitting."""

    last = curve[-1]
    gap = last["val_rmse"] - last["train_rmse"]
    ratio = last["val_rmse"] / last["train_rmse"] if last["train_rmse"] else float("inf")
    # Dollars: a typical month in the later training years is roughly 600–800k.
    # "High" error means the miss is still large relative to a month's revenue
    # after the curve has had the full training prefix.
    high_error = 80_000
    if last["train_rmse"] >= high_error and last["val_rmse"] >= high_error and ratio < 1.5:
        label = "underfitting"
        action = (
            "The forest is too shallow for the December spike once the forecast "
            "has to run forward without next month's actual revenue. Raise "
            "`max_depth` from 4 to 8 and add the month number as a feature "
            "before collecting more years."
        )
    elif ratio >= 1.5 and gap >= 25_000:
        label = "overfitting"
        action = (
            "The training error is low and the forward validation error stays "
            f"about {ratio:.1f}× higher on the longest prefix. Lower "
            "`max_depth` from 4 to 3 and raise `min_samples_leaf` from 2 to 4 "
            "before adding more years. Do not add depth."
        )
    else:
        label = "well fitted"
        action = (
            "Keep `max_depth=4`, `min_samples_leaf=2`, and `random_state=42`. "
            "The next change is operational: review a December forecast by hand "
            "before Felipe places the meat order, because underestimating that "
            "month is the costly miss. Do not add depth and do not throw the holdout years into training."
        )
    return {
        "label": label,
        "gap_usd": gap,
        "ratio": ratio,
        "last_train_rmse": last["train_rmse"],
        "last_val_rmse": last["val_rmse"],
        "action": action,
        "primary_mean_std": summary["val_rmse"]["text"],
    }
