import logging

import pandas as pd

# Журнал для этого модуля; __name__ подставит имя файла — "cleaner"
logger = logging.getLogger(__name__)

def remove_duplicates(df):
    """Удаляет полностью повторяющиеся строки из DataFrame.

    Аргументы:
        df (pd.DataFrame): Таблица с данными.

    Возвращает:
        pd.DataFrame: Новая таблица без дубликатов. Исходная не изменяется.
    """
    initial_count = len(df)
    df = df.drop_duplicates()
    removed_count = initial_count - len(df)
    if removed_count > 0:
        logger.info("Удалено дубликатов: %d", removed_count)
    else:
        logger.info("Дубликатов не найдено")
    return df

def convert_dates(df, column, date_format="%d.%m.%Y"):
    """Преобразует колонку с датами в формат datetime.

    Аргументы:
        df (pd.DataFrame): Таблица с данными.
        column (str): Название колонки с датами.
        date_format (str, optional): Формат даты. По умолчанию "%d.%m.%Y".

    Возвращает:
        pd.DataFrame: Новая таблица с преобразованной колонкой. Исходная не изменяется.
    """
    if column not in df.columns:
        logger.warning("Колонка '%s' не найдена в таблице", column)
        return df

    df = df.copy()
    df[column] = pd.to_datetime(df[column], format=date_format, errors='coerce')

    # Сколько значений не удалось превратить в дату
    failed = df[column].isna().sum()
    if failed > 0:
        logger.warning("Не удалось преобразовать в даты %d значений в колонке '%s'", failed, column)
    else:
        logger.info("Колонка '%s' успешно преобразована в формат datetime", column)
    return df

def fill_missing(df, column, strategy="median", group_by=None):
    """Обрабатывает пропущенные значения в указанной колонке.

    Аргументы:
        df (pd.DataFrame): Таблица с данными.
        column (str): Название колонки с пропусками.
        strategy (str, optional): Способ обработки:
            "mean" — заменить средним, "median" — заменить медианой,
            "drop" — удалить строки с пропусками. По умолчанию "median".
        group_by (str, optional): Колонка для группировки (например, customer_id).
            Если указана, среднее и медиана считаются внутри каждой группы.

    Возвращает:
        pd.DataFrame: Новая таблица без пропусков в колонке. Исходная не изменяется.

    Исключения:
        ValueError: Если указана неизвестная стратегия.
    """
    if strategy not in ("mean", "median", "drop"):
        raise ValueError(f"Неизвестная стратегия: '{strategy}'. Допустимо: mean, median, drop")

    df = df.copy()
    missing_count = df[column].isna().sum()

    if missing_count == 0:
        logger.info("Пропусков в колонке '%s' нет", column)
        return df

    # Удаление строк с пропусками
    if strategy == "drop":
        df = df.dropna(subset=[column])
        logger.info("Удалено строк с пропусками в '%s': %d", column, missing_count)
        return df

    # Замена средним или медианой
    if group_by:
        # Значение для заполнения своё у каждой группы, "растянуто" на все её строки
        fill_values = df.groupby(group_by)[column].transform(strategy)
    else:
        # Одно значение на всю колонку
        fill_values = df[column].agg(strategy)

    df[column] = df[column].fillna(fill_values)
    logger.info(
        "Заполнено пропусков в '%s': %d (стратегия: %s%s)",
        column, missing_count, strategy,
        f", по группам '{group_by}'" if group_by else "",
    )
    return df

if __name__ == "__main__":
    from loader import load_csv

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    df = load_csv("data/consumption.csv")
    df = remove_duplicates(df)
    df = convert_dates(df, "period")
    print(df.dtypes)

    filled = fill_missing(df, "kwh", strategy="median", group_by="customer_id")
    print("Пропусков после заполнения:", filled["kwh"].isna().sum())