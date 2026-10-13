# Brasaland sales forecast — test metrics

Audience: Mariana Restrepo (chain sales), Felipe Guerrero (covers and purchasing), Lucía Fernández (volume). Currency in the model is consolidated USD. An illustrative COP column uses 1 USD = 4,000 COP and is not a live exchange rate.

## Model

Random forest (`n_estimators=300`, `max_depth=4`, `min_samples_leaf=2`, `random_state=42`).

Chosen over XGBoost because the series has 120 months and Finance asked for an explainable range. The forest averages trees; the chart band is the standard deviation across those trees, scaled back into dollars. XGBoost would need more tuning than this sample supports, and sequential boosting is harder to walk through in a Monday meeting.

The forest predicts the year-over-year factor (this month ÷ the same month last year). The dollar forecast is that factor times last year's same month. Trees cannot invent a higher dollar level than they saw in training; the brief's growth is a multiplier, and the December spike is already stored in last December.

Scaler: `StandardScaler` fit on the training months only, then applied to 2024–2025.

Warmup rows dropped before the split (12-month lag): 12. Training uses 2017-01-01 through 2023-12-01 (84 months). The holdout is 2024-01-01 through 2025-12-01 (24 months), which is the last two years (cutoff year 2024).

## What the series already contains

Additive seasonal component matches the brief: December averages 128,096 USD above the trend and January averages -90,682 USD below it.

| Check | Value | Brief |
| --- | --- | --- |
| Mean January vs prior-year average | -12.0% | drop of about 12–18% |
| Mean December vs same-year average | 23.0% | rise of about 20–30% |
| Median year-over-year growth | 5.1% | base growth about 5% |
| Year-over-year range | 2.6% to 9.0% | generation band is about 3–7%; annual totals move a bit wider because December and January have different weights |

## Test-set metrics

All four required metrics are computed on 2024–2025 only.

| Metric | Value | How to read it |
| --- | --- | --- |
| MSE | 1,274,710,813 USD² | Average squared miss. Sensitive to a bad December. A low training MSE would not be reported here. |
| RMSE | 35,703 USD | Typical miss in dollars (square root of MSE). |
| MAPE | 3.8% | Average percent miss. This is the figure Felipe and Mariana can use. |
| PSI | 0.356 | large shift (over 0.25). Compares the year-over-year factor in training with 2024–2025. Dollar-level PSI is 8.612 because growth puts most test months in the top training decile; that is the 5% path, not a new season. |
| Gini | 0.730 | 1 means the forecast ranks months in the same order as actual sales. A low Gini means December and January are not distinguished. |
| K² | 0.114 (p=0.945) | D'Agostino-Pearson test on test residuals. A small p-value means the errors are skewed rather than symmetric. |

A low MSE on its own is not enough. The forest can sit near the average level (small squared error) and still miss which months are strong. Gini checks that ranking. PSI checks whether 2024–2025 still look like the training years. K² checks whether the misses lean high or low instead of scattering evenly.

## What the forest uses

| Feature | Importance |
| --- | --- |
| `revenue_lag_12` | 0.244 |
| `revenue_roll_std_12` | 0.196 |
| `revenue_roll_mean_3` | 0.169 |
| `avg_ticket_lag_1` | 0.119 |
| `covers_lag_1` | 0.095 |
| `month_cos` | 0.070 |
| `revenue_lag_1` | 0.054 |
| `month_sin` | 0.043 |
| `quarter` | 0.010 |

Lag and rolling features are built with `shift` before `rolling`, so a month does not see its own revenue. Same-month covers and average ticket are not features: together they reconstruct revenue.
