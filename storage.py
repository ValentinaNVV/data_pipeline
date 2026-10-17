# Сохранение результатов анализа и обученных моделей в PostgreSQL

import logging
import pickle
from datetime import datetime

from sqlalchemy import text

from db import get_engine

# Журнал для этого модуля; __name__ подставит имя файла — "storage"
logger = logging.getLogger(__name__)


def save_tables(tables, run_at=None, engine=None):
    """Дописывает таблицы результатов в базу данных с отметкой времени запуска.

    Каждая таблица дополняется колонкой run_at, поэтому результаты разных
    запусков накапливаются и их можно сравнивать.

    Аргументы:
        tables (dict): {имя_таблицы_в_БД: pd.DataFrame}. Имена колонок — латиницей.
        run_at (datetime, optional): Время запуска. По умолчанию — текущее.
        engine (Engine, optional): Подключение к БД. По умолчанию — из get_engine().

    Возвращает:
        None
    """
    engine = engine or get_engine()
    run_at = run_at or datetime.now()

    for name, df in tables.items():
        df = df.copy()
        df.insert(0, "run_at", run_at)  # первая колонка — когда был запуск
        # if_exists="append": дописываем, а не перезаписываем — копим историю
        df.to_sql(name, engine, if_exists="append", index=False)
        logger.info("Сохранено в таблицу '%s': %d строк", name, len(df))


def save_model(name, model, metrics, run_at=None, engine=None):
    """Сохраняет обученную модель и её метрики в таблицу ml_models.

    Модель сериализуется через pickle и хранится в колонке типа BYTEA.

    Аргументы:
        name (str): Название модели (например, "LinearRegression").
        model: Обученная модель scikit-learn.
        metrics (dict): Метрики качества: {"MAE": ..., "RMSE": ..., "R2": ...}.
        run_at (datetime, optional): Время запуска. По умолчанию — текущее.
        engine (Engine, optional): Подключение к БД. По умолчанию — из get_engine().

    Возвращает:
        None
    """
    engine = engine or get_engine()
    run_at = run_at or datetime.now()

    create_sql = text("""
        CREATE TABLE IF NOT EXISTS ml_models (
            id     SERIAL PRIMARY KEY,
            run_at TIMESTAMP NOT NULL,
            name   TEXT NOT NULL,
            mae    DOUBLE PRECISION,
            rmse   DOUBLE PRECISION,
            r2     DOUBLE PRECISION,
            model  BYTEA NOT NULL
        )
    """)
    insert_sql = text("""
        INSERT INTO ml_models (run_at, name, mae, rmse, r2, model)
        VALUES (:run_at, :name, :mae, :rmse, :r2, :model)
    """)

    # engine.begin() — транзакция: либо выполнится всё, либо ничего
    with engine.begin() as conn:
        conn.execute(create_sql)
        conn.execute(insert_sql, {
            "run_at": run_at,
            "name": name,
            "mae": float(metrics["MAE"]),
            "rmse": float(metrics["RMSE"]),
            "r2": float(metrics["R2"]),
            "model": pickle.dumps(model),  # модель -> байты
        })
    logger.info("Модель '%s' сохранена в таблицу 'ml_models' (R2 = %s)", name, metrics["R2"])


def load_latest_model(name, engine=None):
    """Загружает из базы последнюю сохранённую версию модели.

    Важно: pickle можно загружать только из доверенного источника —
    здесь это наша собственная база данных.

    Аргументы:
        name (str): Название модели.
        engine (Engine, optional): Подключение к БД. По умолчанию — из get_engine().

    Возвращает:
        Обученная модель или None, если модель с таким названием не найдена.
    """
    engine = engine or get_engine()
    query = text("""
        SELECT model FROM ml_models
        WHERE name = :name
        ORDER BY run_at DESC
        LIMIT 1
    """)
    with engine.connect() as conn:
        row = conn.execute(query, {"name": name}).fetchone()

    if row is None:
        logger.warning("Модель '%s' в базе не найдена", name)
        return None
    logger.info("Загружена последняя версия модели '%s'", name)
    return pickle.loads(row[0])  # байты -> модель

def load_last_saved_model(engine=None):
    """Загружает модель, сохранённую последней (лучшую модель последнего запуска).

    Аргументы:
        engine (Engine, optional): Подключение к БД. По умолчанию — из get_engine().

    Возвращает:
        tuple: (название, модель) или (None, None), если моделей в базе нет.
    """
    engine = engine or get_engine()
    query = text("SELECT name, model FROM ml_models ORDER BY run_at DESC, id DESC LIMIT 1")
    with engine.connect() as conn:
        row = conn.execute(query).fetchone()

    if row is None:
        logger.warning("В базе нет сохранённых моделей")
        return None, None
    return row[0], pickle.loads(row[1])