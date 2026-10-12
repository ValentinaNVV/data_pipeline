import logging
import numpy as np
import pandas as pd
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
