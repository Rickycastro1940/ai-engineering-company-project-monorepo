"""Chronological folds for the Brasaland sales-forest evaluation."""

from __future__ import annotations

from data.process.sales_forecast_eval import (
    N_SPLITS,
    fold_is_chronological,
    temporal_folds,
    training_history,
)


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
        train_months = history.iloc[list(train_idx)]["month"]
        val_months = history.iloc[list(val_idx)]["month"]
        assert train_months.max() < val_months.min()

    years = set(history["month"].dt.year)
    assert years == set(range(2016, 2024))
    assert 2024 not in years
    assert 2025 not in years
