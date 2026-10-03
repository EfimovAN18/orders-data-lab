import base64
import csv
import html
import json
import os
import sqlite3
import tempfile
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from importlib.resources import files
from pathlib import Path


def query(connection: sqlite3.Connection, filename: str) -> list[dict]:
    sql = files("orders_lab.analytics").joinpath(filename).read_text(encoding="utf-8")
    return [dict(row) for row in connection.execute(sql)]


def ratio(numerator: int, denominator: int, scale: int = 1) -> str | None:
    if not denominator:
        return None
    value = Decimal(numerator) * scale / Decimal(denominator)
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def compute_metrics(connection: sqlite3.Connection) -> dict:
    metrics = query(connection, "summary.sql")[0]
    metrics["revenue_rub"] = str(
        (Decimal(metrics["revenue_kopecks"]) / 100).quantize(Decimal("0.01"))
    )
    metrics["average_order_value_rub"] = ratio(
        metrics["revenue_kopecks"], metrics["paid_orders"] * 100
    )
    metrics["repeat_customer_percent"] = ratio(
        metrics["repeat_customers"], metrics["paying_customers"], 100
    )
    metrics["cancellation_percent"] = ratio(
        metrics["cancelled_orders"], metrics["total_orders"], 100
    )
    return metrics


def display_money(value: str | int | None) -> str:
    if value is None:
        return "—"
    return f"{Decimal(value):,.2f}".replace(",", " ").replace(".", ",") + " ₽"


def fill_dates(rows: list[dict], start: str | None, end: str | None) -> list[dict]:
    if start is None or end is None:
        return []
    by_date = {row["order_date"]: row for row in rows}
    current, last = date.fromisoformat(start), date.fromisoformat(end)
    result = []
    while current <= last:
        day = current.isoformat()
        result.append(
            by_date.get(
                day,
                {
                    "order_date": day,
                    "total_orders": 0,
                    "paid_orders": 0,
                    "revenue_kopecks": 0,
                    "cancelled_orders": 0,
                },
            )
        )
        current += timedelta(days=1)
    return result


def build_chart(daily: list[dict], categories: list[dict], target: Path) -> None:
    os.environ.setdefault(
        "MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "orders-lab-matplotlib")
    )
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    with plt.rc_context(
        {
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "axes.spines.top": False,
            "axes.spines.right": False,
        }
    ):
        figure, axes = plt.subplots(2, 1, figsize=(11, 7), layout="constrained")
        figure.set_facecolor("#f5f7fb")
        axes[0].set_title("Выручка по дате создания заказа · ₽", loc="left", fontweight="bold")
        if daily:
            dates = [date.fromisoformat(row["order_date"]) for row in daily]
            values = [row["revenue_kopecks"] / 100 for row in daily]
            axes[0].plot(dates, values, color="#2563eb", linewidth=1.8)
            axes[0].fill_between(dates, values, color="#2563eb", alpha=0.12)
            axes[0].xaxis.set_major_locator(mdates.AutoDateLocator(minticks=3, maxticks=8))
            axes[0].xaxis.set_major_formatter(mdates.DateFormatter("%d.%m.%Y"))
        else:
            axes[0].text(0.5, 0.5, "Нет заказов", ha="center", transform=axes[0].transAxes)
        axes[0].set_ylim(bottom=0)
        axes[0].grid(axis="y", alpha=0.2)
        axes[1].set_title("Выручка по категориям · ₽", loc="left", fontweight="bold")
        if categories:
            subset = list(reversed(categories[:8]))
            axes[1].barh(
                [row["category"] for row in subset],
                [row["revenue_kopecks"] / 100 for row in subset],
                color="#0d9488",
                height=0.6,
            )
        else:
            axes[1].text(
                0.5, 0.5, "Нет оплаченных заказов", ha="center", transform=axes[1].transAxes
            )
        axes[1].grid(axis="x", alpha=0.2)
        figure.savefig(target, dpi=145)
        plt.close(figure)


