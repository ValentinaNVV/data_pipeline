# Тесты загрузки данных: CSV, Excel, API (без реальной сети)

import pandas as pd
import pytest

import loader


def test_load_csv_reads_file(tmp_path):
    """CSV загружается в DataFrame с правильными размерами и значениями."""
    # tmp_path — временная папка, которую pytest создаёт и удаляет сам
    path = tmp_path / "data.csv"
    pd.DataFrame({"customer_id": [1, 2], "kwh": [100.5, 200.0]}).to_csv(
        path, index=False
    )

    df = loader.load_csv(path)

    assert df.shape == (2, 2)
    assert df["kwh"].tolist() == [100.5, 200.0]


def test_load_csv_missing_file_raises():
    """Несуществующий файл — понятная ошибка FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        loader.load_csv("no_such_file.csv")


def test_load_excel_reads_file(tmp_path):
    """Excel загружается в DataFrame."""
    path = tmp_path / "data.xlsx"
    pd.DataFrame({"district": ["Северный", "Южный"]}).to_excel(path, index=False)

    df = loader.load_excel(path)

    assert df["district"].tolist() == ["Северный", "Южный"]


class FakeResponse:
    """Подделка ответа requests: возвращает заданный JSON без обращения к сети."""

    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass  # "сервер ответил успешно"

    def json(self):
        return self._payload


def test_load_api_extracts_data_key(monkeypatch):
    """Из ответа API берётся часть по ключу data_key и превращается в таблицу."""
    payload = {"daily": {"time": ["2023-01-01", "2023-01-02"], "temp": [-3.0, -5.0]}}
    # monkeypatch подменяет requests.get на время теста — в интернет никто не ходит
    monkeypatch.setattr(
        loader.requests, "get", lambda *args, **kwargs: FakeResponse(payload)
    )

    df = loader.load_api("https://example.com", data_key="daily")

    assert df.shape == (2, 2)
    assert df["temp"].tolist() == [-3.0, -5.0]


def test_load_api_missing_key_raises(monkeypatch):
    """Если ключа нет в ответе — ошибка KeyError, а не пустая таблица."""
    monkeypatch.setattr(
        loader.requests, "get", lambda *args, **kwargs: FakeResponse({"other": []})
    )

    with pytest.raises(KeyError):
        loader.load_api("https://example.com", data_key="daily")
