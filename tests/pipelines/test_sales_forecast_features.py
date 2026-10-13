"""Causal lag and rolling features for the Brasaland sales forecast."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from data.process.sales_forecast import (
    FEATURE_COLUMNS,
    TARGET_COLUMN,
    assert_official_calendar,
    build_features,
    load_sales,
    sales_columns_in_context,
)


def test_official_series_is_unchanged_calendar():
    frame = load_sales()
    assert_official_calendar(frame)
    assert (frame["revenue_usd"] > 0).all()
    assert set(frame["market"]) == {"consolidated"}
    assert list(frame.columns) == [
        "month",
        "revenue_usd",
        "covers_served",
        "avg_ticket_usd",
        "market",
    ]


def test_csv_header_matches_context_company_and_blanks_drop(tmp_path):
    documented = sales_columns_in_context()
    assert documented == (
        "month",
        "revenue_usd",
        "covers_served",
        "avg_ticket_usd",
        "market",
    )
    header = ",".join(documented)
    target = tmp_path / "brasaland_sales.csv"
    target.write_text(
        "\n".join(
            [
                header,
                "2016-01-01,420817.2,37946,11.09,consolidated",
                "2016-02-01,,10,1,consolidated",
                " ,100,10,1, ",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    loaded = load_sales(target)
    assert len(loaded) == 1
    assert loaded.iloc[0]["revenue_usd"] == pytest.approx(420817.2)


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
