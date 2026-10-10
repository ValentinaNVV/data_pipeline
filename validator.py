import logging
import pandas as pd

# Журнал для этого модуля; __name__ подставит имя файла — "validator"
logger = logging.getLogger(__name__)

# Ящик с инструментами для проверки типов: название ожидаемого типа -> функция-проверка
TYPE_CHECKS = {
    "numeric": pd.api.types.is_numeric_dtype,
    "datetime": pd.api.types.is_datetime64_any_dtype,
    "string": pd.api.types.is_string_dtype,
}

def check_types(df, expected):
    """Проверяет, что типы колонок в DataFrame соответствуют ожидаемым.

    Аргументы:
        df (pd.DataFrame): Таблица с данными.
        expected (dict): Словарь вида {название_колонки: ожидаемый_тип}.
            Допустимые типы: "numeric", "datetime", "string".

    Возвращает:
        list: Список колонок с проблемами. Пустой список — всё в порядке.
    """
    problems = []  # сюда собираем все проблемные колонки — полный "акт"

    for col, expected_type in expected.items():
        # 1. Колонки нет в таблице — записываем и идём к следующей
        if col not in df.columns:
            logger.warning("Колонка '%s' не найдена в таблице", col)
            problems.append(col)
            continue

        # 2. Достаём из "ящика" нужную проверку и применяем к колонке
        checker = TYPE_CHECKS[expected_type]
        if not checker(df[col]):
            logger.warning(
                "Колонка '%s' имеет тип %s, ожидается %s",
                col, df[col].dtype, expected_type,
            )
            problems.append(col)

    # 3. Итог проверки
    if not problems:
        logger.info("Все типы колонок соответствуют ожидаемым")
    return problems

def check_duplicates(df):
    """Проверяет наличие полностью повторяющихся строк в DataFrame.

    Аргументы:
        df (pd.DataFrame): Таблица с данными.

    Возвращает:
        int: Количество найденных дубликатов.
    """    
    duplicates = df.duplicated()
    count = duplicates.sum()
    if count > 0:
        logger.warning("Найдено дубликатов: %d", count)
    else:
        logger.info("Дубликатов не найдено")
    return count

def check_missing(df):
    """Проверяет наличие пропущенных значений в каждой колонке DataFrame.

    Аргументы:
        df (pd.DataFrame): Таблица с данными.

    Возвращает:
        pd.Series: Количество пропусков по каждой колонке.
    """
    missing = df.isnull().sum()
    total_missing = missing.sum()
    if total_missing > 0:
        logger.warning("Найдено пропущенных значений: %d", total_missing)
        for col, count in missing.items():
            if count > 0:
                logger.warning("Колонка '%s': %d", col, count)
    else:
        logger.info("Пропущенных значений не найдено")

    
    return missing

def detect_outliers_iqr(df, column, group_by=None, k=1.5):
    """Находит выбросы методом межквартильного размаха (IQR).

    Аргументы:
        df (pd.DataFrame): Таблица с данными.
        column (str): Колонка, в которой ищем выбросы.
        group_by (str, optional): Колонка для группировки (например, customer_id).
            Если указана, коридор нормы считается внутри каждой группы.
        k (float): Множитель IQR. По умолчанию 1.5.

    Возвращает:
        pd.Series: True для строк-выбросов, False для остальных.
    """
    if group_by:
        # Q1 и Q3 считаются по каждому абоненту и "растягиваются" на все его строки
        grouped = df.groupby(group_by)[column]
        q1 = grouped.transform(lambda s: s.quantile(0.25))
        q3 = grouped.transform(lambda s: s.quantile(0.75))
    else:
        # Q1 и Q3 по всей колонке сразу
        q1 = df[column].quantile(0.25)
        q3 = df[column].quantile(0.75)

    iqr = q3 - q1
    lower = q1 - k * iqr  # нижняя граница коридора
    upper = q3 + k * iqr  # верхняя граница коридора

    # Выброс — всё, что за пределами коридора.
    # Пропуски (NaN) при сравнении дают False, поэтому выбросами не считаются
    mask = (df[column] < lower) | (df[column] > upper)

    count = mask.sum()
    if count > 0:
        logger.warning("IQR: найдено выбросов в '%s': %d", column, count)
    else:
        logger.info("IQR: выбросов в '%s' не найдено", column)
    return mask

def detect_outliers_zscore(df, column, group_by=None, threshold=3):
    """Находит выбросы методом Z-оценки.

    Аргументы:
        df (pd.DataFrame): Таблица с данными.
        column (str): Колонка, в которой ищем выбросы.
        group_by (str, optional): Колонка для группировки (например, customer_id).
            Если указана, Z-оценка считается внутри каждой группы.
        threshold (float): Порог Z-оценки. По умолчанию 3.

    Возвращает:
        pd.Series: True для строк-выбросов, False для остальных.
    """
    if group_by:
        grouped = df.groupby(group_by)[column]
        mean = grouped.transform('mean')
        std = grouped.transform('std')
    else:
        mean = df[column].mean()
        std = df[column].std()

    z_scores = (df[column] - mean) / std
    mask = z_scores.abs() > threshold

    count = mask.sum()
    if count > 0:
        logger.warning("Z-score: найдено выбросов в '%s': %d", column, count)
    else:
        logger.info("Z-score: выбросов в '%s' не найдено", column)
    return mask

if __name__ == "__main__":
    from loader import load_csv

    # Настройка журнала: формат строки — время, уровень, модуль, сообщение
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    df = load_csv("data/consumption.csv")
    check_duplicates(df)
    check_missing(df)

    detect_outliers_iqr(df, "kwh")
    detect_outliers_iqr(df, "kwh", group_by="customer_id")
    detect_outliers_zscore(df, "kwh")
    detect_outliers_zscore(df, "kwh", group_by="customer_id")

    expected = {
        "customer_id": "numeric",
        "period": "datetime",
        "kwh": "numeric",
    }
    check_types(df, expected)