def write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def make_table(headers: list[str], rows: list[list[str]]) -> str:
    head = "".join(f"<th>{html.escape(value)}</th>" for value in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{html.escape(value)}</td>" for value in row) + "</tr>"
        for row in rows
    )
    if not rows:
        body = f'<tr><td colspan="{len(headers)}">Нет данных</td></tr>'
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def build_report(warehouse: Path, output_dir: Path) -> dict:
    warehouse = Path(warehouse)
    if not warehouse.exists():
        raise ValueError("Аналитическая база отсутствует. Сначала выполните pipeline или demo.")
    with sqlite3.connect(warehouse.resolve().as_uri() + "?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("BEGIN")
        last_run = connection.execute(
            "SELECT * FROM etl_runs WHERE status='success' ORDER BY finished_at DESC LIMIT 1"
        ).fetchone()
        if last_run is None:
            raise ValueError("Нет успешной загрузки данных")
        metrics = compute_metrics(connection)
        metrics["etl_run_id"] = last_run["run_id"]
        metrics["snapshot_at"] = last_run["finished_at"]
        demo_count = connection.execute(
            "SELECT COUNT(*) FROM fact_orders WHERE external_id LIKE 'demo-order-%'"
        ).fetchone()[0]
        metrics["demo_only"] = metrics["total_orders"] > 0 and demo_count == metrics["total_orders"]
        daily = fill_dates(
            [
                dict(row)
                for row in connection.execute("SELECT * FROM mart_daily_sales ORDER BY order_date")
            ],
            metrics["date_from"],
            metrics["date_to"],
        )
        categories = query(connection, "categories.sql")
        monthly = query(connection, "monthly.sql")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    chart_path = output_dir / "sales.png"
    build_chart(daily, categories, chart_path)
    (output_dir / "metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    write_csv(
        output_dir / "daily_sales.csv",
        daily,
        ["order_date", "total_orders", "paid_orders", "revenue_kopecks", "cancelled_orders"],
    )
    write_csv(
        output_dir / "categories.csv",
        categories,
        ["category", "units_sold", "revenue_kopecks", "paid_orders"],
    )
    write_csv(
        output_dir / "monthly_sales.csv",
        monthly,
        ["month", "revenue_kopecks", "paid_orders", "growth_percent"],
    )

    period = (
        f"{metrics['date_from']} — {metrics['date_to']}"
        if metrics["date_from"]
        else "Пустой набор данных"
    )
    note = (
        "Синтетические демонстрационные данные: выводы не описывают реальный бизнес."
        if metrics["demo_only"]
        else "Учебный отчёт по загруженному снимку данных."
    )
    observations = [
        f"Заказов в снимке: {metrics['total_orders']}; сейчас оплачены: {metrics['paid_orders']}; отменены: {metrics['cancelled_orders']}.",
        f"Выручка: {display_money(metrics['revenue_rub'])}. Средний чек оплаченного заказа: {display_money(metrics['average_order_value_rub'])}.",
    ]
    if categories and metrics["revenue_kopecks"]:
        top = categories[0]
        share = ratio(top["revenue_kopecks"], metrics["revenue_kopecks"], 100)
        observations.append(
            f"Наибольшая выручка у категории «{top['category']}»: {share}% выручки снимка."
        )
    if metrics["paying_customers"]:
        observations.append(
            f"Повторных покупателей: {metrics['repeat_customers']} из {metrics['paying_customers']} ({metrics['repeat_customer_percent']}%). Покупатель считается повторным при двух и более оплаченных заказах в снимке."
        )
    observations.append(
        "Для объяснения изменений нужны данные о трафике, рекламе, возвратах и себестоимости; этот набор не позволяет рассчитать прибыль или доказать причины изменений."
    )
    assumptions = "Выручка учитывает только текущий статус paid и относится к дате создания заказа в UTC. Отмена исключает заказ из выручки при следующей загрузке. Это не отчёт о движении денег; частичные возвраты и история оплат не моделируются."
    markdown = (
        f"# Аналитика заказов\n\n{note}\n\nПериод: {period}.\n\n"
        + "\n".join(f"- {text}" for text in observations)
        + f"\n\n## Определения\n\n{assumptions}\n\n![Графики продаж](sales.png)\n"
    )
    (output_dir / "analysis.md").write_text(markdown, encoding="utf-8")

    cards = [
        ("Выручка", display_money(metrics["revenue_rub"])),
        ("Оплаченные заказы", str(metrics["paid_orders"])),
        ("Средний чек", display_money(metrics["average_order_value_rub"])),
        (
            "Повторные покупатели",
            f"{metrics['repeat_customer_percent']}%"
            if metrics["repeat_customer_percent"] is not None
            else "—",
        ),
    ]
    card_html = "".join(
        f"<div class='card'><span>{html.escape(label)}</span><strong>{html.escape(value)}</strong></div>"
        for label, value in cards
    )
    category_table = make_table(
        ["Категория", "Единиц продано", "Выручка"],
        [
            [
                row["category"],
                str(row["units_sold"]),
                display_money(str(Decimal(row["revenue_kopecks"]) / 100)),
            ]
            for row in categories
        ],
    )
    monthly_table = make_table(
        ["Месяц", "Оплаченные заказы", "Выручка", "Изменение к предыдущему месяцу"],
        [
            [
                row["month"][:7],
                str(row["paid_orders"]),
                display_money(str(Decimal(row["revenue_kopecks"]) / 100)),
                "—" if row["growth_percent"] is None else f"{row['growth_percent']}%",
            ]
            for row in monthly
        ],
    )
    chart_data = base64.b64encode(chart_path.read_bytes()).decode()
    document = f"""<!doctype html>
<html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Orders Data Lab — аналитика</title>
<style>
body{{margin:0;background:#f5f7fb;color:#15243b;font:16px/1.6 system-ui,sans-serif}}
main{{max-width:1080px;margin:0 auto;padding:36px 24px}}h1{{font-size:38px;line-height:1.15;margin:10px 0}}
.eyebrow{{color:#2563eb;font-weight:700;letter-spacing:.13em;font-size:13px}}.muted{{color:#52627a}}
.cards{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;margin:28px 0}}
.card,section{{background:white;border:1px solid #dfe7ef;border-radius:14px;padding:22px}}.card span{{display:block;color:#52627a;font-size:13px}}
.card strong{{font-size:23px;display:block;margin-top:8px}}section{{margin:18px 0}}h2{{font-size:21px;margin-top:0}}
img{{max-width:100%;height:auto}}table{{width:100%;border-collapse:collapse}}td,th{{padding:12px 10px;text-align:left;border-bottom:1px solid #e6edf5}}th{{font-size:13px;color:#52627a}}li{{margin:10px 0}}.table-wrap{{overflow-x:auto}}
@media(max-width:780px){{.cards{{grid-template-columns:repeat(2,minmax(0,1fr))}}h1{{font-size:30px}}main{{padding:24px 14px}}}}
@media(max-width:400px){{.cards{{grid-template-columns:1fr}}}}
</style><main><div class="eyebrow">ORDERS DATA LAB / ANALYTICS</div><h1>Заказы, выручка, покупатели</h1>
<p class="muted">{html.escape(period)} · RUB · даты в UTC</p><p>{html.escape(note)}</p>
<div class="cards">{card_html}</div><section><h2>Продажи в цифрах</h2><img alt="Выручка по дням и категориям" src="data:image/png;base64,{chart_data}"></section>
<section><h2>Наблюдения</h2><ul>{"".join("<li>" + html.escape(value) + "</li>" for value in observations)}</ul></section>
<section><h2>Категории</h2><div class="table-wrap">{category_table}</div></section>
<section><h2>Месяцы</h2><div class="table-wrap">{monthly_table}</div><p class="muted">Первый и последний месяцы могут быть неполными. При нулевой базе процент изменения не определён.</p></section>
<section><h2>Как считаем</h2><p>{html.escape(assumptions)}</p><p>Средний чек = выручка / оплаченные заказы. Доля повторных покупателей = покупатели с ≥2 оплаченными заказами / все покупатели с оплатой. При нулевом знаменателе показываем «—».</p></section>
<p class="muted">Снимок: {html.escape(metrics["snapshot_at"])}<br>Запуск ETL: {metrics["etl_run_id"]}</p></main></html>"""
    (output_dir / "index.html").write_text(document, encoding="utf-8")
    return metrics
