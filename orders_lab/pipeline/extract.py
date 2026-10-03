from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, joinedload, selectinload

from orders_lab.models import Order, OrderItem


def iso_utc(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


def extract_orders(engine: Engine) -> list[dict]:
    """Полный согласованный снимок; рассчитан на небольшой учебный набор."""
    with engine.connect() as connection:
        if engine.dialect.name == "postgresql":
            connection = connection.execution_options(isolation_level="REPEATABLE READ")
        with connection.begin(), Session(bind=connection) as session:
            orders = session.scalars(
                select(Order)
                .options(
                    joinedload(Order.customer),
                    selectinload(Order.items).joinedload(OrderItem.product),
                )
                .order_by(Order.id)
            )
            return [
                {
                    "order_id": order.id,
                    "external_id": order.external_id,
                    "customer": {"customer_id": order.customer_id, "region": order.customer.region},
                    "status": order.status,
                    "total_kopecks": order.total_kopecks,
                    "created_at": iso_utc(order.created_at),
                    "updated_at": iso_utc(order.updated_at),
                    "items": [
                        {
                            "product_id": item.product_id,
                            "sku": item.product.sku,
                            "name": item.product.name,
                            "category": item.product.category,
                            "quantity": item.quantity,
                            "unit_price_kopecks": item.unit_price_kopecks,
                        }
                        for item in sorted(order.items, key=lambda line: line.product_id)
                    ],
                }
                for order in orders
            ]
