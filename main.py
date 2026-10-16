# Точка входа: запускает весь конвейер — загрузка, валидация, очистка, анализ, отчёты

import logging
from pathlib import Path

import pandas as pd
import sys
from datetime import date, datetime
from logging.handlers import RotatingFileHandler
from storage import save_model, save_tables

from dotenv import load_dotenv


from analyzer import (
    MONTHS,
    aggregate_monthly,
    basic_stats,
    build_features,
    decompose_series,
    detect_anomalies,
    merge_customer_data,
    train_and_evaluate,
)
from cleaner import (
    convert_dates,
    encode_label,
    encode_onehot,
    fill_by_billing_rules,
    remove_duplicates,
    replace_outliers,
)
from loader import load_api, load_csv, load_excel
from reporter import (
    build_pdf_report,
    export_to_excel,
    plot_interactive,
    plot_seasonality_heatmap,
    plot_trend,
    send_report_email,
)
from validator import check_duplicates, check_missing, check_types, detect_outliers_iqr

# Загружаем настройки из .env (база данных, почта)
load_dotenv()

logger = logging.getLogger("main")

# Источник погоды: архив Open-Meteo, средняя дневная температура
WEATHER_URL = "https://archive-api.open-meteo.com/v1/archive"
WEATHER_PARAMS = {
    "latitude": 55.75,
    "longitude": 37.62,
    "start_date": "2023-01-01",
    "end_date": "2025-12-31",
    "daily": "temperature_2m_mean",
    "timezone": "Europe/Moscow",
}

def setup_logging(log_dir="logs"):
    """Настраивает журнал: вывод в консоль и в файл с ротацией.

    Файл logs/pipeline.log ограничен 1 МБ; при переполнении он архивируется
    (pipeline.log.1 ... .5), самый старый архив удаляется.

    Аргументы:
        log_dir (str): Папка для файлов журнала. По умолчанию "logs".

    Возвращает:
        None
    """
    Path(log_dir).mkdir(exist_ok=True)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    file_handler = RotatingFileHandler(
        Path(log_dir) / "pipeline.log",
        maxBytes=1_000_000,   # 1 МБ на один файл
        backupCount=5,        # хранить 5 архивных файлов
        encoding="utf-8",     # чтобы русский текст читался в любом редакторе
    )
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    root = logging.getLogger()   # общий журнал, в который пишут все модули
    root.setLevel(logging.INFO)
    root.handlers.clear()        # на случай повторного вызова — без дублей строк
    root.addHandler(file_handler)
    root.addHandler(console_handler)


