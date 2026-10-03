import json
import sqlite3

import pytest
from sqlalchemy.orm import Session

from orders_lab.models import Order
from orders_lab.pipeline.extract import extract_orders
from orders_lab.pipeline.run import run_pipeline
from orders_lab.pipeline.validate import validate_snapshot


def test_repeat_run_and_status_change(engine, sales_data, tmp_path):
    warehouse, raw_dir = tmp_path / "warehouse.db", tmp_path / "raw"
    run_pipeline(engine, warehouse, raw_dir)
    run_pipeline(engine, warehouse, raw_dir)
    with sqlite3.connect(warehouse) as connection:
        assert connection.execute("SELECT COUNT(*) FROM fact_orders").fetchone()[0] == 5
        assert connection.execute("SELECT COUNT(*) FROM fact_order_items").fetchone()[0] == 6
        assert (
            connection.execute("SELECT SUM(revenue_kopecks) FROM mart_daily_sales").fetchone()[0]
            == 5303
        )
    with Session(engine) as session, session.begin():
        session.get(Order, sales_data[0]).status = "cancelled"
    run_pipeline(engine, warehouse, raw_dir)
    with sqlite3.connect(warehouse) as connection:
        assert (
            connection.execute("SELECT SUM(revenue_kopecks) FROM mart_daily_sales").fetchone()[0]
            == 2601
        )
        assert (
            connection.execute("SELECT COUNT(*) FROM etl_runs WHERE status='success'").fetchone()[0]
            == 3
        )
    assert len(list(raw_dir.glob("*.jsonl"))) == 3


def test_bad_snapshot_keeps_previous_warehouse(engine, sales_data, tmp_path, monkeypatch):
    warehouse, raw_dir = tmp_path / "warehouse.db", tmp_path / "raw"
    run_pipeline(engine, warehouse, raw_dir)
    rows = extract_orders(engine)
    rows[0]["total_kopecks"] += 1
    monkeypatch.setattr("orders_lab.pipeline.run.extract_orders", lambda _: rows)
    with pytest.raises(ValueError):
        run_pipeline(engine, warehouse, raw_dir)
    with sqlite3.connect(warehouse) as connection:
        assert (
            connection.execute("SELECT SUM(revenue_kopecks) FROM mart_daily_sales").fetchone()[0]
            == 5303
        )
        assert (
            connection.execute("SELECT COUNT(*) FROM etl_runs WHERE status='failed'").fetchone()[0]
            == 1
        )


@pytest.mark.parametrize(
    "defect", ["duplicate", "negative", "status", "empty", "missing", "duplicate_item"]
)
def test_data_quality_checks(engine, sales_data, defect):
    rows = extract_orders(engine)
    if defect == "duplicate":
        rows.append(rows[0])
    elif defect == "negative":
        rows[0]["items"][0]["quantity"] = -1
    elif defect == "status":
        rows[0]["status"] = "lost"
    elif defect == "empty":
        rows[0]["items"] = []
    elif defect == "missing":
        del rows[0]["customer"]
    elif defect == "duplicate_item":
        rows[0]["items"].append(rows[0]["items"][0])
    with pytest.raises(ValueError):
        validate_snapshot(rows)


def test_raw_snapshot_omits_name_email(engine, sales_data, tmp_path):
    result = run_pipeline(engine, tmp_path / "warehouse.db", tmp_path / "raw")
    with open(result["raw_file"], encoding="utf-8") as stream:
        row = json.loads(stream.readline())
    assert set(row["customer"]) == {"customer_id", "region"}


def test_empty_source_replaces_old_snapshot(engine, sales_data, tmp_path):
    warehouse, raw_dir = tmp_path / "warehouse.db", tmp_path / "raw"
    run_pipeline(engine, warehouse, raw_dir)
    with Session(engine) as session, session.begin():
        for order_id in sales_data:
            session.delete(session.get(Order, order_id))
    run_pipeline(engine, warehouse, raw_dir)
    with sqlite3.connect(warehouse) as connection:
        assert connection.execute("SELECT COUNT(*) FROM fact_orders").fetchone()[0] == 0
