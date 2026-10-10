import pandas as pd
from pathlib import Path
from db import get_engine

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

