"""Evaluate the Brasaland sales forest with temporal cross-validation.

Run from the repo root::

    uv run python scripts/evaluate_sales_model.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from data.process.sales_forecast_eval import (
    PRIMARY_METRIC,
    diagnose,
    evaluate_folds,
    learning_curve_points,
    summarize,
    training_history,
)

OUTPUT_DIR = _REPO_ROOT / "data" / "eval"


def save_learning_curve(points: list[dict], path: Path) -> None:
    sizes = [point["prefix_months"] for point in points]
    figure, axis = plt.subplots(figsize=(9, 5))
    axis.plot(sizes, [point["train_rmse"] for point in points], marker="o", color="#1f2933", label="Training RMSE")
    axis.plot(sizes, [point["val_rmse"] for point in points], marker="o", color="#c2410c", label="Validation RMSE (next 12 months)")
    axis.set_xlabel("Training months (from 2016-01, before the 2024 holdout)")
    axis.set_ylabel("RMSE (USD)")
    axis.set_title("Brasaland sales forest — learning curve")
    axis.legend(loc="best")
    axis.grid(True, axis="y", alpha=0.3)
    figure.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=120)
    plt.close(figure)


def write_report(path: Path, folds: list[dict], summary: dict, curve: list[dict], diagnosis: dict) -> None:
    fold_rows = "\n".join(
        f"| {fold['fold']} | {fold['train_end']} | {fold['val_start']} → {fold['val_end']} | "
        f"{fold['train_rmse']:,.0f} | {fold['val_rmse']:,.0f} | {fold['train_mae']:,.0f} | {fold['val_mae']:,.0f} |"
        for fold in folds
    )
    curve_rows = "\n".join(
        f"| {point['prefix_months']} | {point['train_rmse']:,.0f} | {point['val_rmse']:,.0f} | "
        f"{point['train_mae']:,.0f} | {point['val_mae']:,.0f} |"
        for point in curve
    )
    label = diagnosis["label"]
    text = f"""# Brasaland sales forecast — technical evaluation

Audience: Mariana Restrepo, Felipe Guerrero, Lucía Fernández. Series: `data/raw/brasaland_sales.csv`. Model: scikit-learn random forest from `scripts/train_sales_forecast.py` (`max_depth=4`, `min_samples_leaf=2`, `random_state=42`). The 2024–2025 holdout is not used in these folds.

## 1. Fit

**Diagnosis: {label}.**

The learning curve (`data/eval/learning_curve.png`) plots training RMSE and the RMSE of a 12-month forward forecast as the training prefix grows from 36 to 84 months inside 2016–2023.

| Training months | Train RMSE | Validation RMSE | Train MAE | Validation MAE |
| --- | --- | --- | --- | --- |
{curve_rows}

On the longest prefix the training RMSE is {diagnosis["last_train_rmse"]:,.0f} USD and the next-12-month RMSE is {diagnosis["last_val_rmse"]:,.0f} USD (gap {diagnosis["gap_usd"]:,.0f} USD, ratio {diagnosis["ratio"]:.2f}).

## 2. Stability

Temporal cross-validation is `TimeSeriesSplit` with 5 folds and a 12-month validation window. Folds are not shuffled. Features for a validation month are built from earlier months only; once the window starts, later months see the forecast, not the actual revenue.

Primary metric is **RMSE**, reported as mean ± standard deviation across the 5 validation windows: **{summary["val_rmse"]["text"]} USD**. The standard deviation is the stability result: validation RMSE runs from {min(fold["val_rmse"] for fold in folds):,.0f} to {max(fold["val_rmse"] for fold in folds):,.0f} USD. Windows for 2020, 2021, and 2022 sit near 30,000 USD. The 2023 window is the one that jumps.

| Fold | Train through | Validation window | Train RMSE | Val RMSE | Train MAE | Val MAE |
| --- | --- | --- | --- | --- | --- | --- |
{fold_rows}

| Metric | Training (mean ± std) | Validation (mean ± std) |
| --- | --- | --- |
| RMSE (primary) | {summary["train_rmse"]["text"]} | {summary["val_rmse"]["text"]} |
| MAE | {summary["train_mae"]["text"]} | {summary["val_mae"]["text"]} |

## 3. Why RMSE, not MAE

`CONTEXT-company.md` says underestimating sales is the costlier error. Felipe buys from the forecast. December runs about 20–30% above the rest of the year; a low call that month stocks the kitchens out and the cover is lost. Overestimating raises waste, which the next order can trim. RMSE weights a large December miss more than MAE, which treats every dollar the same. MAE is still reported so a single outlier is visible.

## 4. Corrective action

{diagnosis["action"]}
"""
    path.write_text(text, encoding="utf-8")


def main() -> None:
    history = training_history()
    folds = evaluate_folds(history)
    summary = summarize(folds)
    curve = learning_curve_points(history)
    diagnosis = diagnose(curve, summary)
    save_learning_curve(curve, OUTPUT_DIR / "learning_curve.png")
    write_report(OUTPUT_DIR / "evaluation_report.md", folds, summary, curve, diagnosis)
    payload = {"primary_metric": PRIMARY_METRIC, "summary": summary, "diagnosis": diagnosis["label"], "folds": folds, "curve": curve}
    (OUTPUT_DIR / "evaluation_summary.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"diagnosis": diagnosis["label"], "val_rmse": summary["val_rmse"]["text"], "val_mae": summary["val_mae"]["text"]}, indent=2))


if __name__ == "__main__":
    main()
