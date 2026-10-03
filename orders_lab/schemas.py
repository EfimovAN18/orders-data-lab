from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator

OrderStatus = Literal["pending", "paid", "cancelled"]


class InputModel(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class CustomerCreate(InputModel):
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    region: str = Field(min_length=1, max_length=100)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.lower()


class CustomerRead(CustomerCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int


class ProductCreate(InputModel):
    sku: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=150)
    category: str = Field(min_length=1, max_length=100)
    price_kopecks: StrictInt = Field(gt=0, le=1_000_000_000)


class ProductRead(ProductCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int


class OrderLineCreate(InputModel):
    product_id: StrictInt = Field(gt=0)
    quantity: StrictInt = Field(gt=0, le=1_000)


class OrderCreate(InputModel):
    external_id: str = Field(min_length=1, max_length=64)
    customer_id: StrictInt = Field(gt=0)
    items: list[OrderLineCreate] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_products(self):
        ids = [item.product_id for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("Объедините одинаковые товары в одну позицию")
        return self


class OrderStatusUpdate(InputModel):
    status: OrderStatus


class OrderLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    product_id: int
    quantity: int
    unit_price_kopecks: int


class OrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    external_id: str
    customer_id: int
    status: OrderStatus
    total_kopecks: int
    created_at: datetime
    updated_at: datetime
    items: list[OrderLineRead]

    @field_validator("created_at", "updated_at")
    @classmethod
    def as_utc(cls, value: datetime) -> datetime:
        # SQLite возвращает naive datetime; значения в БД всегда записаны в UTC.
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
