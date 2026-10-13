"""Train the Brasaland monthly revenue forecast.

Model choice (scikit-learn ``RandomForestRegressor``)
------------------------------------------------------
Criteria, in order:

1. Explainability. Mariana asked for a range she can walk through on a
   Monday, not a single optimistic number. A forest averages trees. The
   chart band is the standard deviation across those trees.
2. Data size. The series is 120 months and about 84 of them are fit.
   That is a small sample for sequential boosting.
3. Time to tune. XGBoost usually needs a search over learning rate and
   tree depth. That search is not justified here.

Seed is fixed (``random_state=42``). Metric definitions and why a low MSE
is not enough are in ``data/eval/sales_forecast/README.md``.

Run from the repo root::

    uv run python scripts/train_sales_forecast.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error
from statsmodels.tsa.seasonal import seasonal_decompose

from data.process.sales_forecast import (
    FEATURE_COLUMNS,
    ILLUSTRATIVE_COP_PER_USD,
    SEED,
    SERIES_START,
    TARGET_COLUMN,
    TRAIN_CUTOFF_YEAR,
    assert_official_calendar,
    build_features,
    drop_warmup,
    k2_score,
    load_sales,
    mean_absolute_percentage_error,
    normalized_gini,
    population_stability_index,
    scale_features,
    seasonality_check,
    split_by_year,
)

OUTPUT_DIR = Path(__file__).resolve().parents[1] / "data" / "eval" / "sales_forecast"


def save_decomposition(frame: pd.DataFrame, path: Path) -> str:
    """Diagnostic only: trend, seasonal, residual. Not the forecast."""

    series = frame.set_index("month")[TARGET_COLUMN].asfreq("MS")
    result = seasonal_decompose(series, model="additive", period=12)
    figure = result.plot()
    figure.set_size_inches(10, 8)
    figure.suptitle("Brasaland consolidated revenue — trend, seasonality, residual", y=1.02)
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=120, bbox_inches="tight")
    plt.close(figure)

    seasonal = result.seasonal
    january = float(seasonal[seasonal.index.month == 1].mean())
    december = float(seasonal[seasonal.index.month == 12].mean())
    if december > 0 and january < 0:
        note = (
            f"Additive seasonal component matches the brief: "
            f"December averages {december:,.0f} USD above the trend and "
            f"January averages {january:,.0f} USD below it."
        )
    else:
        note = (
            "Seasonal component does not show a December peak and a January "
            f"dip (December {december:,.0f}, January {january:,.0f})."
        )
    return note


def fit_forest(train: pd.DataFrame, test: pd.DataFrame) -> dict:
    """Fit on train only. Scaler statistics come from train only.

    The forest predicts the year-over-year factor ``revenue_t / revenue_{t-12}``.
    Dollar revenue is that factor times the same month last year. A tree cannot
    extrapolate a rising dollar level; the brief's growth is a multiplier on
    last year, and December's spike is already in last December's revenue.
    """

    x_train, x_test, scaler = scale_features(train, test)
    y_train_usd = train[TARGET_COLUMN].to_numpy(dtype=float)
    y_test = test[TARGET_COLUMN].to_numpy(dtype=float)
    lag_12_train = train["revenue_lag_12"].to_numpy(dtype=float)
    lag_12_test = test["revenue_lag_12"].to_numpy(dtype=float)
    y_train = y_train_usd / lag_12_train

    # scikit-learn RandomForestRegressor. See the module docstring for the
    # choice: explainability, 120-month sample, and little time to tune.
    model = RandomForestRegressor(
        n_estimators=300,
        max_depth=4,
        min_samples_leaf=2,
        random_state=SEED,
        n_jobs=1,
    )
    model.fit(x_train, y_train)

    tree_factors = np.stack([tree.predict(x_test) for tree in model.estimators_])
    factor = tree_factors.mean(axis=0)
    factor_std = tree_factors.std(axis=0)
    mean_pred = np.maximum(factor * lag_12_test, 0.0)
    std_pred = factor_std * lag_12_test

    residuals = y_test - mean_pred
    mse = float(mean_squared_error(y_test, mean_pred))
    k2, k2_p = k2_score(residuals)
    yoy_test = y_test / lag_12_test
    metrics = {
        "mse": mse,
        "rmse_usd": float(np.sqrt(mse)),
        "mape_pct": mean_absolute_percentage_error(y_test, mean_pred),
        # Behavior shift: year-over-year factor, not the rising dollar level.
        "psi": population_stability_index(y_train, yoy_test),
        "psi_revenue_level": population_stability_index(y_train_usd, y_test),
        "gini": normalized_gini(y_test, mean_pred),
        "k2": k2,
        "k2_p_value": k2_p,
        "train_rows": int(len(train)),
        "test_rows": int(len(test)),
        "train_start": str(train["month"].iloc[0].date()),
        "train_end": str(train["month"].iloc[-1].date()),
        "test_start": str(test["month"].iloc[0].date()),
        "test_end": str(test["month"].iloc[-1].date()),
    }
    importances = {
        name: float(score)
        for name, score in zip(FEATURE_COLUMNS, model.feature_importances_)
    }
    return {
        "metrics": metrics,
        "importances": importances,
        "model": model,
        "scaler": scaler,
        "y_test": y_test,
        "mean_pred": mean_pred,
        "std_pred": std_pred,
        "months": test["month"].to_numpy(),
    }


def save_forecast_plot(result: dict, path: Path) -> None:
    months = pd.to_datetime(result["months"])
    actual = result["y_test"]
    forecast = result["mean_pred"]
    band = result["std_pred"]
    figure, axis = plt.subplots(figsize=(10, 5))
    axis.plot(months, actual, color="#1f2933", marker="o", label="Actual revenue (USD)")
    axis.plot(months, forecast, color="#c2410c", marker="o", label="Random forest forecast")
    axis.fill_between(
        months,
        np.maximum(forecast - band, 0.0),
        forecast + band,
        color="#c2410c",
        alpha=0.25,
        label="Tree variability (± 1 std across trees)",
    )
    axis.set_title("Brasaland consolidated sales — 2024–2025 holdout")
    axis.set_ylabel("Revenue (USD)")
    axis.set_xlabel("Month")
    axis.legend(loc="upper left")
    axis.grid(True, axis="y", alpha=0.3)
    figure.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=120)
    plt.close(figure)


def write_metrics_markdown(
    path: Path,
    metrics: dict,
    importances: dict,
    pattern: dict[str, float],
    decomposition_note: str,
    warmup_rows: int,
) -> None:
    ranked = sorted(importances.items(), key=lambda item: item[1], reverse=True)
    importance_lines = "\n".join(
        f"| `{name}` | {score:.3f} |" for name, score in ranked
    )
    psi = metrics["psi"]
    if psi < 0.10:
        psi_read = "stable (under 0.10)"
    elif psi < 0.25:
        psi_read = "moderate shift (0.10–0.25)"
    else:
        psi_read = "large shift (over 0.25)"

    text = f"""# Brasaland sales forecast — test metrics

