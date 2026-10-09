# generate_data.py
# Генерирует учебные данные: абоненты (Excel) и их месячное потребление (CSV).
# В потреблении специально добавляются "грязные" записи:
# пропуски, дубликаты и выбросы — чтобы было что проверять и чистить.

import os

import numpy as np
import pandas as pd

np.random.seed(42)  # фиксируем случайность: при каждом запуске данные одинаковые

N_CUSTOMERS = 50

# ---------- Таблица абонентов ----------
customers = pd.DataFrame({
    "customer_id": range(1, N_CUSTOMERS + 1),
    "account_number": [f"ЛС-{100000 + i}" for i in range(1, N_CUSTOMERS + 1)],
    "district": np.random.choice(["Северный", "Южный", "Восточный", "Западный"], N_CUSTOMERS),
    "tariff": np.random.choice(["одноставочный", "двухзонный"], N_CUSTOMERS),
    # 80% физлиц, 20% юрлиц
    "customer_type": np.random.choice(["физлицо", "юрлицо"], N_CUSTOMERS, p=[0.8, 0.2]),
})

# ---------- Таблица потребления ----------
# Первое число каждого месяца с января 2023 по декабрь 2025 — 36 месяцев
months = pd.date_range("2023-01-01", "2025-12-01", freq="MS")

rows = []
for _, customer in customers.iterrows():
    # Юрлица потребляют намного больше физлиц
    # У каждого абонента своё "базовое" потребление в месяц, кВт·ч
    if customer["customer_type"] == "физлицо":
        base = np.random.uniform(150, 400)
    else:
        base = np.random.uniform(5000, 30000)

    for i, month in enumerate(months):
        # Сезонность: зимой потребление выше (пик в январе), летом ниже
        season = 1 + 0.35 * np.cos(2 * np.pi * (month.month - 1) / 12)
        # Тренд: потребление растёт примерно на 3% в год
        trend = 1 + 0.03 * i / 12
        # Случайный шум ±8%, как в жизни
        noise = np.random.normal(1, 0.08)

        rows.append({
            "customer_id": customer["customer_id"],
            "period": month.strftime("%d.%m.%Y"),
            "kwh": round(base * season * trend * noise, 1),
        })

consumption = pd.DataFrame(rows)

# ---------- Портим данные ----------
# 1. Пропуски: у 50 случайных строк стираем потребление
missing_idx = np.random.choice(consumption.index, 50, replace=False)
consumption.loc[missing_idx, "kwh"] = np.nan

# 2. Выбросы: у 10 случайных строк потребление в 10 раз больше
outlier_idx = np.random.choice(consumption.index, 10, replace=False)
consumption.loc[outlier_idx, "kwh"] = consumption.loc[outlier_idx, "kwh"] * 10

# 3. Дубликаты: 20 случайных строк добавляем повторно
duplicates = consumption.sample(20, random_state=1)
consumption = pd.concat([consumption, duplicates], ignore_index=True)

# ---------- Сохраняем ----------
os.makedirs("data", exist_ok=True)
customers.to_excel("data/customers.xlsx", index=False)
consumption.to_csv("data/consumption.csv", index=False, encoding="utf-8")

print(f"Абонентов: {len(customers)}")
print(f"Записей о потреблении: {len(consumption)} (из них 20 дубликатов)")
print("Файлы сохранены в папку data/")