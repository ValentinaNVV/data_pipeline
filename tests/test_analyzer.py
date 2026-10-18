# Тесты анализа: статистики, агрегация, декомпозиция, модель

import numpy as np
import pandas as pd
import pytest

from analyzer import (
    aggregate_monthly,
    basic_stats,
    decompose_series,
    train_and_evaluate,
)


def test_basic_stats():
    df = pd.DataFrame({"kwh": [1, 2, 2, 3, 10]})
    stats = basic_stats(df, "kwh")
    assert stats == {"mean": 3.6, "median": 2.0, "mode": 2.0, "std": 3.65}


def test_aggregate_monthly_sum_and_mean():
    df = pd.DataFrame(
        {
            "period": ["2023-01-05", "2023-01-20", "2023-02-10"],
            "kwh": [1.0, 2.0, 3.0],
        }
    )
    total = aggregate_monthly(df)
    average = aggregate_monthly(df, agg="mean")

    assert total.tolist() == [3.0, 3.0]
    assert average.tolist() == [1.5, 3.0]


def test_decompose_series_finds_january_peak():
    """Ряд с заранее известной сезонностью: пик в январе, лёгкий рост."""
    months = pd.date_range("2023-01-01", periods=36, freq="MS")
    values = [
        100 + 10 * np.cos(2 * np.pi * (m.month - 1) / 12) + 0.5 * i
        for i, m in enumerate(months)
    ]
    series = pd.Series(values, index=months)

    result = decompose_series(series)

    assert result.seasonal.idxmax().month == 1
    # Тренд не определён для первых и последних 6 месяцев
    assert result.trend.isna().sum() == 12


def test_train_and_evaluate_linear_data():
    """На точной линейной зависимости y = 2x + 1 линейная регрессия почти идеальна."""
    X = pd.DataFrame({"x": range(100)})
    y = 2 * X["x"] + 1

    results = train_and_evaluate(X, y)

    assert set(results) == {"LinearRegression", "RandomForest"}
    assert results["LinearRegression"]["R2"] == pytest.approx(1.0)
    assert results["LinearRegression"]["MAE"] == pytest.approx(0, abs=1e-6)
