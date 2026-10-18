import logging

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from statsmodels.tsa.seasonal import seasonal_decompose

from cleaner import (
    convert_dates,
    fill_by_billing_rules,
    remove_duplicates,
    replace_outliers,
)

# Журнал для этого модуля; __name__ подставит имя файла — "analyzer"
logger = logging.getLogger(__name__)


def basic_stats(df, column):
    """Вычисляет базовые статистики по указанной колонке DataFrame.

    Аргументы:
        df (pd.DataFrame): Таблица с данными.
        column (str): Название колонки для анализа.

    Возвращает:
        dict: Словарь с базовыми статистиками: mean, median, mode, std.
    """
    stats = {
        "mean": round(float(df[column].mean()), 2),
        "median": round(float(df[column].median()), 2),
        "mode": (
            round(float(df[column].mode().iloc[0]), 2)
            if not df[column].mode().empty
            else np.nan
        ),
        "std": round(float(df[column].std()), 2),
    }
    logger.info("Базовые статистики для '%s': %s", column, stats)
    return stats


def merge_customer_data(consumption, customers):
    """Объединяет таблицы потребления и абонентов по customer_id (LEFT JOIN).

    Аргументы:
        consumption (pd.DataFrame): Таблица с данными о потреблении.
        customers (pd.DataFrame): Справочник абонентов.

    Возвращает:
        pd.DataFrame: Таблица потребления с добавленными данными абонентов.
            Количество строк совпадает с исходной таблицей потребления,
            если в справочнике нет дублей customer_id.
    """
    merged = pd.merge(consumption, customers, on="customer_id", how="left")

    # Если строк стало больше — в справочнике повторяются customer_id
    if len(merged) > len(consumption):
        logger.warning(
            "После объединения строк стало больше: %d -> %d. "
            "Проверьте дубли customer_id в справочнике абонентов",
            len(consumption),
            len(merged),
        )
    else:
        logger.info("Таблицы объединены: %d строк, %d колонок", *merged.shape)
    return merged


def aggregate_monthly(df, column="kwh", date_column="period", agg="sum"):
    """Агрегирует значения колонки по месяцам и возвращает временной ряд.

    Аргументы:
        df (pd.DataFrame): Таблица с данными.
        column (str): Колонка для агрегации. По умолчанию "kwh".
        date_column (str): Колонка с датами. По умолчанию "period".
        agg (str): Метод агрегации: "sum", "mean", "median" и т.д. По умолчанию "sum".

    Возвращает:
        pd.Series: Временной ряд — агрегированное значение за каждый месяц,
            индекс — первое число месяца (datetime).
    """
    df = df.copy()
    df[date_column] = pd.to_datetime(df[date_column], errors="coerce")

    # Приводим каждую дату к её месяцу и агрегируем внутри месяца
    month = df[date_column].dt.to_period("M")
    series = df.groupby(month)[column].agg(agg)

    # Индекс из "периодов" переводим в обычные даты (первое число месяца)
    series.index = series.index.to_timestamp()
    series.index.name = "month"

    logger.info(
        "Данные агрегированы по месяцам (%s): %d месяцев (%s — %s)",
        agg,
        len(series),
        series.index.min().strftime("%m.%Y"),
        series.index.max().strftime("%m.%Y"),
    )
    return series


# Названия месяцев для понятного лога: MONTHS[1] -> "январь"
MONTHS = [
    "",
    "январь",
    "февраль",
    "март",
    "апрель",
    "май",
    "июнь",
    "июль",
    "август",
    "сентябрь",
    "октябрь",
    "ноябрь",
    "декабрь",
]


def decompose_series(series, period=12):
    """Раскладывает временной ряд на тренд, сезонность и остаток.

    Используется аддитивная модель: значение = тренд + сезон + остаток.
    Тренд считается скользящим средним, поэтому для первых и последних
    period/2 точек он не определён (NaN).

    Аргументы:
        series (pd.Series): Временной ряд с индексом типа datetime.
        period (int): Длина сезонного цикла. По умолчанию 12 (месяцев).

    Возвращает:
        DecomposeResult: Объект с атрибутами trend, seasonal и resid (pd.Series).
    """
    result = seasonal_decompose(series, model="additive", period=period)

    # Рост по тренду: от первого до последнего известного значения, в %
    trend = result.trend.dropna()
    growth = (trend.iloc[-1] / trend.iloc[0] - 1) * 100

    # Размах сезона и месяцы пика и спада
    seasonal = result.seasonal
    amplitude = seasonal.max() - seasonal.min()
    peak_month = MONTHS[seasonal.idxmax().month]
    low_month = MONTHS[seasonal.idxmin().month]

    logger.info(
        "Рост по тренду: %.1f%%; размах сезона: %.0f; пик: %s; спад: %s",
        growth,
        amplitude,
        peak_month,
        low_month,
    )
    return result


def detect_anomalies(result, threshold=3):
    """Ищет аномальные месяцы по остатку временного ряда (метод Z-score).

    Аномалией считается месяц, где остаток отклоняется от среднего остатка
    больше чем на threshold стандартных отклонений.

    Аргументы:
        result (DecomposeResult): Результат decompose_series.
        threshold (float): Порог в стандартных отклонениях. По умолчанию 3.

    Возвращает:
        pd.Series: Остатки аномальных месяцев (индекс — дата).
            Пустой ряд, если аномалий нет.
    """
    # У первых и последних period/2 месяцев остатка нет — убираем пустые
    resid = result.resid.dropna()
    mean = resid.mean()
    std = resid.std()

    # |остаток - среднее| > threshold * std  — то же самое, что |Z| > threshold
    anomalies = resid[(resid - mean).abs() > threshold * std]

    if anomalies.empty:
        logger.info("Аномальных месяцев не найдено (порог %.1f)", threshold)
    else:
        logger.warning(
            "Найдено аномальных месяцев: %d — %s",
            len(anomalies),
            [d.strftime("%m.%Y") for d in anomalies.index],
        )
    return anomalies


