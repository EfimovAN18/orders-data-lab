from collections.abc import Iterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session, sessionmaker

from orders_lab.config import get_settings
from orders_lab.db import make_engine
from orders_lab.models import Base, Customer, Order, Product
from orders_lab.schemas import (
    CustomerCreate,
    CustomerRead,
    OrderCreate,
    OrderRead,
    OrderStatus,
    OrderStatusUpdate,
    ProductCreate,
    ProductRead,
)
from orders_lab.services import DomainError, change_status, create_order


def get_session(request: Request) -> Iterator[Session]:
    with request.app.state.sessions() as session:
        yield session


DB = Annotated[Session, Depends(get_session)]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]


def create_app(database_url: str | None = None) -> FastAPI:
    engine = make_engine(database_url or get_settings().database_url)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        Base.metadata.create_all(engine)
        yield
        engine.dispose()

    app = FastAPI(
        title="Orders Data Lab",
        version="0.1.0",
        description=(
            "Учебный API заказов. Все суммы в копейках. Локальная демонстрация без авторизации."
        ),
        lifespan=lifespan,
    )
    app.state.sessions = sessionmaker(engine, expire_on_commit=False)

    @app.exception_handler(DomainError)
    async def domain_error(_request: Request, exc: DomainError):
        return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})

    @app.exception_handler(IntegrityError)
    async def integrity_error(_request: Request, _exc: IntegrityError):
        return JSONResponse(status_code=409, content={"detail": "Конфликт уникальности или связи"})

    @app.exception_handler(OperationalError)
    async def operational_error(_request: Request, _exc: OperationalError):
        return JSONResponse(
            status_code=503,
            content={"detail": "База данных временно недоступна; повторите запрос"},
        )

    @app.get("/health", tags=["health"])
    def health(session: DB):
        session.execute(text("SELECT 1"))
        return {"status": "ok"}

    @app.post("/customers", response_model=CustomerRead, status_code=201, tags=["customers"])
    def add_customer(payload: CustomerCreate, session: DB):
        customer = Customer(**payload.model_dump())
        with session.begin():
            session.add(customer)
        return customer

    @app.get("/customers", response_model=list[CustomerRead], tags=["customers"])
    def customers(session: DB, limit: Limit = 20, offset: Offset = 0):
        return list(
            session.scalars(select(Customer).order_by(Customer.id).offset(offset).limit(limit))
        )

    @app.post("/products", response_model=ProductRead, status_code=201, tags=["products"])
    def add_product(payload: ProductCreate, session: DB):
        product = Product(**payload.model_dump())
        with session.begin():
            session.add(product)
        return product

    @app.get("/products", response_model=list[ProductRead], tags=["products"])
    def products(session: DB, limit: Limit = 20, offset: Offset = 0):
        return list(
            session.scalars(select(Product).order_by(Product.id).offset(offset).limit(limit))
        )

    @app.post("/orders", response_model=OrderRead, status_code=201, tags=["orders"])
    def add_order(payload: OrderCreate, response: Response, session: DB):
        with session.begin():
            order, created = create_order(session, payload)
        response.status_code = 201 if created else 200
        return OrderRead.model_validate(order)

    @app.get("/orders", response_model=list[OrderRead], tags=["orders"])
    def orders(
        session: DB,
        limit: Limit = 20,
        offset: Offset = 0,
        status: OrderStatus | None = None,
        customer_id: Annotated[int | None, Query(gt=0)] = None,
    ):
        statement = select(Order).order_by(Order.id).offset(offset).limit(limit)
        if status is not None:
            statement = statement.where(Order.status == status)
        if customer_id is not None:
            statement = statement.where(Order.customer_id == customer_id)
        return [OrderRead.model_validate(order) for order in session.scalars(statement)]

    @app.get("/orders/{order_id}", response_model=OrderRead, tags=["orders"])
    def get_order(order_id: int, session: DB):
        order = session.get(Order, order_id)
        if order is None:
            raise HTTPException(404, "Заказ не найден")
        return OrderRead.model_validate(order)

    @app.patch("/orders/{order_id}/status", response_model=OrderRead, tags=["orders"])
    def update_status(order_id: int, payload: OrderStatusUpdate, session: DB):
        with session.begin():
            order = change_status(session, order_id, payload.status)
        return OrderRead.model_validate(order)

    return app
