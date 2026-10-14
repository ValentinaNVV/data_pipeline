# reporter.py
# Генерация отчётов: графики (Matplotlib, Seaborn, Plotly), Excel, PDF, отправка по email

import logging
from pathlib import Path

import matplotlib

# Рисуем сразу в файлы, без открытия окон — нужно для запуска по расписанию
matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import seaborn as sns  # noqa: E402
from plotly.subplots import make_subplots  # noqa: E402

# Журнал для этого модуля; __name__ подставит имя файла — "reporter"
logger = logging.getLogger(__name__)

# Короткие названия месяцев для подписей: MONTHS_SHORT[1] -> "янв"
MONTHS_SHORT = [
    "", "янв", "фев", "мар", "апр", "май", "июн",
    "июл", "авг", "сен", "окт", "ноя", "дек",
]


def _prepare_dir(output_dir):
    """Создаёт папку для отчётов, если её нет, и возвращает её как Path."""
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True)
    return output_dir


def plot_trend(series, decomposition, output_dir="reports"):
    """Строит график расхода по месяцам с линией тренда (Matplotlib).

    Аргументы:
        series (pd.Series): Суммарный расход по месяцам (индекс — дата).
        decomposition (DecomposeResult): Результат decompose_series.
        output_dir (str): Папка для сохранения. По умолчанию "reports".

    Возвращает:
        Path: Путь к сохранённому PNG-файлу.
    """
    output_dir = _prepare_dir(output_dir)

    fig, ax = plt.subplots(figsize=(10, 5))
    # Делим на 1000, чтобы на оси были тысячи кВт·ч, а не длинные числа
    ax.plot(series.index, series.values / 1000, marker="o", label="Фактический расход")
    ax.plot(
        decomposition.trend.index,
        decomposition.trend.values / 1000,
        linewidth=3,
        label="Тренд",
    )
    ax.set_title("Суммарное потребление электроэнергии по месяцам")
    ax.set_xlabel("Месяц")
    ax.set_ylabel("тыс. кВт·ч")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()

    path = output_dir / "consumption_trend.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)  # освобождаем память после сохранения
    logger.info("График сохранён: %s", path)
    return path


def plot_seasonality_heatmap(series, output_dir="reports"):
    """Строит тепловую карту расхода «год * месяц» (Seaborn).

    Аргументы:
        series (pd.Series): Суммарный расход по месяцам (индекс — дата).
        output_dir (str): Папка для сохранения. По умолчанию "reports".

    Возвращает:
        Path: Путь к сохранённому PNG-файлу.
    """
    output_dir = _prepare_dir(output_dir)

    # Раскладываем ряд в таблицу: строки — годы, колонки — месяцы
    table = pd.DataFrame({
        "year": series.index.year,
        "month": series.index.month,
        "kwh": series.values / 1000,
    })
    pivot = table.pivot(index="year", columns="month", values="kwh")
    pivot.columns = [MONTHS_SHORT[m] for m in pivot.columns]

    fig, ax = plt.subplots(figsize=(12, 3.5))
    sns.heatmap(
        pivot,
        annot=True,          # подписать число в каждой клетке
        fmt=".0f",           # без знаков после запятой
        cmap="Blues",        # от светло-голубого (мало) к тёмно-синему (много)
        cbar_kws={"label": "тыс. кВт·ч"},
        ax=ax,
    )
    ax.set_title("Сезонность потребления: расход по годам и месяцам")
    ax.set_xlabel("")
    ax.set_ylabel("Год")
    fig.tight_layout()

    path = output_dir / "seasonality_heatmap.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    logger.info("График сохранён: %s", path)
    return path


def plot_interactive(series, temperature, output_dir="reports"):
    """Строит интерактивный график расхода и температуры (Plotly, HTML).

    Аргументы:
        series (pd.Series): Суммарный расход по месяцам (индекс — дата).
        temperature (pd.Series): Средняя температура по месяцам (индекс — дата).
        output_dir (str): Папка для сохранения. По умолчанию "reports".

    Возвращает:
        Path: Путь к сохранённому HTML-файлу.
    """
    output_dir = _prepare_dir(output_dir)

    # Две оси Y: слева расход, справа температура
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Bar(x=series.index, y=series.values, name="Расход, кВт·ч"),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=temperature.index,
            y=temperature.values,
            name="Температура, °C",
            mode="lines+markers",
        ),
        secondary_y=True,
    )
    fig.update_layout(title="Потребление электроэнергии и температура по месяцам")
    fig.update_yaxes(title_text="кВт·ч", secondary_y=False)
    fig.update_yaxes(title_text="°C", secondary_y=True)

    path = output_dir / "consumption_vs_temperature.html"
    fig.write_html(str(path))
    logger.info("Интерактивный график сохранён: %s", path)
    return path


if __name__ == "__main__":
    from analyzer import aggregate_monthly, decompose_series
    from cleaner import convert_dates, fill_by_billing_rules, remove_duplicates, replace_outliers
    from loader import load_api, load_csv

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Подготовка данных: очистка, ряд по месяцам, декомпозиция
    df = load_csv("data/consumption.csv")
    df = remove_duplicates(df)
    df = convert_dates(df, "period")
    df = replace_outliers(df, "kwh", group_by="customer_id")
    df = fill_by_billing_rules(df)
    monthly = aggregate_monthly(df)
    decomposition = decompose_series(monthly)

    # Температура по месяцам
    weather = load_api(
        "https://archive-api.open-meteo.com/v1/archive",
        params={
            "latitude": 55.75,
            "longitude": 37.62,
            "start_date": "2023-01-01",
            "end_date": "2025-12-31",
            "daily": "temperature_2m_mean",
            "timezone": "Europe/Moscow",
        },
        data_key="daily",
    )
    monthly_temp = aggregate_monthly(
        weather, column="temperature_2m_mean", date_column="time", agg="mean"
    )

    # Графики
    plot_trend(monthly, decomposition)
    plot_seasonality_heatmap(monthly)
    plot_interactive(monthly, monthly_temp)