Audience: Mariana Restrepo (chain sales), Felipe Guerrero (covers and purchasing), Lucía Fernández (volume). Currency in the model is consolidated USD. An illustrative COP column uses 1 USD = {ILLUSTRATIVE_COP_PER_USD:,} COP and is not a live exchange rate.

## Model

Random forest (`n_estimators=300`, `max_depth=4`, `min_samples_leaf=2`, `random_state={SEED}`).

Chosen over XGBoost because the series has 120 months and Finance asked for an explainable range. The forest averages trees; the chart band is the standard deviation across those trees, scaled back into dollars. XGBoost would need more tuning than this sample supports, and sequential boosting is harder to walk through in a Monday meeting.

The forest predicts the year-over-year factor (this month ÷ the same month last year). The dollar forecast is that factor times last year's same month. Trees cannot invent a higher dollar level than they saw in training; the brief's growth is a multiplier, and the December spike is already stored in last December.

Scaler: `StandardScaler` fit on the training months only, then applied to 2024–2025.

Warmup rows dropped before the split (12-month lag): {warmup_rows}. Training uses {metrics["train_start"]} through {metrics["train_end"]} ({metrics["train_rows"]} months). The holdout is {metrics["test_start"]} through {metrics["test_end"]} ({metrics["test_rows"]} months), which is the last two years (cutoff year {TRAIN_CUTOFF_YEAR}).

## What the series already contains

{decomposition_note}

