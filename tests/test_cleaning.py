"""Unit tests for the cleansing helpers. Run with:  python -m pytest"""

import pandas as pd

from etl.cleaning import (build_date_dimension, clean_text, fix_percentage_scale, map_with_aliases,
                          match_key, parse_mixed_dates, sku_key, title_case_if_shouting, to_date_key)
from etl.reference import COUNTRY_ALIASES, ORDER_DATE_FORMATS, STATUS_ALIASES


def test_parse_mixed_dates_handles_every_source_format():
    raw = pd.Series(["2025-03-14T10:22:05", "2025-03-14", "2025.03.14.", "14.03.2025", "14/03/2025"])
    parsed = parse_mixed_dates(raw, ORDER_DATE_FORMATS).dt.normalize()
    assert (parsed == pd.Timestamp("2025-03-14")).all()


def test_parse_mixed_dates_leaves_garbage_empty():
    parsed = parse_mixed_dates(pd.Series(["not a date", None, "31.02.2025"]), ORDER_DATE_FORMATS)
    assert parsed.isna().all()


def test_clean_text_trims_and_collapses_spaces():
    out = clean_text(pd.Series(["  Danube   Logistics Kft. ", "", None]))
    assert out[0] == "Danube Logistics Kft."
    assert out[1:].isna().all()


def test_title_case_only_changes_all_caps_names():
    out = title_case_if_shouting(pd.Series(["DANUBE LOGISTICS KFT.", "Nova Hotels GmbH"]))
    assert list(out) == ["Danube Logistics Kft.", "Nova Hotels GmbH"]


def test_match_key_ignores_case_and_punctuation():
    a, b, c = match_key(pd.Series(["Apex Media Kft.", "APEX MEDIA KFT", "  apex  media kft. "]))
    assert a == b == c


def test_sku_key_unifies_spellings():
    keys = sku_key(pd.Series(["PP-001", "pp-001 ", "PP001"]))
    assert keys.nunique() == 1


def test_country_aliases():
    out = map_with_aliases(pd.Series(["HU", "Magyarország", " hungary ", "Czech Republic", "Atlantis"]),
                           COUNTRY_ALIASES)
    assert list(out[:4]) == ["Hungary", "Hungary", "Hungary", "Czechia"]
    assert pd.isna(out[4])


def test_status_aliases():
    out = map_with_aliases(pd.Series(["DELIVERED", "Delivered ", "Canceled", "cancelled"]), STATUS_ALIASES)
    assert list(out) == ["Delivered", "Delivered", "Cancelled", "Cancelled"]


def test_fix_percentage_scale():
    fixed, mask = fix_percentage_scale(pd.Series([0.1, 10, 0.0, 12.5]))
    assert list(fixed) == [0.1, 0.1, 0.0, 0.125]
    assert list(mask) == [False, True, False, True]


def test_date_key_and_dimension():
    assert to_date_key(pd.Series([pd.Timestamp("2025-03-14")]))[0] == 20250314
    dim = build_date_dimension("2024-01-01", "2024-12-31")
    assert len(dim) == 366                      # leap year
    assert dim["date_key"].is_unique
    assert dim.loc[dim["date_key"] == 20240106, "is_weekend"].item()   # a Saturday
