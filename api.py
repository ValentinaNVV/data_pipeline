# REST API для интеграции с системами бизнес-анализа:
# выдача результатов последнего запуска и прогноз расхода сохранённой моделью.
# Запуск: uvicorn api:app --reload   Документация: http://127.0.0.1:8000/docs

import logging
from typing import Literal

import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from db import get_engine
from storage import load_last_saved_model

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Data Pipeline API",
    description="Результаты анализа потребления электроэнергии и прогноз расхода",
)

# Кодирование категорий — так же, как в cleaner (encode_label / encode_onehot)
TARIFF_CODES = {"двухзонный": 0, "одноставочный": 1}
CUSTOMER_TYPE_CODES = {"физлицо": 0, "юрлицо": 1}
DISTRICTS = ["Восточный", "Западный", "Северный", "Южный"]

# Порядок признаков должен совпадать с тем, на котором обучалась модель
FEATURE_COLUMNS = (
    ["tariff", "customer_type"]
    + [f"district_{d}" for d in DISTRICTS]
    + ["month", "temperature", "kwh_last_year"]
)


def _latest_run(table):
    """Возвращает строки таблицы результатов за последний запуск конвейера.

    Аргументы:
        table (str): Имя таблицы (только из фиксированного списка внутри модуля).

    Возвращает:
        list of dict: Строки таблицы в виде словарей (готово для JSON).
    """
    # Имя таблицы подставляется в запрос напрямую, поэтому сюда передаются
    # только наши константы, а не данные от пользователя
    query = text(
        f"SELECT * FROM {table} WHERE run_at = (SELECT MAX(run_at) FROM {table})"
    )
    try:
        df = pd.read_sql(query, get_engine())
    except Exception:
        logger.exception("Ошибка чтения таблицы %s", table)
        raise HTTPException(
            status_code=503, detail="База данных недоступна или таблица не создана"
        )

    if df.empty:
        raise HTTPException(
            status_code=404, detail="Результатов пока нет — запустите main.py"
        )

    # NaN нельзя передать в JSON — заменяем на None (в JSON это null)
    df = df.astype(object).where(df.notna(), None)
    return df.to_dict(orient="records")


@app.get("/health")
def health():
    """Проверка, что API работает."""
    return {"status": "ok"}


@app.get("/stats/latest")
def latest_stats():
    """Базовые статистики расхода последнего запуска (все абоненты, физлица, юрлица)."""
    return _latest_run("analysis_stats")


@app.get("/monthly/latest")
def latest_monthly():
    """Расход, температура, тренд и сезонная составляющая по месяцам."""
    return _latest_run("analysis_monthly")


@app.get("/metrics/latest")
def latest_metrics():
    """Метрики качества моделей последнего запуска."""
    return _latest_run("model_metrics")


class PredictRequest(BaseModel):
    """Данные абонента и месяца для прогноза расхода."""

    customer_type: Literal["физлицо", "юрлицо"]
    tariff: Literal["одноставочный", "двухзонный"]
    district: Literal["Восточный", "Западный", "Северный", "Южный"]
    month: int = Field(ge=1, le=12, description="Номер месяца, 1–12")
    temperature: float = Field(description="Средняя температура месяца, °C")
    kwh_last_year: float = Field(
        gt=0, description="Расход того же месяца прошлого года, кВт·ч"
    )


@app.post("/predict")
def predict(request: PredictRequest):
    """Прогноз расхода за месяц лучшей сохранённой моделью."""
    name, model = load_last_saved_model()
    if model is None:
        raise HTTPException(
            status_code=404, detail="Модель не найдена — запустите main.py"
        )

    # Собираем одну строку признаков в том же виде, что при обучении
    row = {
        "tariff": TARIFF_CODES[request.tariff],
        "customer_type": CUSTOMER_TYPE_CODES[request.customer_type],
        **{f"district_{d}": int(request.district == d) for d in DISTRICTS},
        "month": request.month,
        "temperature": request.temperature,
        "kwh_last_year": request.kwh_last_year,
    }
    features = pd.DataFrame([row], columns=FEATURE_COLUMNS)
    prediction = float(model.predict(features)[0])

    return {"model": name, "predicted_kwh": round(prediction, 1)}
