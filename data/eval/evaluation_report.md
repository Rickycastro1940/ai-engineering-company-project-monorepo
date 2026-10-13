# Brasaland sales forecast — technical evaluation

Audience: Mariana Restrepo, Felipe Guerrero, Lucía Fernández. Series: `data/raw/brasaland_sales.csv`. Model: scikit-learn random forest from `scripts/train_sales_forecast.py` (`max_depth=4`, `min_samples_leaf=2`, `random_state=42`). The 2024–2025 holdout is not used in these folds.

## 1. Fit

**Diagnosis: overfitting.**

The learning curve (`data/eval/learning_curve.png`) plots training RMSE and the RMSE of a 12-month forward forecast as the training prefix grows from 36 to 84 months inside 2016–2023.

| Training months | Train RMSE | Validation RMSE | Train MAE | Validation MAE |
| --- | --- | --- | --- | --- |
| 36 | 8,194 | 41,147 | 6,762 | 34,310 |
| 48 | 10,634 | 31,398 | 8,604 | 26,679 |
| 60 | 12,371 | 31,063 | 10,087 | 25,871 |
| 72 | 14,626 | 29,213 | 11,779 | 22,473 |
| 84 | 15,710 | 54,797 | 12,588 | 48,946 |

On the longest prefix the training RMSE is 15,710 USD and the next-12-month RMSE is 54,797 USD (gap 39,087 USD, ratio 3.49).

## 2. Stability

Temporal cross-validation is `TimeSeriesSplit` with 5 folds and a 12-month validation window. Folds are not shuffled. Features for a validation month are built from earlier months only; once the window starts, later months see the forecast, not the actual revenue.

Primary metric is **RMSE**, reported as mean ± standard deviation across the 5 validation windows: **37,524 ± 9,590 USD**. The standard deviation is the stability result: validation RMSE runs from 29,213 to 54,797 USD. Windows for 2020, 2021, and 2022 sit near 30,000 USD. The 2023 window is the one that jumps.

| Fold | Train through | Validation window | Train RMSE | Val RMSE | Train MAE | Val MAE |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 2018-12-01 | 2019-01-01 → 2019-12-01 | 8,194 | 41,147 | 6,762 | 34,310 |
| 2 | 2019-12-01 | 2020-01-01 → 2020-12-01 | 10,634 | 31,398 | 8,604 | 26,679 |
| 3 | 2020-12-01 | 2021-01-01 → 2021-12-01 | 12,371 | 31,063 | 10,087 | 25,871 |
| 4 | 2021-12-01 | 2022-01-01 → 2022-12-01 | 14,626 | 29,213 | 11,779 | 22,473 |
| 5 | 2022-12-01 | 2023-01-01 → 2023-12-01 | 15,710 | 54,797 | 12,588 | 48,946 |

| Metric | Training (mean ± std) | Validation (mean ± std) |
| --- | --- | --- |
| RMSE (primary) | 12,307 ± 2,708 | 37,524 ± 9,590 |
| MAE | 9,964 ± 2,112 | 31,656 ± 9,472 |

## 3. Why RMSE, not MAE

`CONTEXT-company.md` says underestimating sales is the costlier error. Felipe buys from the forecast. December runs about 20–30% above the rest of the year; a low call that month stocks the kitchens out and the cover is lost. Overestimating raises waste, which the next order can trim. RMSE weights a large December miss more than MAE, which treats every dollar the same. MAE is still reported so a single outlier is visible.

## 4. Corrective action

The training error is low and the forward validation error stays about 3.5× higher on the longest prefix. Lower `max_depth` from 4 to 3 and raise `min_samples_leaf` from 2 to 4 before adding more years. Do not add depth.
