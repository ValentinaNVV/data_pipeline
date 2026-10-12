import logging
import numpy as np
import pandas as pd
from cleaner import (
       convert_dates,
       fill_by_billing_rules,
       remove_duplicates,
       replace_outliers,
   )
from statsmodels.tsa.seasonal import seasonal_decompose

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
        "mode": round(float(df[column].mode().iloc[0]), 2) if not df[column].mode().empty else np.nan,
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
            len(consumption), len(merged),
        )
    else:
        logger.info("Таблицы объединены: %d строк, %d колонок", *merged.shape)
    return merged

def aggregate_monthly(df, column="kwh", date_column="period"):
    """Суммирует значения колонки по месяцам и возвращает временной ряд.

    Аргументы:
        df (pd.DataFrame): Таблица с данными.
        column (str): Колонка для суммирования. По умолчанию "kwh".
        date_column (str): Колонка с датами. По умолчанию "period".

    Возвращает:
        pd.Series: Временной ряд — сумма значений за каждый месяц,
            индекс — первое число месяца (datetime).
    """
    df = df.copy()
    df[date_column] = pd.to_datetime(df[date_column], errors="coerce")

    # Приводим каждую дату к её месяцу и суммируем внутри месяца
    month = df[date_column].dt.to_period("M")
    series = df.groupby(month)[column].sum()

    # Индекс из "периодов" переводим в обычные даты (первое число месяца)
    series.index = series.index.to_timestamp()
    series.index.name = "month"

    logger.info(
        "Данные агрегированы по месяцам: %d месяцев (%s — %s)",
        len(series),
        series.index.min().strftime("%m.%Y"),
        series.index.max().strftime("%m.%Y"),
    )
    return series

# Названия месяцев для понятного лога: MONTHS[1] -> "январь"
MONTHS = [
    "", "январь", "февраль", "март", "апрель", "май", "июнь",
    "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь",
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
        growth, amplitude, peak_month, low_month,
    )
    return result

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