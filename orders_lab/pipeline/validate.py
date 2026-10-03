from datetime import UTC, datetime

from pydantic import AwareDatetime, Field, StrictInt, model_validator

from orders_lab.schemas import InputModel, OrderStatus


class SnapshotCustomer(InputModel):
    customer_id: StrictInt = Field(gt=0)
    region: str = Field(min_length=1, max_length=100)


class SnapshotItem(InputModel):
    product_id: StrictInt = Field(gt=0)
    sku: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=150)
    category: str = Field(min_length=1, max_length=100)
    quantity: StrictInt = Field(gt=0, le=1_000)
    unit_price_kopecks: StrictInt = Field(gt=0, le=1_000_000_000)


class SnapshotOrder(InputModel):
    order_id: StrictInt = Field(gt=0)
    external_id: str = Field(min_length=1, max_length=64)
    customer: SnapshotCustomer
    status: OrderStatus
    total_kopecks: StrictInt = Field(gt=0)
    created_at: AwareDatetime
    updated_at: AwareDatetime
    items: list[SnapshotItem] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def check_order(self):
        ids = [item.product_id for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("Дубли товара внутри заказа")
        calculated = sum(item.quantity * item.unit_price_kopecks for item in self.items)
        if calculated != self.total_kopecks:
            raise ValueError("Сумма заказа не совпадает с суммой позиций")
        if self.updated_at < self.created_at:
            raise ValueError("Заказ изменён раньше даты создания")
        if self.created_at > datetime.now(UTC):
            raise ValueError("Дата создания заказа находится в будущем")
        return self


def validate_snapshot(rows: list[dict]) -> list[SnapshotOrder]:
    orders = [SnapshotOrder.model_validate(row) for row in rows]
    for field in ("order_id", "external_id"):
        values = [getattr(order, field) for order in orders]
        if len(values) != len(set(values)):
            raise ValueError(f"Найден дублирующийся {field}")
    customers: dict[int, str] = {}
    products: dict[int, tuple] = {}
    for order in orders:
        customer = order.customer
        if customer.customer_id in customers and customers[customer.customer_id] != customer.region:
            raise ValueError("Противоречивые данные покупателя в снимке")
        customers[customer.customer_id] = customer.region
        for item in order.items:
            value = (item.sku, item.name, item.category)
            if item.product_id in products and products[item.product_id] != value:
                raise ValueError("Противоречивые данные товара в снимке")
            products[item.product_id] = value
    skus = [value[0] for value in products.values()]
    if len(skus) != len(set(skus)):
        raise ValueError("Один SKU назначен разным товарам")
    return orders
