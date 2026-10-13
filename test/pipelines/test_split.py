"""Training/test split for Brasaland monthly sales: 8 years, then 2.

The holdout is 2024–2025. No month from those years may appear in training.
"""

from __future__ import annotations

from data.process.sales_forecast import (
    SERIES_START,
    TRAIN_YEARS,
    build_features,
    drop_warmup,
    load_sales,
    split_by_year,
)


def test_split_respects_8_2_rule_and_no_leakage():
    sales = load_sales()
    train, test = split_by_year(sales)
    train_years = set(train["month"].dt.year)
    test_years = set(test["month"].dt.year)

    assert len(train_years) == TRAIN_YEARS
    assert train_years == set(range(2016, 2024))
    assert len(test_years) == 2
    assert test_years == {2024, 2025}
    assert train_years.isdisjoint(test_years)
    assert max(train_years) < min(test_years)

    train_months = set(train["month"])
    test_months = set(test["month"])
    assert train_months.isdisjoint(test_months)
    assert train_months | test_months == set(sales["month"])
    assert len(train) + len(test) == len(sales)


def test_fitted_rows_still_exclude_the_two_test_years():
    """Lag warmup may drop 2016. It must not pull 2024 or 2025 into training."""

    ready = drop_warmup(build_features(load_sales()))
    train, test = split_by_year(ready, origin_year=SERIES_START.year)

    assert set(test["month"].dt.year) == {2024, 2025}
    assert train["month"].max() < test["month"].min()
    assert set(train["month"]).isdisjoint(set(test["month"]))
    assert 2024 not in set(train["month"].dt.year)
    assert 2025 not in set(train["month"].dt.year)
