# Brasaland monthly sales forecast

Serves Mariana Restrepo (chain sales), Felipe Guerrero (purchasing), and Lucía Fernández (volume). The series is `data/raw/brasaland_sales.csv`. Column names match the monthly sales table in `CONTEXT-company.md`: `month`, `revenue_usd`, `covers_served`, `avg_ticket_usd`, `market`.

Train with:

```bash
uv run python scripts/train_sales_forecast.py
```

## Model

`sklearn.ensemble.RandomForestRegressor` from scikit-learn (`n_estimators=300`, `max_depth=4`, `min_samples_leaf=2`, `random_state=42`).

Why this algorithm:

- Explainability. The forecast is the average of the trees. The shaded band on the chart is how far those trees disagree.
- Data size. 120 monthly rows, with about 84 used for fitting, is a small sample.
- Tuning time. XGBoost would need a search over learning rate and depth. That search is not worth it on this series.

The forest predicts the year-over-year factor. Dollar revenue is that factor times the same month last year. The holdout is 2024 and 2025. The scaler is fit on the training years only.

## Test metrics

Numbers from the latest run are in `metrics.md`. All of them are on 2024–2025, not on the training years.

| Metric | What it measures |
| --- | --- |
| MSE | Average squared gap between forecast and actual revenue, in USD². |
| PSI | Population Stability Index. How far the test distribution moved from the training distribution. The reported PSI is on the year-over-year factor. The dollar-level PSI is also stored, because growth alone pushes later years into the top training decile. |
| Gini | Whether the forecast ranks high months above low months. 1 is a perfect ranking of December above January. |
| K2 Score | D'Agostino-Pearson K² on the test residuals. A large p-value means those errors are compatible with a symmetric scatter. |

A low MSE on its own is not enough. A model can sit near the average level, post a small squared error, and still miss which months are the strong ones. Gini checks that ranking. PSI checks whether 2024–2025 still behave like the training years. The K2 Score checks whether the misses lean high or low instead of scattering evenly.

## Chart

`forecast_vs_actual.png` plots actual consolidated revenue for the two test years, the forest forecast, and the variability band (one standard deviation across the trees). `decomposition.png` is the diagnostic split into trend, seasonality, and residual. It is not the forecast.
