import pandas as pd
from pathlib import Path
from db import get_engine
import requests


#функция для загрузки CSV-файла в DataFrame
def load_csv(path):    
    if not Path(path).exists():
        raise FileNotFoundError(f"Файл {path} не найден.")
    return pd.read_csv(path)

#функция для загрузки Excel-файла в DataFrame
def load_excel(path):
    if not Path(path).exists():
        raise FileNotFoundError(f"Файл {path} не найден.")
    return pd.read_excel(path)

def load_sql(query):
    """Выполняет SQL-запрос и возвращает результат в виде DataFrame."""
    engine = get_engine()
    with engine.connect() as connection:
        result = pd.read_sql(query, connection)
    return result

def load_api(url, params=None, data_key=None):
    """Загружает данные из API и возвращает их в виде DataFrame.
    
    Аргументы:
        url (str): URL-адрес API.
        params (dict, optional): Параметры запроса. По умолчанию None.
        data_key (str, optional): Ключ в JSON-ответе, содержащий данные. 
                                  Если None, используется весь ответ. 
                                  По умолчанию None.
    
    Возвращает:
        pd.DataFrame: DataFrame с данными из API.
    """
    
    response = requests.get(url, params=params, timeout=30)  # Устанавливаем таймаут в 30 секунд
    response.raise_for_status()  # Проверяем успешность запроса
    data = response.json()

    if data_key:
        if data_key not in data:
            raise KeyError(f"В ответе API нет ключа '{data_key}'")
        data = data[data_key]
    
    return pd.DataFrame(data)

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

