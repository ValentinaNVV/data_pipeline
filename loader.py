import pandas as pd
from pathlib import Path

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

if __name__ == "__main__":
    #тестируем функции загрузки
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