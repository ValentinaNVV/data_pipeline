# Тесты очистки: дубликаты, даты, пропуски, правило расчёта, кодирование, масштабирование

import numpy as np
import pandas as pd
import pytest

from cleaner import (
    convert_dates,
    encode_label,
    encode_onehot,
    fill_by_billing_rules,
    fill_missing,
    remove_duplicates,
    scale_features,
)


def test_remove_duplicates():
    df = pd.DataFrame({"a": [1, 1, 2]})
    assert len(remove_duplicates(df)) == 2


def test_remove_duplicates_does_not_change_original():
    """Исходная таблица не меняется — работаем с копией."""
    df = pd.DataFrame({"a": [1, 1, 2]})
    remove_duplicates(df)
    assert len(df) == 3


def test_convert_dates_day_first():
    """01.02.2023 — это 1 февраля, а не 2 января."""
    df = pd.DataFrame({"period": ["01.02.2023"]})
    result = convert_dates(df, "period")
    assert result["period"].iloc[0] == pd.Timestamp("2023-02-01")


def test_fill_missing_median_by_group():
    df = pd.DataFrame({
        "customer_id": [1, 1, 1, 2, 2, 2],
        "kwh": [10.0, np.nan, 30.0, 1000.0, np.nan, 3000.0],
    })
    result = fill_missing(df, "kwh", strategy="median", group_by="customer_id")
    # Медиана своего абонента: 20 для первого, 2000 для второго
    assert result["kwh"].tolist() == [10.0, 20.0, 30.0, 1000.0, 2000.0, 3000.0]


def test_fill_missing_drop():
    df = pd.DataFrame({"kwh": [1.0, np.nan, 3.0]})
    assert len(fill_missing(df, "kwh", strategy="drop")) == 2


def test_fill_missing_unknown_strategy_raises():
    df = pd.DataFrame({"kwh": [1.0, np.nan]})
    with pytest.raises(ValueError):
        fill_missing(df, "kwh", strategy="meen")


def test_fill_by_billing_rules():
    """Пропуск — тот же месяц прошлого года; если его нет — предыдущий месяц."""
    df = pd.DataFrame({
        "customer_id": [1] * 24,
        "period": pd.date_range("2023-01-01", periods=24, freq="MS"),
        "kwh": [100.0 + i for i in range(24)],   # 100, 101, ..., 123
    })
    df.loc[1, "kwh"] = np.nan    # февраль 2023: прошлого года нет
    df.loc[12, "kwh"] = np.nan   # январь 2024: есть январь 2023 = 100

    result = fill_by_billing_rules(df)

    assert result.loc[12, "kwh"] == 100.0   # по прошлому году (а не 111 из декабря)
    assert result.loc[1, "kwh"] == 100.0    # по ближайшему предыдущему месяцу
    assert result["kwh"].isna().sum() == 0


def test_encode_label():
    df = pd.DataFrame({"tariff": ["одноставочный", "двухзонный"]})
    result = encode_label(df, ["tariff"])
    # Коды по алфавиту: двухзонный = 0, одноставочный = 1
    assert result["tariff"].tolist() == [1, 0]


def test_encode_onehot():
    df = pd.DataFrame({"district": ["Северный", "Южный"]})
    result = encode_onehot(df, ["district"])
    assert "district" not in result.columns
    assert result["district_Северный"].tolist() == [1, 0]
    assert result["district_Южный"].tolist() == [0, 1]


def test_scale_features_standard():
    df = pd.DataFrame({"kwh": [1.0, 2.0, 3.0, 4.0, 5.0]})
    result = scale_features(df, ["kwh"], method="standard")
    assert result["kwh"].mean() == pytest.approx(0)
    assert result["kwh"].std() == pytest.approx(1)


def test_scale_features_minmax():
    df = pd.DataFrame({"kwh": [10.0, 20.0, 30.0]})
    result = scale_features(df, ["kwh"], method="minmax")
    assert result["kwh"].tolist() == [0.0, 0.5, 1.0]


def test_scale_features_unknown_method_raises():
    df = pd.DataFrame({"kwh": [1.0, 2.0]})
    with pytest.raises(ValueError):
        scale_features(df, ["kwh"], method="standart")