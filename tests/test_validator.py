# Тесты валидации: дубликаты, пропуски, типы, выбросы

import numpy as np
import pandas as pd

from validator import check_duplicates, check_missing, check_types, detect_outliers_iqr


def test_check_duplicates_counts_full_duplicates():
    df = pd.DataFrame({"a": [1, 1, 2], "b": ["x", "x", "y"]})
    assert check_duplicates(df) == 1


def test_check_missing_counts_by_column():
    df = pd.DataFrame({"a": [1, np.nan, 3], "b": [np.nan, np.nan, "y"]})
    missing = check_missing(df)
    assert missing["a"] == 1
    assert missing["b"] == 2


def test_check_types_finds_wrong_type():
    """Дата, записанная строкой, — проблема; числа — в порядке."""
    df = pd.DataFrame({"period": ["01.01.2023"], "kwh": [100.0]})
    problems = check_types(df, {"period": "datetime", "kwh": "numeric"})
    assert problems == ["period"]


def test_detect_outliers_iqr_by_group():
    """С группировкой по абоненту выброс находится, а большой, но обычный расход — нет."""
    df = pd.DataFrame({
        "customer_id": ["A"] * 7 + ["B"] * 7,
        # A — квартира с одним испорченным показанием 1000; B — завод с нормальным расходом
        "kwh": [100, 102, 98, 101, 99, 100, 1000,
                10000, 10200, 9800, 10100, 9900, 10000, 10050],
    })

    mask = detect_outliers_iqr(df, "kwh", group_by="customer_id")

    assert mask.sum() == 1
    assert df.loc[mask, "kwh"].tolist() == [1000]