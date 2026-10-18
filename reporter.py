# reporter.py
# Генерация отчётов: графики (Matplotlib, Seaborn, Plotly), Excel, PDF, отправка по email

import logging
import mimetypes
import os
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path

import matplotlib

# Рисуем сразу в файлы, без открытия окон — нужно для запуска по расписанию
matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import seaborn as sns  # noqa: E402
from openpyxl.styles import Font  # noqa: E402
from plotly.subplots import make_subplots  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # noqa: E402
from reportlab.lib.units import mm  # noqa: E402
from reportlab.lib.utils import ImageReader  # noqa: E402
from reportlab.pdfbase import pdfmetrics  # noqa: E402
from reportlab.pdfbase.ttfonts import TTFont  # noqa: E402
from reportlab.platypus import (
    Image,
    Paragraph,  # noqa: E402
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# Журнал для этого модуля; __name__ подставит имя файла — "reporter"
logger = logging.getLogger(__name__)

# Короткие названия месяцев для подписей: MONTHS_SHORT[1] -> "янв"
MONTHS_SHORT = [
    "",
    "янв",
    "фев",
    "мар",
    "апр",
    "май",
    "июн",
    "июл",
    "авг",
    "сен",
    "окт",
    "ноя",
    "дек",
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
    table = pd.DataFrame(
        {
            "year": series.index.year,
            "month": series.index.month,
            "kwh": series.values / 1000,
        }
    )
    pivot = table.pivot(index="year", columns="month", values="kwh")
    pivot.columns = [MONTHS_SHORT[m] for m in pivot.columns]

    fig, ax = plt.subplots(figsize=(12, 3.5))
    sns.heatmap(
        pivot,
        annot=True,  # подписать число в каждой клетке
        fmt=".0f",  # без знаков после запятой
        cmap="Blues",  # от светло-голубого (мало) к тёмно-синему (много)
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


def export_to_excel(sheets, path):
    """Сохраняет несколько таблиц в один Excel-файл, каждую на отдельный лист.

    Заголовки выделяются жирным, ширина колонок подбирается по содержимому,
    первая строка и первая колонка закрепляются.

    Аргументы:
        sheets (dict): {название_листа: pd.DataFrame}. Название — до 31 символа.
        path (str | Path): Путь к файлу .xlsx.

    Возвращает:
        Path: Путь к сохранённому файлу.
    """
    path = Path(path)
    path.parent.mkdir(exist_ok=True)

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for name, table in sheets.items():
            table.to_excel(writer, sheet_name=name)
            ws = writer.sheets[name]  # лист openpyxl для оформления

            # Жирные заголовки
            for cell in ws[1]:
                cell.font = Font(bold=True)

            # Ширина колонки — по самому длинному значению (но не шире 50)
            for column_cells in ws.columns:
                length = max(
                    len(str(c.value)) for c in column_cells if c.value is not None
                )
                ws.column_dimensions[column_cells[0].column_letter].width = min(
                    length + 2, 50
                )

            # Заголовок и первая колонка не уезжают при прокрутке
            ws.freeze_panes = "B2"

    logger.info("Excel-отчёт сохранён: %s (листы: %s)", path, list(sheets))
    return path


def _register_fonts():
    """Подключает шрифт DejaVu Sans (с кириллицей) из состава matplotlib."""
    font_dir = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
    pdfmetrics.registerFont(TTFont("DejaVu", str(font_dir / "DejaVuSans.ttf")))
    pdfmetrics.registerFont(
        TTFont("DejaVu-Bold", str(font_dir / "DejaVuSans-Bold.ttf"))
    )


def _df_to_pdf_table(df):
    """Превращает DataFrame в оформленную таблицу ReportLab."""
    df = df.reset_index()
    data = [list(map(str, df.columns))] + df.astype(str).values.tolist()

    table = Table(data, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "DejaVu"),
                ("FONTNAME", (0, 0), (-1, 0), "DejaVu-Bold"),  # заголовок жирным
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DCE6F1")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ALIGN", (1, 1), (-1, -1), "RIGHT"),  # числа по правому краю
            ]
        )
    )
    return table