def build_features(consumption, customers, monthly_temp):
    """Собирает таблицу признаков для модели прогноза расхода.

    Признаки: тип абонента, тариф, район (One-Hot), номер месяца,
    средняя температура месяца, расход того же месяца прошлого года.
    Строки без расхода прошлого года (первый год данных) отбрасываются.

    Аргументы:
        consumption (pd.DataFrame): Очищенная таблица потребления
            (customer_id, period в формате datetime, kwh).
        customers (pd.DataFrame): Справочник абонентов, уже закодированный
            (encode_label для tariff и customer_type, encode_onehot для district).
        monthly_temp (pd.Series): Средняя температура по месяцам (индекс — дата).

    Возвращает:
        tuple: (X, y), где X (pd.DataFrame) — признаки, y (pd.Series) — расход kwh.
    """
    df = merge_customer_data(consumption, customers)
    df = df.sort_values(["customer_id", "period"])

    # Номер месяца: 1 — январь, ..., 12 — декабрь
    df["month"] = df["period"].dt.month

    # Температура: каждой дате ставим в соответствие среднюю температуру её месяца
    df["temperature"] = df["period"].map(monthly_temp)

    # Расход того же месяца прошлого года (сдвиг на 12 месяцев внутри абонента)
    df["kwh_last_year"] = df.groupby("customer_id")["kwh"].shift(12)
    df = df.dropna(subset=["kwh_last_year", "temperature"])

    # Убираем то, что не является признаком: номера и даты модели не нужны
    X = df.drop(columns=["kwh", "customer_id", "account_number", "period"])
    y = df["kwh"]

    logger.info("Таблица признаков: %d строк, признаки: %s", len(X), list(X.columns))
    return X, y


def train_and_evaluate(X, y, test_size=0.2, random_state=42):
    """Обучает модели регрессии и оценивает их качество на отложенной выборке.

    Сравниваются линейная регрессия и случайный лес.

    Аргументы:
        X (pd.DataFrame): Признаки.
        y (pd.Series): Целевая переменная (расход kwh).
        test_size (float): Доля данных для проверки. По умолчанию 0.2 (20%).
        random_state (int): Зерно случайности для воспроизводимости. По умолчанию 42.

    Возвращает:
        dict: {название_модели: {"model": обученная модель,
            "MAE": ..., "RMSE": ..., "R2": ...}}.
    """
    # Делим данные: 80% на обучение ("учебник"), 20% на проверку ("экзамен")
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=random_state
    )

    models = {
        "LinearRegression": LinearRegression(),
        "RandomForest": RandomForestRegressor(
            n_estimators=100, random_state=random_state
        ),
    }

    results = {}
    for name, model in models.items():
        model.fit(X_train, y_train)  # обучение на примерах с ответами
        y_pred = model.predict(X_test)  # прогноз на новых примерах

        metrics = {
            "MAE": round(float(mean_absolute_error(y_test, y_pred)), 2),
            "RMSE": round(float(np.sqrt(mean_squared_error(y_test, y_pred))), 2),
            "R2": round(float(r2_score(y_test, y_pred)), 4),
        }
        results[name] = {"model": model, **metrics}
        logger.info("Модель %s: %s", name, metrics)

    return results


if __name__ == "__main__":
    from loader import load_csv, load_excel

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Загружаем данные для анализа
    df = load_csv("data/consumption.csv")

    # Применяем очистку данных
    df = remove_duplicates(df)
    df = convert_dates(df, "period")
    df = replace_outliers(df, "kwh", group_by="customer_id")
    df = fill_by_billing_rules(df)

    # Вычисляем базовые статистики по колонке "kwh"
    stats = basic_stats(df, "kwh")
    print("Базовые статистики по колонке 'kwh':", stats)

    customers = load_excel("data/customers.xlsx")
    merged = merge_customer_data(df, customers)

    for ctype in ["физлицо", "юрлицо"]:
        subset = merged[merged["customer_type"] == ctype]
        print(ctype, basic_stats(subset, "kwh"))

    # Агрегируем данные по месяцам
    monthly = aggregate_monthly(df)
    print(monthly.head(12))

    # Разлагаем временной ряд
    decomposition = decompose_series(monthly)
    print(decomposition.seasonal.head(12))

    # 1. На очищенных данных
    detect_anomalies(decomposition)

    # 2. На «сырых» данных — без очистки, только даты переведены
    raw = load_csv("data/consumption.csv")
    raw = convert_dates(raw, "period")
    raw_monthly = aggregate_monthly(raw)
    raw_decomposition = decompose_series(raw_monthly)
    detect_anomalies(raw_decomposition)

    from loader import load_api

    weather = load_api(
        "https://archive-api.open-meteo.com/v1/archive",
        params={
            "latitude": 55.75,
            "longitude": 37.62,
            "start_date": "2023-01-01",
            "end_date": "2025-12-31",
            "daily": "temperature_2m_mean",
            "timezone": "Europe/Moscow",
        },
        data_key="daily",
    )
    monthly_temp = aggregate_monthly(
        weather, column="temperature_2m_mean", date_column="time", agg="mean"
    )
    print(monthly_temp.head(12))

    from cleaner import encode_label, encode_onehot

    customers_enc = load_excel("data/customers.xlsx")
    customers_enc = encode_label(customers_enc, ["tariff", "customer_type"])
    customers_enc = encode_onehot(customers_enc, ["district"])

    X, y = build_features(df, customers_enc, monthly_temp)
    results = train_and_evaluate(X, y)
