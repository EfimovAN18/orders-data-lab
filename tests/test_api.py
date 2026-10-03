from copy import deepcopy

import pytest
from sqlalchemy.orm import Session

from orders_lab.models import Product


def test_order_money_idempotency_and_price_snapshot(client, engine, payload, catalog):
    response = client.post("/orders", json=payload)
    assert response.status_code == 201
    original = response.json()
    assert original["total_kopecks"] == 2702
    assert original["created_at"].endswith("Z")
    with Session(engine) as session, session.begin():
        session.get(Product, catalog["a"]).price_kopecks = 50_000
    retry = client.post("/orders", json=payload)
    assert retry.status_code == 200
    assert retry.json() == original
    assert len(client.get("/orders").json()) == 1


def test_idempotency_key_rejects_different_payload(client, payload):
    client.post("/orders", json=payload)
    payload["items"][0]["quantity"] += 1
    assert client.post("/orders", json=payload).status_code == 409


@pytest.mark.parametrize("quantity", [0, -1, 1.5, "2", True, 1001])
def test_invalid_quantity_does_not_create_order(client, payload, quantity):
    payload["items"][0]["quantity"] = quantity
    assert client.post("/orders", json=payload).status_code == 422
    assert client.get("/orders").json() == []


def test_duplicate_items_and_extra_fields_are_rejected(client, payload):
    duplicate = deepcopy(payload)
    duplicate["items"].append(duplicate["items"][0])
    assert client.post("/orders", json=duplicate).status_code == 422
    payload["total_kopecks"] = 1
    assert client.post("/orders", json=payload).status_code == 422


def test_order_with_missing_product_is_atomic(client, payload):
    payload["items"][1]["product_id"] = 999_999
    assert client.post("/orders", json=payload).status_code == 404
    assert client.get("/orders").json() == []


def test_missing_customer(client, payload):
    payload["customer_id"] = 999_999
    assert client.post("/orders", json=payload).status_code == 404


def test_status_transitions_and_filters(client, payload):
    order_id = client.post("/orders", json=payload).json()["id"]
    url = f"/orders/{order_id}/status"
    assert client.patch(url, json={"status": "paid"}).status_code == 200
    assert client.patch(url, json={"status": "paid"}).status_code == 200
    assert client.patch(url, json={"status": "pending"}).status_code == 409
    assert len(client.get("/orders?status=paid").json()) == 1
    assert client.patch(url, json={"status": "cancelled"}).status_code == 200
    assert client.patch(url, json={"status": "paid"}).status_code == 409
    assert client.get("/orders?status=paid").json() == []
    assert client.get("/orders?status=unknown").status_code == 422
    assert client.get("/orders/999999").status_code == 404
    assert client.patch("/orders/999999/status", json={"status": "paid"}).status_code == 404


def test_customer_normalization_and_uniqueness(client):
    data = {"name": "  Иван  ", "email": "USER@EXAMPLE.TEST", "region": "Москва"}
    first = client.post("/customers", json=data)
    assert first.status_code == 201
    assert first.json()["name"] == "Иван"
    assert first.json()["email"] == "user@example.test"
    assert client.post("/customers", json=data).status_code == 409
    assert client.get("/health").json() == {"status": "ok"}


def test_product_validation_and_sku_uniqueness(client):
    data = {"sku": "P", "name": "Товар", "category": "Категория", "price_kopecks": 100}
    assert client.post("/products", json=data).status_code == 201
    assert client.post("/products", json=data).status_code == 409
    data["price_kopecks"] = 1.25
    assert client.post("/products", json=data).status_code == 422


def test_pagination_and_customer_filter(client, sales_data, catalog):
    first = client.get("/orders?limit=2").json()
    second = client.get("/orders?limit=2&offset=2").json()
    assert len(first) == len(second) == 2
    assert not ({row["id"] for row in first} & {row["id"] for row in second})
    assert len(client.get(f"/orders?customer_id={catalog['customer']}").json()) == 2
    assert client.get("/orders?limit=101").status_code == 422
    assert client.get("/orders?offset=-1").status_code == 422
