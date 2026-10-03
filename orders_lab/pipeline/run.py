import json
import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy.engine import Engine

from orders_lab.pipeline.extract import extract_orders
from orders_lab.pipeline.validate import SnapshotOrder, validate_snapshot

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS etl_runs (
    run_id TEXT PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT,
    status TEXT NOT NULL, extracted_orders INTEGER, loaded_orders INTEGER,
    raw_file TEXT, error TEXT
);
CREATE TABLE IF NOT EXISTS dim_customers (
    customer_id INTEGER PRIMARY KEY, region TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS dim_products (
    product_id INTEGER PRIMARY KEY, sku TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL, category TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS fact_orders (
    order_id INTEGER PRIMARY KEY, external_id TEXT UNIQUE NOT NULL,
    customer_id INTEGER NOT NULL REFERENCES dim_customers(customer_id),
    status TEXT NOT NULL CHECK (status IN ('pending','paid','cancelled')),
    total_kopecks INTEGER NOT NULL CHECK (total_kopecks > 0),
    order_date TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS fact_order_items (
    order_id INTEGER NOT NULL REFERENCES fact_orders(order_id),
    product_id INTEGER NOT NULL REFERENCES dim_products(product_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_kopecks INTEGER NOT NULL CHECK (unit_price_kopecks > 0),
    line_total_kopecks INTEGER NOT NULL,
    PRIMARY KEY (order_id, product_id)
);
CREATE INDEX IF NOT EXISTS ix_fact_date ON fact_orders(order_date);
CREATE INDEX IF NOT EXISTS ix_fact_customer ON fact_orders(customer_id);
CREATE VIEW IF NOT EXISTS mart_daily_sales AS
SELECT order_date, COUNT(*) AS total_orders,
       SUM(CASE WHEN status = 'paid' THEN 1 ELSE 0 END) AS paid_orders,
       SUM(CASE WHEN status = 'paid' THEN total_kopecks ELSE 0 END) AS revenue_kopecks,
       SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END) AS cancelled_orders
FROM fact_orders GROUP BY order_date;
"""


def timestamp() -> str:
    return datetime.now(UTC).isoformat()


def load_snapshot(connection: sqlite3.Connection, orders: list[SnapshotOrder]) -> None:
    customers = {order.customer.customer_id: order.customer.region for order in orders}
    products = {
        item.product_id: (item.sku, item.name, item.category)
        for order in orders
        for item in order.items
    }
    for table in ("fact_order_items", "fact_orders", "dim_customers", "dim_products"):
        connection.execute(f"DELETE FROM {table}")  # Имена заданы кодом, не вводом пользователя.
    connection.executemany("INSERT INTO dim_customers VALUES (?, ?)", customers.items())
    connection.executemany(
        "INSERT INTO dim_products VALUES (?, ?, ?, ?)",
        [(product_id, *attributes) for product_id, attributes in products.items()],
    )
    connection.executemany(
        "INSERT INTO fact_orders VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                order.order_id,
                order.external_id,
                order.customer.customer_id,
                order.status,
                order.total_kopecks,
                order.created_at.astimezone(UTC).date().isoformat(),
                order.created_at.astimezone(UTC).isoformat(),
                order.updated_at.astimezone(UTC).isoformat(),
            )
            for order in orders
        ],
    )
    connection.executemany(
        "INSERT INTO fact_order_items VALUES (?, ?, ?, ?, ?)",
        [
            (
                order.order_id,
                item.product_id,
                item.quantity,
                item.unit_price_kopecks,
                item.quantity * item.unit_price_kopecks,
            )
            for order in orders
            for item in order.items
        ],
    )


def run_pipeline(engine: Engine, warehouse: Path, raw_dir: Path) -> dict:
    warehouse = Path(warehouse)
    raw_dir = Path(raw_dir)
    warehouse.parent.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)
    run_id = uuid4().hex
    raw_path = raw_dir / f"orders_{run_id}.jsonl"
    connection = sqlite3.connect(warehouse, timeout=30)
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.executescript(SCHEMA)
        connection.execute(
            "INSERT INTO etl_runs(run_id, started_at, status) VALUES (?, ?, 'running')",
            (run_id, timestamp()),
        )
        connection.commit()
        try:
            # Один писатель на всё извлечение и загрузку: старый снимок не затрёт новый.
            connection.execute("BEGIN IMMEDIATE")
            rows = extract_orders(engine)
            with raw_path.open("w", encoding="utf-8") as stream:
                for row in rows:
                    stream.write(json.dumps(row, ensure_ascii=False) + "\n")
            orders = validate_snapshot(rows)
            load_snapshot(connection, orders)
            loaded = connection.execute("SELECT COUNT(*) FROM fact_orders").fetchone()[0]
            if loaded != len(rows):
                raise ValueError("Число извлечённых и загруженных заказов различается")
            connection.execute(
                """UPDATE etl_runs SET status='success', finished_at=?, extracted_orders=?,
                   loaded_orders=?, raw_file=? WHERE run_id=?""",
                (timestamp(), len(rows), loaded, str(raw_path), run_id),
            )
            connection.commit()
        except Exception as exc:
            connection.rollback()
            # Не записываем текст исключений БД: там могут оказаться реквизиты подключения.
            connection.execute(
                "UPDATE etl_runs SET status='failed', finished_at=?, error=?, raw_file=? "
                "WHERE run_id=?",
                (timestamp(), type(exc).__name__, str(raw_path), run_id),
            )
            connection.commit()
            raise
        result = {
            "run_id": run_id,
            "status": "success",
            "orders": loaded,
            "raw_file": str(raw_path),
        }
        logger.info("ETL завершён: %d заказов, run_id=%s", loaded, run_id)
        return result
    finally:
        connection.close()
