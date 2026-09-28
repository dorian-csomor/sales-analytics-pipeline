"""
Small, reusable cleansing helpers. Each function does one thing and is unit tested
(see tests/test_cleaning.py).
"""

from __future__ import annotations

import re
from datetime import datetime

import pandas as pd


def clean_text(s: pd.Series) -> pd.Series:
    """Trim and collapse repeated whitespace. Empty strings become missing values."""
    out = s.astype("string").str.strip().str.replace(r"\s+", " ", regex=True)
    return out.mask(out == "")


def match_key(s: pd.Series) -> pd.Series:
    """Aggressive normalisation for matching duplicates: lower case, letters/digits only."""
    return (clean_text(s).str.lower()
            .str.replace(r"[^\w\s]", "", regex=True)
            .str.replace(r"\s+", " ", regex=True)
            .str.strip())


def sku_key(s: pd.Series) -> pd.Series:
    """'hx-1001 ', 'HX1001' and 'HX-1001' all become 'HX1001'."""
    return s.astype("string").str.upper().str.replace(r"[^A-Z0-9]", "", regex=True)


def title_case_if_shouting(s: pd.Series) -> pd.Series:
    """Fix names typed in ALL CAPS, leave normal names alone ('Kft.' stays 'Kft.')."""
    s = clean_text(s)
    shouting = s.str.isupper().fillna(False)
    return s.where(~shouting, s.str.title())


def parse_mixed_dates(raw: pd.Series, formats: list[str]) -> pd.Series:
    """
    Parse a text column that mixes several date formats.
    Each format is tried in order on the values that are still unparsed, so a value
    is never interpreted by two formats. Returns datetime64 (NaT where nothing matched).
    """
    text = raw.astype("string").str.strip()
    result = pd.Series(pd.NaT, index=raw.index, dtype="datetime64[ns]")
    for fmt in formats:
        todo = result.isna() & text.notna()
        if not todo.any():
            break
        result.loc[todo] = pd.to_datetime(text[todo], format=fmt, errors="coerce")
    return result


def map_with_aliases(s: pd.Series, aliases: dict[str, str], lower: bool = True) -> pd.Series:
    """Map free-text values to canonical ones. Unknown values become missing."""
    key = clean_text(s)
    key = key.str.lower() if lower else key.str.upper()
    return key.map(aliases).astype("string")


def fix_percentage_scale(s: pd.Series) -> tuple[pd.Series, pd.Series]:
    """
    Discounts should be fractions (0.10). Values above 1 were typed as whole
    percentages (10) and are divided by 100. Returns (fixed series, mask of fixed rows).
    """
    s = pd.to_numeric(s, errors="coerce")
    mask = s > 1
    return s.where(~mask, s / 100), mask


def to_date_key(dates: pd.Series) -> pd.Series:
    """datetime -> integer YYYYMMDD key (nullable)."""
    d = pd.to_datetime(dates)
    return (d.dt.year * 10000 + d.dt.month * 100 + d.dt.day).astype("Int64")


def build_date_dimension(start: str, end: str) -> pd.DataFrame:
    dates = pd.date_range(start, end, freq="D")
    return pd.DataFrame({
        "date_key": (dates.year * 10000 + dates.month * 100 + dates.day).astype(int),
        "date": dates.date,
        "year": dates.year,
        "quarter": "Q" + dates.quarter.astype(str),
        "month_number": dates.month,
        "month_name": dates.strftime("%B"),
        "month_short": dates.strftime("%b"),
        "year_month": dates.strftime("%Y-%m"),
        "iso_week": dates.isocalendar().week.to_numpy(),
        "day_of_week": dates.dayofweek + 1,
        "day_name": dates.strftime("%A"),
        "is_weekend": dates.dayofweek >= 5,
    })


def now_run_id() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def compile_pattern(pattern: str) -> re.Pattern:
    return re.compile(pattern, flags=re.IGNORECASE)
