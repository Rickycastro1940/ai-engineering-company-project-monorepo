"""Chronological folds for the Brasaland sales-forest evaluation."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.model_selection import TimeSeriesSplit

from data.process.sales_forecast import FEATURE_COLUMNS, TARGET_COLUMN, build_features
from data.process.sales_forecast_eval import (
    N_SPLITS,
    fold_is_chronological,
    summarize,
    temporal_folds,
    training_history,
)


def test_temporal_cv_uses_time_series_split_with_five_folds():
    history = training_history()
    folds = list(temporal_folds(len(history), N_SPLITS))
    expected = list(TimeSeriesSplit(n_splits=5, test_size=12).split(range(len(history))))

    assert len(folds) == 5
    assert len(expected) == 5
    for (train_idx, val_idx), (expected_train, expected_val) in zip(folds, expected):
        assert list(train_idx) == list(expected_train)
        assert list(val_idx) == list(expected_val)


def test_temporal_cv_preserves_chronological_order():
    history = training_history()
    folds = list(temporal_folds(len(history), N_SPLITS))
    assert len(folds) >= 5

    previous_val_end = -1
    for train_idx, val_idx in folds:
        assert fold_is_chronological(train_idx, val_idx)
        assert list(train_idx) == sorted(int(i) for i in train_idx)
        assert list(val_idx) == sorted(int(i) for i in val_idx)
        assert max(train_idx) < min(val_idx)
        assert min(val_idx) > previous_val_end
        previous_val_end = max(val_idx)
        assert max(val_idx) > max(train_idx)
        # No index from a later fold appears in this fold's training rows.
        assert set(train_idx).isdisjoint(set(val_idx))
        train_months = history.iloc[list(train_idx)]["month"]
        val_months = history.iloc[list(val_idx)]["month"]
        assert train_months.max() < val_months.min()
        assert train_months.is_monotonic_increasing
        assert val_months.is_monotonic_increasing

    years = set(history["month"].dt.year)
    assert years == set(range(2016, 2024))
    assert 2024 not in years
    assert 2025 not in years


def test_lag_and_rolling_features_do_not_cross_the_fold_boundary():
    """Validation actuals must not become the next month's lag inside the fold.

    Building lags on the full series first would do that: month two of the
    validation window would see month one's actual revenue. The fold forecast
    carries the prediction instead.
    """

    history = training_history()
    train_idx, val_idx = next(temporal_folds(len(history), N_SPLITS))
    prefix = history.iloc[list(train_idx)].reset_index(drop=True)
    horizon = history.iloc[list(val_idx)].reset_index(drop=True)
    past = prefix[TARGET_COLUMN]

    first = horizon.iloc[0].copy()
    first[TARGET_COLUMN] = np.nan
    first_features = build_features(pd.concat([prefix, pd.DataFrame([first])], ignore_index=True)).iloc[-1]
    assert first_features["revenue_lag_1"] == past.iloc[-1]
    assert first_features["revenue_lag_12"] == past.iloc[-12]
    assert np.isclose(first_features["revenue_roll_mean_3"], past.iloc[-3:].mean())

    leaked = build_features(history).iloc[int(val_idx[1])]
    assert leaked["revenue_lag_1"] == history.iloc[int(val_idx[0])][TARGET_COLUMN]

    carried = horizon.iloc[0].copy()
    carried[TARGET_COLUMN] = -1.0
    second = horizon.iloc[1].copy()
    second[TARGET_COLUMN] = np.nan
    step = pd.concat([prefix, pd.DataFrame([carried, second])], ignore_index=True)
    safe = build_features(step).iloc[-1]
    assert safe["revenue_lag_1"] == -1.0
    assert safe["revenue_lag_1"] != history.iloc[int(val_idx[0])][TARGET_COLUMN]
    assert max(train_idx) < min(val_idx)


def test_primary_metric_is_reported_as_mean_and_std():
    summary = summarize(
        [
            {"train_mae": 1, "train_rmse": 2, "val_mae": 3, "val_rmse": 10},
            {"train_mae": 1, "train_rmse": 4, "val_mae": 5, "val_rmse": 20},
        ]
    )
    assert summary["val_rmse"]["mean"] == 15
    assert summary["val_rmse"]["std"] == 5
    assert summary["val_rmse"]["text"] == "15 ± 5"
