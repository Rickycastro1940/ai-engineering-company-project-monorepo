"""Brasaland monthly sales forecast features and metrics.

Department need: Restaurant Operations (Felipe Guerrero — anticipate
ingredient demand), Procurement (Lucía Fernández — volume ahead of meat
buys), and Executive (Mariana Restrepo — chain sales before a dashboard).

Source file: ``data/raw/brasaland_sales.csv`` (official series, not
simulated here). Column contract and seasonality are the sales-forecasting
brief for Brasaland:

- ``month`` (YYYY-MM-01), ``revenue_usd``, ``covers_served``,
  ``avg_ticket_usd``, ``market`` (this file is ``consolidated`` only).
- Target: ``revenue_usd``.
- Range: 2016-01 through 2025-12 (120 months).
- Growth about 5% a year, alternating near 3% and 7%.
- January is 12–18% under the prior-year average; December is 20–30%
  above the year's average. Other months stay near the trend.

Illustrative COP view uses 1 USD = 4,000 COP. That rate is a label for
leadership, not a live FX feed. Colombia and Florida are already combined
in ``revenue_usd``; Florida is the smaller market and is not a separate
series in this file.
"""

from __future__ import annotations

from pathlib import Path

import re

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.preprocessing import StandardScaler

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SALES_PATH = REPO_ROOT / "data" / "raw" / "brasaland_sales.csv"

# First day of each month in the official file.
SERIES_START = pd.Timestamp("2016-01-01")
SERIES_END = pd.Timestamp("2025-12-01")
TRAIN_YEARS = 8
TEST_YEARS = 2
# Hold out 2024-01 .. 2025-12. 2016 is available for lags only.
TRAIN_CUTOFF_YEAR = SERIES_START.year + TRAIN_YEARS

SEED = 42
# Documented illustrative rate from the sales-forecasting brief.
ILLUSTRATIVE_COP_PER_USD = 4000

EXPECTED_COLUMNS = (
    "month",
    "revenue_usd",
    "covers_served",
    "avg_ticket_usd",
    "market",
)

# Used by the regressor. None of these read the current month's revenue.
FEATURE_COLUMNS = (
    "revenue_lag_1",
    "revenue_lag_12",
    "revenue_roll_mean_3",
    "revenue_roll_std_12",
    "covers_lag_1",
    "avg_ticket_lag_1",
    "month_sin",
    "month_cos",
    "quarter",
)

TARGET_COLUMN = "revenue_usd"


def sales_columns_in_context(path: Path | str | None = None) -> tuple[str, ...]:
    """Column names from the monthly-sales table in ``CONTEXT-company.md``."""

    context_path = Path(path) if path is not None else REPO_ROOT / "CONTEXT-company.md"
    text = context_path.read_text(encoding="utf-8")
    marker = "## Monthly consolidated sales"
    start = text.find(marker)
    if start < 0:
        raise ValueError("CONTEXT-company.md has no monthly consolidated sales section")
    section = text[start:].split("\n## ", 1)[0]
    columns = tuple(re.findall(r"^\| `([a-z0-9_]+)` \|", section, flags=re.MULTILINE))
    if columns != EXPECTED_COLUMNS:
        raise ValueError(
            "CONTEXT-company.md sales columns "
            f"{columns} do not match the loader contract {EXPECTED_COLUMNS}"
        )
    return columns


def load_sales(path: Path | str | None = None) -> pd.DataFrame:
    """Load the consolidated monthly series and reject a broken file.

    Columns must match the monthly-sales table in ``CONTEXT-company.md``.
    Null and blank cells are dropped before any split or scaling.
    """

    csv_path = Path(path) if path is not None else DEFAULT_SALES_PATH
    documented = sales_columns_in_context()
    frame = pd.read_csv(csv_path)
    header = tuple(frame.columns)
    if header != documented:
        raise ValueError(
            f"brasaland_sales.csv columns {header} do not match "
            f"CONTEXT-company.md {documented}"
        )

    frame = frame.loc[:, list(EXPECTED_COLUMNS)].copy()
    for name in ("month", "market"):
        frame[name] = frame[name].replace(r"^\s*$", np.nan, regex=True)
    frame["revenue_usd"] = pd.to_numeric(frame["revenue_usd"], errors="coerce")
    frame["covers_served"] = pd.to_numeric(frame["covers_served"], errors="coerce")
    frame["avg_ticket_usd"] = pd.to_numeric(frame["avg_ticket_usd"], errors="coerce")
    before = len(frame)
    frame = frame.dropna(subset=list(EXPECTED_COLUMNS))
    dropped = before - len(frame)
    if dropped:
        frame.attrs["null_rows_dropped"] = dropped

    frame["month"] = pd.to_datetime(frame["month"], format="%Y-%m-%d")
    frame = frame.sort_values("month").drop_duplicates("month", keep="last")
    frame = frame.reset_index(drop=True)

    if not (frame["revenue_usd"] > 0).all():
        raise ValueError("revenue_usd must stay positive")

    consolidated = frame[frame["market"] == "consolidated"].reset_index(drop=True)
    if consolidated.empty:
        raise ValueError("no consolidated rows to forecast")
    return consolidated