def build_pdf_report(path, title, summary, tables, images):
    """Собирает PDF-отчёт: заголовок, ключевые выводы, таблицы и графики.

    Аргументы:
        path (str | Path): Путь к файлу .pdf.
        title (str): Заголовок отчёта.
        summary (list of str): Ключевые выводы, по одному на строку.
        tables (dict): {подзаголовок: pd.DataFrame} — таблицы для отчёта.
        images (list): Пути к PNG-графикам.

    Возвращает:
        Path: Путь к сохранённому файлу.
    """
    path = Path(path)
    path.parent.mkdir(exist_ok=True)
    _register_fonts()

    # Стили текста на основе стандартных, но со шрифтом с кириллицей
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "TitleRu", parent=styles["Title"], fontName="DejaVu-Bold"
    )
    heading_style = ParagraphStyle(
        "HeadingRu", parent=styles["Heading2"], fontName="DejaVu-Bold"
    )
    text_style = ParagraphStyle(
        "TextRu", parent=styles["Normal"], fontName="DejaVu", leading=14
    )

    content_width = A4[0] - 40 * mm  # ширина страницы минус поля

    # story — список элементов, которые ReportLab выложит на страницы по порядку
    story = [Paragraph(title, title_style), Spacer(1, 6 * mm)]

    story.append(Paragraph("Ключевые выводы", heading_style))
    for line in summary:
        story.append(Paragraph(f"• {line}", text_style))

    for name, table in tables.items():
        story += [
            Spacer(1, 5 * mm),
            Paragraph(name, heading_style),
            _df_to_pdf_table(table),
        ]

    for image_path in images:
        # Высоту картинки считаем по её пропорциям, чтобы не исказить
        img_w, img_h = ImageReader(str(image_path)).getSize()
        story += [
            Spacer(1, 5 * mm),
            Image(
                str(image_path),
                width=content_width,
                height=content_width * img_h / img_w,
            ),
        ]

    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
    )
    doc.build(story)
    logger.info("PDF-отчёт сохранён: %s", path)
    return path


def send_report_email(attachments, subject, body, recipients=None):
    """Отправляет отчёты по email через SMTP (SSL).

    Настройки берутся из переменных окружения (.env): SMTP_HOST, SMTP_PORT,
    SMTP_USER, SMTP_PASSWORD, REPORT_RECIPIENTS (адреса через запятую).
    Если настройки не заданы, отправка пропускается с предупреждением —
    так проект можно запускать и без почты.

    Аргументы:
        attachments (list): Пути к файлам для вложения.
        subject (str): Тема письма.
        body (str): Текст письма.
        recipients (list of str, optional): Получатели. По умолчанию — из REPORT_RECIPIENTS.

    Возвращает:
        bool: True, если письмо отправлено, False, если отправка пропущена.
    """
    host = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "465"))
    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASSWORD")
    if recipients is None:
        recipients = [
            r.strip()
            for r in os.getenv("REPORT_RECIPIENTS", "").split(",")
            if r.strip()
        ]

    if not all([host, user, password]) or not recipients:
        logger.warning("Настройки почты не заданы в .env — отправка отчёта пропущена")
        return False

    # Собираем письмо: заголовки, текст, вложения
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = ", ".join(recipients)
    msg.set_content(body)

    for file_path in attachments:
        file_path = Path(file_path)
        # Определяем тип файла по расширению (например, application/pdf)
        mime_type, _ = mimetypes.guess_type(file_path.name)
        maintype, subtype = (mime_type or "application/octet-stream").split("/", 1)
        msg.add_attachment(
            file_path.read_bytes(),
            maintype=maintype,
            subtype=subtype,
            filename=file_path.name,
        )

    # Защищённое соединение с почтовым сервером, вход и отправка
    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(host, port, context=context, timeout=30) as server:
        server.login(user, password)
        server.send_message(msg)

    logger.info(
        "Отчёт отправлен: %s (вложения: %s)",
        recipients,
        [Path(p).name for p in attachments],
    )
    return True


if __name__ == "__main__":
    from analyzer import aggregate_monthly, decompose_series
    from cleaner import (
        convert_dates,
        fill_by_billing_rules,
        remove_duplicates,
        replace_outliers,
    )
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
