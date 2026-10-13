"""Causal lag and rolling features for the Brasaland sales forecast."""

from __future__ import annotations

import numpy as np
import pandas as pd

from data.process.sales_forecast import (
    FEATURE_COLUMNS,
    TARGET_COLUMN,
    assert_official_calendar,
    build_features,
    load_sales,
)


def test_official_series_is_unchanged_calendar():
    frame = load_sales()
    assert_official_calendar(frame)
    assert (frame["revenue_usd"] > 0).all()
    assert set(frame["market"]) == {"consolidated"}


def test_lag_feature_is_causal():
    raw = load_sales()
    featured = build_features(raw)
    revenue = featured[TARGET_COLUMN]
    lag = featured["revenue_lag_1"]

    assert pd.isna(lag.iloc[0])
    for index in range(1, len(featured)):
        assert lag.iloc[index] == revenue.iloc[index - 1]
        assert lag.iloc[index] != revenue.iloc[index]


def test_lag_12_matches_same_month_last_year():
    featured = build_features(load_sales())
    revenue = featured[TARGET_COLUMN]
    lag = featured["revenue_lag_12"]
    assert lag.iloc[:12].isna().all()
    for index in range(12, len(featured)):
        assert lag.iloc[index] == revenue.iloc[index - 12]


def test_rolling_mean_uses_only_past_months():
    featured = build_features(load_sales())
    revenue = featured[TARGET_COLUMN]
    rolling = featured["revenue_roll_mean_3"]
    expected = revenue.shift(1).rolling(3, min_periods=3).mean()
    pd.testing.assert_series_equal(rolling, expected, check_names=False)

    # Row t's window is revenue[t-3], revenue[t-2], revenue[t-1] — not t.
    for index in range(3, len(featured)):
        window = revenue.iloc[index - 3 : index]
        assert np.isclose(rolling.iloc[index], window.mean())
        assert revenue.iloc[index] not in set(window)


def test_calendar_features_are_known_from_the_month_stamp():
    featured = build_features(load_sales())
    january = featured.loc[featured["month"].dt.month == 1].iloc[0]
    december = featured.loc[featured["month"].dt.month == 12].iloc[0]
    assert january["quarter"] == 1
    assert december["quarter"] == 4
    assert np.isclose(january["month_sin"], np.sin(2 * np.pi * 1 / 12))
    assert "month_sin" in FEATURE_COLUMNS
    assert "revenue_roll_mean_3" in FEATURE_COLUMNS
    assert "revenue_lag_1" in FEATURE_COLUMNS
    assert TARGET_COLUMN not in FEATURE_COLUMNS
