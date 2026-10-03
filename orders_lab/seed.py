import random
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from orders_lab.models import Customer, Order, Product
from orders_lab.schemas import OrderCreate
from orders_lab.services import create_order


def seed_demo(engine: Engine, order_count: int = 600) -> bool:
    """Детерминированные синтетические данные; существующая БД не изменяется."""
    if not 1 <= order_count <= 10_000:
        raise ValueError("Количество заказов должно быть от 1 до 10000")
    rng = random.Random(42)
    with Session(engine) as session, session.begin():
        if any(
            session.scalar(select(func.count()).select_from(cls))
            for cls in (Customer, Product, Order)
        ):
            return False
        regions = ["Москва", "Санкт-Петербург", "Казань", "Екатеринбург", "Новосибирск"]
        customers = [
            Customer(
                name=f"Демо-покупатель {i:03d}",
                email=f"customer-{i:03d}@example.test",
                region=regions[(i - 1) % len(regions)],
            )
            for i in range(1, 101)
        ]
        catalog = [
            ("Клавиатура", "Периферия", 349_900),
            ("Мышь", "Периферия", 149_900),
            ("Веб-камера", "Периферия", 279_900),
            ("Коврик", "Периферия", 59_900),
            ("USB-хаб", "Аксессуары", 119_900),
            ("Кабель USB-C", "Аксессуары", 49_900),
            ("Подставка", "Аксессуары", 189_900),
            ("Блокнот", "Канцелярия", 29_900),
            ("Набор ручек", "Канцелярия", 19_900),
            ("Планер", "Канцелярия", 79_900),
            ("Наушники", "Аудио", 499_900),
            ("Микрофон", "Аудио", 599_900),
        ]
        products = [
            Product(sku=f"DEMO-{i:03d}", name=name, category=category, price_kopecks=price)
            for i, (name, category, price) in enumerate(catalog, start=1)
        ]
        session.add_all(customers + products)
        session.flush()
        start = datetime(2026, 1, 1, tzinfo=UTC)
        for index in range(order_count):
            chosen = rng.sample(products, rng.randint(1, 4))
            customer = rng.choice(customers[:35] if rng.random() < 0.55 else customers)
            created_at = start + timedelta(days=rng.randrange(90), hours=rng.randrange(24))
            order, _ = create_order(
                session,
                OrderCreate(
                    external_id=f"demo-order-{index + 1:04d}",
                    customer_id=customer.id,
                    items=[{"product_id": p.id, "quantity": rng.randint(1, 3)} for p in chosen],
                ),
                created_at=created_at,
            )
            order.status = rng.choices(["paid", "cancelled", "pending"], [0.78, 0.12, 0.10])[0]
            order.updated_at = created_at + timedelta(minutes=30)
    return True
