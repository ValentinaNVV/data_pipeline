import logging

import numpy as np
import pandas as pd

from validator import detect_outliers_iqr

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
    df[column] = pd.to_datetime(df[column], format=date_format, errors="coerce")

    # Сколько значений не удалось превратить в дату
    failed = df[column].isna().sum()
    if failed > 0:
        logger.warning(
            "Не удалось преобразовать в даты %d значений в колонке '%s'", failed, column
        )
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
        raise ValueError(
            f"Неизвестная стратегия: '{strategy}'. Допустимо: mean, median, drop"
        )

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
        column,
        missing_count,
        strategy,
        f", по группам '{group_by}'" if group_by else "",
    )
    return df


def replace_outliers(df, column, group_by=None):
    """Заменяет выбросы (найденные методом IQR) на пропуски.

    Аномальное значение считается недостоверным потреблением: оно удаляется
    и далее обрабатывается как пропуск по правилам расчёта.

    Аргументы:
        df (pd.DataFrame): Таблица с данными.
        column (str): Колонка, в которой ищем выбросы.
        group_by (str, optional): Колонка для группировки (например, customer_id).

    Возвращает:
        pd.DataFrame: Новая таблица, где выбросы заменены на NaN.
    """
    df = df.copy()
    mask = detect_outliers_iqr(df, column, group_by=group_by)
    df.loc[mask, column] = np.nan
    logger.info("Выбросы в '%s' заменены на пропуски: %d", column, mask.sum())
    return df


def fill_by_billing_rules(
    df, column="kwh", group_by="customer_id", date_column="period"
):
    """Заполняет пропуски по правилам расчёта при отсутствии показаний.

    Порядок:
        1. Расход того же месяца прошлого года.
        2. Если его нет — расход ближайшего предыдущего месяца.
        3. Если и его нет (начало периода) — ближайшего следующего месяца.

    Важно: данные должны быть помесячными, без пропущенных месяцев
    у каждого абонента (сдвиг на 12 строк = сдвиг на 12 месяцев).

    Аргументы:
        df (pd.DataFrame): Таблица с данными.
        column (str): Колонка с расходом. По умолчанию "kwh".
        group_by (str): Колонка с абонентом. По умолчанию "customer_id".
        date_column (str): Колонка с расчётным периодом (тип datetime). По умолчанию "period".

    Возвращает:
        pd.DataFrame: Новая таблица без пропусков в колонке, отсортированная
            по абоненту и периоду.
    """
    # Сортируем по абоненту и месяцу, чтобы сдвиги шли в правильном порядке
    df = df.sort_values([group_by, date_column]).copy()

    missing_before = df[column].isna().sum()
    if missing_before == 0:
        logger.info("Пропусков в '%s' нет", column)
        return df

    # Шаг 1: тот же месяц прошлого года (сдвиг на 12 строк внутри абонента)
    year_ago = df.groupby(group_by)[column].shift(12)
    df[column] = df[column].fillna(year_ago)
    missing_after_step1 = df[column].isna().sum()

    # Шаги 2 и 3: ближайший предыдущий месяц, затем ближайший следующий
    df[column] = df.groupby(group_by)[column].ffill()
    df[column] = df.groupby(group_by)[column].bfill()

    logger.info(
        "Заполнено пропусков в '%s': %d (по прошлому году: %d, по ближайшему месяцу: %d)",
        column,
        missing_before,
        missing_before - missing_after_step1,
        missing_after_step1,
    )
    return df


def encode_label(df, columns):
    """Преобразует категориальные колонки в числовые с помощью Label Encoding.

    Аргументы:
        df (pd.DataFrame): Таблица с данными.
        columns (list of str): Список колонок для кодирования.

    Возвращает:
        pd.DataFrame: Новая таблица с закодированными колонками.
    """
    df = df.copy()
    for col in columns:
        if col not in df.columns:
            logger.warning("Колонка '%s' не найдена в таблице", col)
            continue
        categories = df[col].astype("category")
        # Расшифровка до замены: {0: 'физлицо', 1: 'юрлицо'}
        mapping = dict(enumerate(categories.cat.categories))
        df[col] = categories.cat.codes
        logger.info("Колонка '%s' закодирована: %s", col, mapping)
    return df


def encode_onehot(df, columns):
    """Преобразует категориальные колонки в бинарные с помощью One-Hot Encoding.

    Аргументы:
        df (pd.DataFrame): Таблица с данными.
        columns (list of str): Список колонок для кодирования.

    Возвращает:
        pd.DataFrame: Новая таблица с бинарными колонками.
    """
    df = df.copy()
    for col in columns:
        if col not in df.columns:
            logger.warning("Колонка '%s' не найдена в таблице", col)
            continue
        dummies = pd.get_dummies(df[col], prefix=col, dtype=int)
        df = pd.concat([df, dummies], axis=1)
        df = df.drop(columns=[col])
        logger.info("Колонка '%s' преобразована в: %s", col, list(dummies.columns))
    return df


def scale_features(df, columns, method="standard"):
    """Масштабирует числовые колонки.

    Аргументы:
        df (pd.DataFrame): Таблица с данными.
        columns (list of str): Список колонок для масштабирования.
        method (str): Метод масштабирования ("standard", "minmax").

    Исключения:
        ValueError: Если указан неизвестный метод.

    Возвращает:
        pd.DataFrame: Новая таблица с масштабированными колонками.
    """
    if method not in ("standard", "minmax"):
        raise ValueError(
            f"Неизвестный метод масштабирования: '{method}'. Допустимо: standard, minmax"
        )
    df = df.copy()
    for col in columns:
        if col not in df.columns:
            logger.warning("Колонка '%s' не найдена в таблице", col)
            continue
        if method == "standard":
            df[col] = (df[col] - df[col].mean()) / df[col].std()
        elif method == "minmax":
            df[col] = (df[col] - df[col].min()) / (df[col].max() - df[col].min())
        logger.info("Колонка '%s' масштабирована методом '%s'", col, method)
    return df


if __name__ == "__main__":
    from loader import load_csv, load_excel

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Очистка таблицы потребления
    df = load_csv("data/consumption.csv")
    df = remove_duplicates(df)
    df = convert_dates(df, "period")
    df = replace_outliers(df, "kwh", group_by="customer_id")
    df = fill_by_billing_rules(df)
    print("Пропусков после очистки:", df["kwh"].isna().sum())

    # Кодирование категорий в таблице абонентов
    customers = load_excel("data/customers.xlsx")
    customers = encode_label(customers, ["tariff", "customer_type"])
    customers = encode_onehot(customers, ["district"])
    print(customers.head())

    # Масштабирование
    scaled = scale_features(df, ["kwh"], method="standard")
    print(scaled["kwh"].describe())