def assert_official_calendar(frame: pd.DataFrame) -> None:
    """The provided series is 120 consecutive months, 2016-01 to 2025-12."""

    months = frame["month"]
    expected = pd.date_range(SERIES_START, SERIES_END, freq="MS")
    if len(frame) != len(expected) or not months.equals(pd.Series(expected)):
        raise ValueError(
            "brasaland_sales.csv must stay the official 2016-01..2025-12 "
            "monthly series (120 consolidated rows, no gaps)"
        )


def build_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Lag, rolling, and calendar features using only earlier months.

    Rolling windows run on ``shift(1)`` so month ``t`` never sees ``revenue_usd``
    at ``t`` or later. Calendar features use the month stamp, which is known
    before the month's sales exist.
    """

    out = frame.copy()
    revenue = out[TARGET_COLUMN]
    past = revenue.shift(1)
    out["revenue_lag_1"] = past
    out["revenue_lag_12"] = revenue.shift(12)
    out["revenue_roll_mean_3"] = past.rolling(3, min_periods=3).mean()
    out["revenue_roll_std_12"] = past.rolling(12, min_periods=12).std()
    out["covers_lag_1"] = out["covers_served"].shift(1)
    out["avg_ticket_lag_1"] = out["avg_ticket_usd"].shift(1)

    month_number = out["month"].dt.month.astype(float)
    out["month_sin"] = np.sin(2 * np.pi * month_number / 12.0)
    out["month_cos"] = np.cos(2 * np.pi * month_number / 12.0)
    out["quarter"] = out["month"].dt.quarter.astype(float)
    return out


def scale_features(
    train: pd.DataFrame,
    test: pd.DataFrame,
    columns: tuple[str, ...] = FEATURE_COLUMNS,
) -> tuple[np.ndarray, np.ndarray, StandardScaler]:
    """Scale model inputs. The scaler is fit on the training years only."""

    scaler = StandardScaler()
    x_train = scaler.fit_transform(train.loc[:, list(columns)])
    x_test = scaler.transform(test.loc[:, list(columns)])
    return x_train, x_test, scaler


def drop_warmup(frame: pd.DataFrame) -> pd.DataFrame:
    """Drop the opening months that cannot yet form a 12-month lag."""

    ready = frame.dropna(subset=list(FEATURE_COLUMNS)).reset_index(drop=True)
    return ready


def split_by_year(
    frame: pd.DataFrame,
    origin_year: int | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Train on the first 8 calendar years; test on the last 2.

    ``origin_year`` defaults to the earliest year in ``frame``. Pass
    ``SERIES_START.year`` when warmup rows were already removed so the
    cutoff stays 2024 instead of sliding forward.
    """

    if frame.empty:
        raise ValueError("cannot split an empty sales frame")
    origin = SERIES_START.year if origin_year is None else int(origin_year)
    # Raw load starts in 2016, so the default matches the 8/2 rule.
    if origin_year is None:
        origin = int(frame["month"].dt.year.min())
    cutoff = origin + TRAIN_YEARS
    years = frame["month"].dt.year
    train = frame.loc[years < cutoff].reset_index(drop=True)
    test = frame.loc[years >= cutoff].reset_index(drop=True)
    if train.empty or test.empty:
        raise ValueError(
            f"split produced an empty side (origin={origin}, cutoff={cutoff})"
        )
    return train, test