def run_pipeline(output_dir="reports"):
    """Запускает полный цикл обработки данных и формирует отчёты.

    Этапы: загрузка → валидация → очистка → анализ → отчёты (графики, Excel, PDF).

    Аргументы:
        output_dir (str): Папка для отчётов. По умолчанию "reports".

    Возвращает:
        dict: Пути к отчётам ("excel", "pdf") и таблицы результатов
            ("stats", "metrics", "monthly").
    """
    output_dir = Path(output_dir)
    logger.info("=== Запуск конвейера ===")

    # 1. Загрузка
    consumption = load_csv("data/consumption.csv")
    customers = load_excel("data/customers.xlsx")
    weather = load_api(WEATHER_URL, params=WEATHER_PARAMS, data_key="daily")

    # 2. Валидация сырых данных
    check_duplicates(consumption)
    check_missing(consumption)
    check_types(consumption, {"customer_id": "numeric", "period": "datetime", "kwh": "numeric"})
    detect_outliers_iqr(consumption, "kwh", group_by="customer_id")

    # 3. Очистка
    df = remove_duplicates(consumption)
    df = convert_dates(df, "period")
    df = replace_outliers(df, "kwh", group_by="customer_id")
    df = fill_by_billing_rules(df)

    customers_enc = encode_label(customers, ["tariff", "customer_type"])
    customers_enc = encode_onehot(customers_enc, ["district"])

    # 4. Анализ
    merged = merge_customer_data(df, customers)
    stats = {"Все абоненты": basic_stats(df, "kwh")}
    for ctype in ["физлицо", "юрлицо"]:
        stats[ctype] = basic_stats(merged[merged["customer_type"] == ctype], "kwh")

    monthly = aggregate_monthly(df)
    decomposition = decompose_series(monthly)
    anomalies = detect_anomalies(decomposition)

    monthly_temp = aggregate_monthly(
        weather, column="temperature_2m_mean", date_column="time", agg="mean"
    )
    X, y = build_features(df, customers_enc, monthly_temp)
    results = train_and_evaluate(X, y)

    # 5. Таблицы для отчётов
    stats_df = pd.DataFrame(stats).T
    stats_df.index.name = "Группа"

    metrics_df = pd.DataFrame(
        {name: {k: v for k, v in r.items() if k != "model"} for name, r in results.items()}
    ).T
    metrics_df.index.name = "Модель"

    monthly_df = pd.DataFrame({
        "Расход, кВт·ч": monthly.round(1),
        "Температура, °C": monthly_temp.round(1),
        "Тренд": decomposition.trend.round(0),
        "Сезонная составляющая": decomposition.seasonal.round(0),
    })
    monthly_df.index = monthly_df.index.strftime("%m.%Y")
    monthly_df.index.name = "Месяц"

    if anomalies.empty:
        anomalies_df = pd.DataFrame({"Результат": ["Аномальных месяцев не найдено"]})
    else:
        anomalies_df = anomalies.round(0).to_frame("Остаток")
        anomalies_df.index = anomalies_df.index.strftime("%m.%Y")

    # Ключевые выводы для PDF
    trend = decomposition.trend.dropna()
    growth = (trend.iloc[-1] / trend.iloc[0] - 1) * 100
    best_name = metrics_df["R2"].idxmax()
    summary = [
        f"Обработано записей потребления: {len(df)}, абонентов: {df['customer_id'].nunique()}.",
        f"Рост потребления по тренду: {growth:.1f}% за период.",
        f"Пик сезона: {MONTHS[decomposition.seasonal.idxmax().month]}, "
        f"спад: {MONTHS[decomposition.seasonal.idxmin().month]}.",
        f"Аномальных месяцев: {len(anomalies)}.",
        f"Лучшая модель прогноза: {best_name} (R² = {metrics_df.loc[best_name, 'R2']}).",
    ]

    # 6. Отчёты
    trend_png = plot_trend(monthly, decomposition, output_dir)
    heatmap_png = plot_seasonality_heatmap(monthly, output_dir)
    plot_interactive(monthly, monthly_temp, output_dir)

    excel_path = export_to_excel(
        {
            "Статистика": stats_df,
            "По месяцам": monthly_df,
            "Модели": metrics_df,
            "Аномалии": anomalies_df,
        },
        output_dir / "report.xlsx",
    )
    pdf_path = build_pdf_report(
        output_dir / "report.pdf",
        title="Отчёт по потреблению электроэнергии",
        summary=summary,
        tables={"Базовые статистики, кВт·ч": stats_df, "Качество моделей": metrics_df},
        images=[trend_png, heatmap_png],
    )

     # 7. Рассылка. Ошибка почты не должна "уронить" конвейер: отчёты уже сохранены
    try:
        send_report_email(
            attachments=[excel_path, pdf_path],
            subject=f"Отчёт по потреблению электроэнергии от {date.today():%d.%m.%Y}",
            body="\n".join(["Добрый день!", "", "Во вложении автоматический отчёт.", "", *summary]),
        )
    except Exception:
        # logger.exception пишет в журнал и сообщение, и подробности ошибки
        logger.exception("Не удалось отправить отчёт по почте")

    # 8. Сохраняем результаты в БД
    # Названия колонок — латиницей, чтобы с ними было удобно работать в SQL и API
    try:
        run_at = datetime.now()
        monthly_db = pd.DataFrame({
            "month": monthly.index,
            "kwh": monthly.values,
            "temperature": monthly_temp.reindex(monthly.index).values,
            "trend": decomposition.trend.values,
            "seasonal": decomposition.seasonal.values,
        })
        stats_db = pd.DataFrame(stats).T.rename_axis("customer_group").reset_index()
        # В PostgreSQL имена колонок — строчными, иначе их нужно писать в кавычках
        metrics_db = metrics_df.rename(columns=str.lower).rename_axis("model_name").reset_index()

        save_tables(
            {
                "analysis_monthly": monthly_db,
                "analysis_stats": stats_db,
                "model_metrics": metrics_db,
            },
            run_at=run_at,
        )
        save_model(
            best_name,
            results[best_name]["model"],
            metrics_df.loc[best_name].to_dict(),
            run_at=run_at,
        )
    except Exception:
        logger.exception("Не удалось сохранить результаты в базу данных")

    logger.info("=== Конвейер завершён ===")
    return {
        "excel": excel_path,
        "pdf": pdf_path,
        "stats": stats_df,
        "metrics": metrics_df,
        "monthly": monthly_df,
    }


if __name__ == "__main__":
    setup_logging()
    try:
        run_pipeline()
    except Exception:
        logger.exception("Конвейер завершился с ошибкой")
        # Код выхода 1 — сигнал планировщику задач, что запуск неудачный
        sys.exit(1)