| Check | Value | Brief |
| --- | --- | --- |
| Mean January vs prior-year average | {pattern["january_vs_prior_year_mean"]:.1%} | drop of about 12–18% |
| Mean December vs same-year average | {pattern["december_vs_same_year_mean"]:.1%} | rise of about 20–30% |
| Median year-over-year growth | {pattern["median_yoy_growth"]:.1%} | base growth about 5% |
| Year-over-year range | {pattern["min_yoy_growth"]:.1%} to {pattern["max_yoy_growth"]:.1%} | generation band is about 3–7%; annual totals move a bit wider because December and January have different weights |

## Test-set metrics

All four required metrics are computed on 2024–2025 only.

| Metric | Value | How to read it |
| --- | --- | --- |
| MSE | {metrics["mse"]:,.0f} USD² | Average squared miss. Sensitive to a bad December. A low training MSE would not be reported here. |
| RMSE | {metrics["rmse_usd"]:,.0f} USD | Typical miss in dollars (square root of MSE). |
| MAPE | {metrics["mape_pct"]:.1f}% | Average percent miss. This is the figure Felipe and Mariana can use. |
| PSI | {metrics["psi"]:.3f} | {psi_read}. Compares the year-over-year factor in training with 2024–2025. Dollar-level PSI is {metrics["psi_revenue_level"]:.3f} because growth puts most test months in the top training decile; that is the 5% path, not a new season. |
| Gini | {metrics["gini"]:.3f} | 1 means the forecast ranks months in the same order as actual sales. A low Gini means December and January are not distinguished. |
| K² | {metrics["k2"]:.3f} (p={metrics["k2_p_value"]:.3f}) | D'Agostino-Pearson test on test residuals. A small p-value means the errors are skewed rather than symmetric. |

A low MSE on its own is not enough. The forest can sit near the average level (small squared error) and still miss which months are strong. Gini checks that ranking. PSI checks whether 2024–2025 still look like the training years. K² checks whether the misses lean high or low instead of scattering evenly.

## What the forest uses

| Feature | Importance |
| --- | --- |
{importance_lines}

Lag and rolling features are built with `shift` before `rolling`, so a month does not see its own revenue. Same-month covers and average ticket are not features: together they reconstruct revenue.
"""
    path.write_text(text, encoding="utf-8")


def main() -> None:
    raw = load_sales()
    assert_official_calendar(raw)
    pattern = seasonality_check(raw)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    decomposition_note = save_decomposition(raw, OUTPUT_DIR / "decomposition.png")

    featured = build_features(raw)
    ready = drop_warmup(featured)
    warmup_rows = len(featured) - len(ready)
    train, test = split_by_year(ready, origin_year=SERIES_START.year)
    result = fit_forest(train, test)

    save_forecast_plot(result, OUTPUT_DIR / "forecast_vs_actual.png")
    forecast = pd.DataFrame(
        {
            "month": pd.to_datetime(result["months"]).strftime("%Y-%m-%d"),
            "actual_revenue_usd": result["y_test"],
            "forecast_revenue_usd": result["mean_pred"],
            "variability_std_usd": result["std_pred"],
            "forecast_low_usd": np.maximum(result["mean_pred"] - result["std_pred"], 0.0),
            "forecast_high_usd": result["mean_pred"] + result["std_pred"],
            "actual_revenue_cop_illustrative": result["y_test"] * ILLUSTRATIVE_COP_PER_USD,
            "forecast_revenue_cop_illustrative": result["mean_pred"] * ILLUSTRATIVE_COP_PER_USD,
        }
    )
    forecast.to_csv(OUTPUT_DIR / "test_forecast.csv", index=False)
    write_metrics_markdown(
        OUTPUT_DIR / "metrics.md",
        result["metrics"],
        result["importances"],
        pattern,
        decomposition_note,
        warmup_rows,
    )
    (OUTPUT_DIR / "metrics.json").write_text(
        json.dumps(result["metrics"], indent=2) + "\n",
        encoding="utf-8",
    )
    joblib.dump(
        {
            "model": result["model"],
            "scaler": result["scaler"],
            "feature_columns": list(FEATURE_COLUMNS),
            "target": "revenue_usd / revenue_lag_12",
            "seed": SEED,
        },
        OUTPUT_DIR / "random_forest.joblib",
    )
    print(json.dumps(result["metrics"], indent=2))
    print(decomposition_note)


if __name__ == "__main__":
    main()
