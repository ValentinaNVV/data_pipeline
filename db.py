# Подключение к PostgreSQL. Параметры берутся из файла .env

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine

# Читаем .env и кладём значения в переменные окружения
load_dotenv()


def get_engine():
    """Создаёт и возвращает объект подключения к базе данных PostgreSQL."""
    url = (
        f"postgresql+psycopg2://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
        f"@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
    )
    return create_engine(url)