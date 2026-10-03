import hashlib
import json
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from orders_lab.models import Customer, Order, OrderItem, Product, utc_now
from orders_lab.schemas import OrderCreate, OrderStatus


class DomainError(Exception):
    def __init__(self, message: str, status_code: int = 409):
        super().__init__(message)
        self.status_code = status_code


def create_order(
    session: Session, payload: OrderCreate, *, created_at: datetime | None = None
) -> tuple[Order, bool]:
    """Создаёт заказ без commit: транзакцией управляет вызывающий код."""
    content = {
        "customer_id": payload.customer_id,
        "items": sorted((line.product_id, line.quantity) for line in payload.items),
    }
    fingerprint = hashlib.sha256(json.dumps(content).encode()).hexdigest()
    existing = session.scalar(select(Order).where(Order.external_id == payload.external_id))
    if existing:
        if existing.request_fingerprint != fingerprint:
            raise DomainError("external_id уже использован для другого заказа")
        return existing, False

    if session.get(Customer, payload.customer_id) is None:
        raise DomainError("Покупатель не найден", 404)
    ids = [item.product_id for item in payload.items]
    products = {
        product.id: product
        for product in session.scalars(select(Product).where(Product.id.in_(ids)))
    }
    if len(products) != len(ids):
        raise DomainError("Один или несколько товаров не найдены", 404)
    items = [
        OrderItem(
            product_id=item.product_id,
            quantity=item.quantity,
            unit_price_kopecks=products[item.product_id].price_kopecks,
        )
        for item in payload.items
    ]
    timestamp = created_at or utc_now()
    order = Order(
        external_id=payload.external_id,
        request_fingerprint=fingerprint,
        customer_id=payload.customer_id,
        status="pending",
        total_kopecks=sum(item.quantity * item.unit_price_kopecks for item in items),
        created_at=timestamp,
        updated_at=timestamp,
        items=items,
    )
    session.add(order)
    session.flush()
    return order, True


def change_status(session: Session, order_id: int, status: OrderStatus) -> Order:
    order = session.get(Order, order_id)
    if order is None:
        raise DomainError("Заказ не найден", 404)
    if order.status == status:
        return order
    allowed = {"pending": {"paid", "cancelled"}, "paid": {"cancelled"}, "cancelled": set()}
    if status not in allowed[order.status]:
        raise DomainError(f"Переход {order.status} → {status} запрещён")
    # Compare-and-set: параллельный запрос не должен затереть чужое изменение.
    result = session.execute(
        update(Order)
        .where(Order.id == order_id, Order.status == order.status)
        .values(status=status, updated_at=utc_now())
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        raise DomainError("Заказ уже изменился; перечитайте его и повторите запрос")
    session.expire(order)
    return order
