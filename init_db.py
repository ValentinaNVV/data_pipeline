# Однократное наполнение базы: переносим данные из CSV и Excel в PostgreSQL

from db import get_engine
from loader import load_csv, load_excel

engine = get_engine()

customers = load_excel("data/customers.xlsx")
consumption = load_csv("data/consumption.csv")

# to_sql создаёт таблицу и записывает в неё DataFrame.
# if_exists="replace" — если таблица уже есть, пересоздать (при перезапуске)
customers.to_sql("customers", engine, if_exists="replace", index=False)
consumption.to_sql("consumption", engine, if_exists="replace", index=False)

print(f"Загружено абонентов: {len(customers)}")
print(f"Загружено записей потребления: {len(consumption)}")