def population_stability_index(
    expected: np.ndarray,
    actual: np.ndarray,
    bins: int = 10,
) -> float:
    """PSI of ``actual`` against the ``expected`` (training) distribution.

    Below 0.10 is stable, 0.10–0.25 is a moderate shift, above 0.25 is a
    large shift. A growing restaurant chain should show some shift; the
    report says whether that shift is the documented 3–7% growth.
    """

    expected = np.asarray(expected, dtype=float)
    actual = np.asarray(actual, dtype=float)
    quantiles = np.linspace(0.0, 1.0, bins + 1)
    cuts = np.quantile(expected, quantiles)
    cuts = np.unique(cuts)
    if len(cuts) < 3:
        return 0.0
    cuts[0] = -np.inf
    cuts[-1] = np.inf
    expected_counts = np.histogram(expected, bins=cuts)[0].astype(float)
    actual_counts = np.histogram(actual, bins=cuts)[0].astype(float)
    expected_share = expected_counts / expected_counts.sum()
    actual_share = actual_counts / max(actual_counts.sum(), 1.0)
    expected_share = np.clip(expected_share, 1e-6, None)
    actual_share = np.clip(actual_share, 1e-6, None)
    expected_share = expected_share / expected_share.sum()
    actual_share = actual_share / actual_share.sum()
    psi = np.sum((actual_share - expected_share) * np.log(actual_share / expected_share))
    return float(psi)


def _gini_raw(actual: np.ndarray, pred: np.ndarray) -> float:
    """Gini of ``actual`` when rows are ordered by ``pred`` (descending)."""

    actual = np.asarray(actual, dtype=float)
    pred = np.asarray(pred, dtype=float)
    order = np.lexsort((np.arange(len(actual)), -pred))
    sorted_actual = actual[order]
    total = sorted_actual.sum()
    if total == 0:
        return 0.0
    cumulative = np.cumsum(sorted_actual)
    gini_sum = cumulative.sum() / total
    gini_sum -= (len(actual) + 1) / 2.0
    return float(gini_sum / len(actual))


def normalized_gini(actual: np.ndarray, pred: np.ndarray) -> float:
    """1 when predictions rank months exactly like actual sales; 0 when random.

    A low Gini means the model does not separate strong months (December)
    from weak ones (January) even if squared error looks small.
    """

    perfect = _gini_raw(actual, actual)
    if perfect == 0:
        return 0.0
    return float(_gini_raw(actual, pred) / perfect)


def k2_score(residuals: np.ndarray) -> tuple[float, float]:
    """D'Agostino-Pearson K² on forecast residuals, plus the p-value.

    K² near the chi-square center (and a large p-value) means residuals
    are compatible with a symmetric, non-skewed error. A tiny p-value
    means the errors lean — usually the model is systematically high or
    low in a season.
    """

    residuals = np.asarray(residuals, dtype=float)
    residuals = residuals[np.isfinite(residuals)]
    if len(residuals) < 8:
        raise ValueError("K² needs at least 8 residuals")
    statistic, p_value = stats.normaltest(residuals)
    return float(statistic), float(p_value)


def mean_absolute_percentage_error(actual: np.ndarray, pred: np.ndarray) -> float:
    """Average absolute percent error. This is the figure Finance can read."""

    actual = np.asarray(actual, dtype=float)
    pred = np.asarray(pred, dtype=float)
    return float(np.mean(np.abs(actual - pred) / actual) * 100.0)


def seasonality_check(frame: pd.DataFrame) -> dict[str, float]:
    """Compare January and December to the pattern in the sales brief.

    January drop is versus the previous calendar year's average.
    December rise is versus the same calendar year's average.
    """

    work = frame.copy()
    work["year"] = work["month"].dt.year
    annual = work.groupby("year")[TARGET_COLUMN].mean()
    january_gaps: list[float] = []
    december_lifts: list[float] = []
    for year, block in work.groupby("year"):
        january = block.loc[block["month"].dt.month == 1, TARGET_COLUMN]
        december = block.loc[block["month"].dt.month == 12, TARGET_COLUMN]
        if len(january) and (year - 1) in annual.index:
            previous = float(annual.loc[year - 1])
            january_gaps.append(float(january.iloc[0]) / previous - 1.0)
        if len(december):
            baseline = float(annual.loc[year])
            december_lifts.append(float(december.iloc[0]) / baseline - 1.0)

    yoy: list[float] = []
    yearly_sum = work.groupby("year")[TARGET_COLUMN].sum()
    for year in yearly_sum.index[1:]:
        yoy.append(float(yearly_sum.loc[year] / yearly_sum.loc[year - 1] - 1.0))

    return {
        "january_vs_prior_year_mean": float(np.mean(january_gaps)),
        "december_vs_same_year_mean": float(np.mean(december_lifts)),
        "median_yoy_growth": float(np.median(yoy)),
        "min_yoy_growth": float(np.min(yoy)),
        "max_yoy_growth": float(np.max(yoy)),
    }
