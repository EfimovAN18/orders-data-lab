import sqlite3

from orders_lab.analytics.report import build_report, compute_metrics, query
from orders_lab.pipeline.run import run_pipeline
from orders_lab.seed import seed_demo


def test_metrics_use_correct_grain_and_denominators(engine, sales_data, tmp_path):
    warehouse = tmp_path / "warehouse.db"
    run_pipeline(engine, warehouse, tmp_path / "raw")
    with sqlite3.connect(warehouse) as connection:
        connection.row_factory = sqlite3.Row
        metrics = compute_metrics(connection)
        categories = query(connection, "categories.sql")
        monthly = query(connection, "monthly.sql")
    assert metrics["revenue_kopecks"] == 5303
    assert metrics["revenue_rub"] == "53.03"
    assert metrics["paid_orders"] == 3
    assert metrics["average_order_value_rub"] == "17.68"
    assert metrics["repeat_customer_percent"] == "50.00"
    assert metrics["cancellation_percent"] == "20.00"
    assert sum(row["revenue_kopecks"] for row in categories) == 5303
    assert [row["month"] for row in monthly] == ["2026-01-01", "2026-02-01", "2026-03-01"]
    assert monthly[1]["revenue_kopecks"] == 0
    assert monthly[2]["growth_percent"] is None


def test_empty_report_and_zero_denominators(engine, tmp_path):
    warehouse = tmp_path / "warehouse.db"
    run_pipeline(engine, warehouse, tmp_path / "raw")
    metrics = build_report(warehouse, tmp_path / "report")
    assert metrics["total_orders"] == 0
    assert metrics["revenue_kopecks"] == 0
    assert metrics["average_order_value_rub"] is None
    assert metrics["repeat_customer_percent"] is None
    document = (tmp_path / "report" / "index.html").read_text(encoding="utf-8")
    assert "Пустой набор данных" in document
    assert len((tmp_path / "report" / "monthly_sales.csv").read_text().splitlines()) == 1
    assert (tmp_path / "report" / "sales.png").stat().st_size > 1000


def test_report_is_self_contained_and_seed_is_safe(engine, tmp_path):
    assert seed_demo(engine, 25) is True
    assert seed_demo(engine, 100) is False
    warehouse = tmp_path / "warehouse.db"
    run_pipeline(engine, warehouse, tmp_path / "raw")
    metrics = build_report(warehouse, tmp_path / "report")
    document = (tmp_path / "report" / "index.html").read_text(encoding="utf-8")
    assert metrics["total_orders"] == 25
    assert metrics["demo_only"] is True
    assert "data:image/png;base64," in document
    assert "Синтетические" in document
    assert 'src="http' not in document
