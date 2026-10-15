# Загрузка данных из разных источников: CSV, Excel, PostgreSQL, внешний API

import logging
from pathlib import Path

import pandas as pd
import requests

from db import get_engine

# Журнал для этого модуля; __name__ подставит имя файла — "loader"
logger = logging.getLogger(__name__)


#функция для загрузки данных из CSV-файла
def load_csv(path):
    """Загружает данные из CSV-файла.

    Аргументы:
        path (str | Path): Путь к CSV-файлу.

    Возвращает:
        pd.DataFrame: Загруженная таблица.

    Исключения:
        FileNotFoundError: Если файл не найден.
    """
    if not Path(path).exists():
        logger.error("Файл не найден: %s", path)
        raise FileNotFoundError(f"Файл {path} не найден.")
    df = pd.read_csv(path)
    logger.info("Загружен CSV %s: %d строк, %d колонок", path, *df.shape)
    return df

# функция для загрузки данных из Excel-файла
def load_excel(path):
    """Загружает данные из Excel-файла (первый лист).

    Аргументы:
        path (str | Path): Путь к файлу .xlsx.

    Возвращает:
        pd.DataFrame: Загруженная таблица.

    Исключения:
        FileNotFoundError: Если файл не найден.
    """
    if not Path(path).exists():
        logger.error("Файл не найден: %s", path)
        raise FileNotFoundError(f"Файл {path} не найден.")
    df = pd.read_excel(path)
    logger.info("Загружен Excel %s: %d строк, %d колонок", path, *df.shape)
    return df

# функция для загрузки данных из PostgreSQL
def load_sql(query):
    """Выполняет SQL-запрос к PostgreSQL и возвращает результат.

    Параметры подключения берутся из .env (см. db.get_engine).

    Аргументы:
        query (str): Текст SQL-запроса (поддерживаются JOIN, агрегаты и т.д.).

    Возвращает:
        pd.DataFrame: Результат запроса.
    """
    engine = get_engine()
    with engine.connect() as connection:
        result = pd.read_sql(query, connection)
    logger.info("SQL-запрос выполнен: %d строк, %d колонок", *result.shape)
    return result

# функция для загрузки данных из REST API
def load_api(url, params=None, data_key=None):
    """Загружает данные из REST API и возвращает их в виде DataFrame.

    Аргументы:
        url (str): Адрес API.
        params (dict, optional): Параметры запроса. По умолчанию None.
        data_key (str, optional): Ключ в JSON-ответе, где лежат данные.
            Если None, используется весь ответ. По умолчанию None.

    Возвращает:
        pd.DataFrame: Таблица с данными из API.

    Исключения:
        requests.HTTPError: Если сервер вернул ошибку.
        KeyError: Если в ответе нет ключа data_key.
    """
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()  # ошибка, если сервер ответил неудачей (4xx, 5xx)
    data = response.json()

    if data_key:
        if data_key not in data:
            logger.error("В ответе API нет ключа '%s'", data_key)
            raise KeyError(f"В ответе API нет ключа '{data_key}'")
        data = data[data_key]

    df = pd.DataFrame(data)
    logger.info("Загружены данные из API %s: %d строк", url, len(df))
    return df

if __name__ == "__main__":
    # тестируем загрузку из файлов
    csv_path = Path("data/consumption.csv")
    excel_path = Path("data/customers.xlsx")

    consumption_df = load_csv(csv_path)
    customers_df = load_excel(excel_path)

    print("\nРазмер:", consumption_df.shape)
    print("Первые 5 строк таблицы потребления:")
    print(consumption_df.head())
    print("\nРазмер:", customers_df.shape)
    print("Первые 5 строк таблицы абонентов:")
    print(customers_df.head())

    # тестируем загрузку из PostgreSQL: запрос с JOIN и агрегатами
    # Тройные кавычки """ позволяют записать строку в несколько строк
    query = """
        SELECT c.district,
               c.customer_type,
               COUNT(DISTINCT c.customer_id) AS customers_count,
               ROUND(SUM(k.kwh)::numeric, 1) AS total_kwh
        FROM consumption k
        JOIN customers c ON c.customer_id = k.customer_id
        GROUP BY c.district, c.customer_type
        ORDER BY total_kwh DESC
    """
    sql_df = load_sql(query)
    print("\nПотребление по районам и типам абонентов:")
    print(sql_df)

    weather_df = load_api(
        "https://archive-api.open-meteo.com/v1/archive",
        params={
            "latitude": 55.75,      # координаты города (здесь Москва, можно свои)
            "longitude": 37.62,
            "start_date": "2023-01-01",
            "end_date": "2025-12-31",
            "daily": "temperature_2m_mean",
            "timezone": "Europe/Moscow",
        },
        data_key="daily",
    )
    print("\nРазмер:", weather_df.shape)
    print(weather_df.head())

