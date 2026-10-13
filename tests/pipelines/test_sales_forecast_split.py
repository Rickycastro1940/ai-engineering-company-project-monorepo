"""8-year / 2-year split for the Brasaland sales forecast."""

from __future__ import annotations

from data.process.sales_forecast import (
    SERIES_START,
    TRAIN_CUTOFF_YEAR,
    build_features,
    drop_warmup,
    load_sales,
    split_by_year,
)


def test_split_respects_8_2_rule_and_no_leakage():
    train, test = split_by_year(load_sales())
    train_years = set(train["month"].dt.year)
    test_years = set(test["month"].dt.year)

    assert test_years == {2024, 2025}
    assert train_years == set(range(2016, 2024))
    assert len(test_years) == 2
    assert len(train_years) == 8
    assert train_years.isdisjoint(test_years)
    assert max(train_years) < min(test_years)
    assert set(train["month"]).isdisjoint(set(test["month"]))


def test_feature_warmup_does_not_pull_test_years_into_training():
    raw = load_sales()
    ready = drop_warmup(build_features(raw))
    train, test = split_by_year(ready, origin_year=SERIES_START.year)

    assert int(train["month"].dt.year.max()) < TRAIN_CUTOFF_YEAR
    assert set(test["month"].dt.year) == {2024, 2025}
    assert train["month"].max() < test["month"].min()
    # 2016 cannot form a 12-month lag; it stays out of both sides.
    assert 2016 not in set(train["month"].dt.year)
    assert len(set(train["month"].dt.year)) >= 6
