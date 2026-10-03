import os
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from orders_lab.api import create_app
from orders_lab.db import make_engine
from orders_lab.models import Base, Customer, Product
from orders_lab.schemas import OrderCreate
from orders_lab.services import create_order


@pytest.fixture
def engine(tmp_path):
    url = os.getenv("TEST_DATABASE_URL", f"sqlite:///{tmp_path / 'app.db'}")
    if make_url(url).get_backend_name() != "sqlite":
        # Тесты пересоздают таблицы только в выделенной тестовой базе.
        if make_url(url).database != "orders_lab_test":
            raise RuntimeError("TEST_DATABASE_URL должен указывать на orders_lab_test")
    db = make_engine(url)
    Base.metadata.drop_all(db)
    Base.metadata.create_all(db)
    yield db
    Base.metadata.drop_all(db)
    db.dispose()


@pytest.fixture
def client(engine):
    with TestClient(create_app(engine.url.render_as_string(hide_password=False))) as test_client:
        yield test_client


@pytest.fixture
def catalog(engine):
    with Session(engine) as session, session.begin():
        first = Customer(name="Покупатель 1", email="one@example.test", region="Москва")
        second = Customer(name="Покупатель 2", email="two@example.test", region="Казань")
        product_a = Product(sku="A", name="Товар A", category="Техника", price_kopecks=101)
        product_b = Product(sku="B", name="Товар B", category="Канцелярия", price_kopecks=2500)
        session.add_all([first, second, product_a, product_b])
        session.flush()
        return {
            "customer": first.id,
            "other_customer": second.id,
            "a": product_a.id,
            "b": product_b.id,
        }


@pytest.fixture
def payload(catalog):
    return {
        "external_id": "test-order-1",
        "customer_id": catalog["customer"],
        "items": [
            {"product_id": catalog["a"], "quantity": 2},
            {"product_id": catalog["b"], "quantity": 1},
        ],
    }


@pytest.fixture
def sales_data(engine, catalog):
    specifications = [
        (catalog["customer"], [(catalog["a"], 2), (catalog["b"], 1)], "paid", 1, 1),
        (catalog["customer"], [(catalog["a"], 1)], "paid", 1, 3),
        (catalog["other_customer"], [(catalog["b"], 1)], "paid", 3, 1),
        (catalog["other_customer"], [(catalog["a"], 1)], "cancelled", 3, 2),
        (catalog["other_customer"], [(catalog["a"], 1)], "pending", 3, 3),
    ]
    ids = []
    with Session(engine) as session, session.begin():
        for index, (customer, items, status, month, day) in enumerate(specifications):
            order, _ = create_order(
                session,
                OrderCreate(
                    external_id=f"fixture-{index}",
                    customer_id=customer,
                    items=[{"product_id": p, "quantity": q} for p, q in items],
                ),
                created_at=datetime(2026, month, day, tzinfo=UTC),
            )
            order.status = status
            ids.append(order.id)
    return ids
