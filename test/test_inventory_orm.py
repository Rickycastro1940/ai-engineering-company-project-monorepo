from __future__ import annotations

from fastapi.testclient import TestClient

from test.conftest import register_user


def _auth_headers(client: TestClient, email: str = "ops.inventory@brasaland.test") -> dict[str, str]:
    token = register_user(client, email)["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_seeded_inventory_matches_context_minimums_and_net_stock(client: TestClient) -> None:
    from sqlmodel import Session, select

    from services.database import get_engine
    from services.inventory_stock import computed_stock_by_ingredient
    from services.models import Ingredient, IngredientEntry, IngredientExit
    from services.seed_inventory import SEED_NET_STOCK

    headers = _auth_headers(client, "seed.net@brasaland.test")
    products = {item["sku"]: item for item in client.get("/inventory/products", headers=headers).json()}
    assert set(products) >= set(SEED_NET_STOCK)
    for sku, expected in SEED_NET_STOCK.items():
        assert products[sku]["current_stock"] == expected

    with Session(get_engine()) as session:
        ingredients = {item.sku: item for item in session.exec(select(Ingredient)).all() if item.sku}
        entries = list(session.exec(select(IngredientEntry)).all())
        exits = list(session.exec(select(IngredientExit)).all())
        assert len(ingredients) >= 6
        assert len(entries) >= 4
        assert len(exits) >= 3
        assert any(row.reason == "waste" for row in exits)
        beef_id = ingredients["BRS-BEEF-001"].id
        beef_inbound = sorted(row.quantity for row in entries if row.ingredient_id == beef_id)
        beef_outbound = sorted(row.quantity for row in exits if row.ingredient_id == beef_id)
        assert beef_inbound == [30, 50]
        assert beef_outbound == [5, 15]
        suppliers = {row.supplier_name for row in entries}
        assert suppliers >= {"Carnes del Valle S.A.", "MiamiMeat Co.", "Salsas Artesanales Ltda."}
        stock = computed_stock_by_ingredient(session)
        for sku, expected in SEED_NET_STOCK.items():
            ingredient_id = ingredients[sku].id or 0
            inbound = sum(row.quantity for row in entries if row.ingredient_id == ingredient_id)
            outbound = sum(row.quantity for row in exits if row.ingredient_id == ingredient_id)
            assert stock.get(ingredient_id, 0.0) == inbound - outbound == expected


def test_inventory_products_can_filter_by_country(client: TestClient) -> None:
    headers = _auth_headers(client)
    colombia = client.get("/inventory/products", params={"country": "CO"}, headers=headers)
    florida = client.get("/inventory/products", params={"country": "US"}, headers=headers)
    assert colombia.status_code == 200
    assert florida.status_code == 200
    assert {item["sku"] for item in colombia.json()} >= {"BRS-BEEF-001", "BRS-SAUCE-001"}
    assert {item["sku"] for item in florida.json()} == {"BRS-PORK-001", "BRS-SAUCE-002"}
    assert all(item["country"] == "CO" for item in colombia.json())
    assert all(item["country"] == "US" for item in florida.json())


def test_ingredient_entry_fk_is_only_to_ingredient() -> None:
    from services.models import Ingredient, IngredientEntry

    targets = {fk.target_fullname for fk in IngredientEntry.__table__.foreign_keys}
    columns = {column.name for column in IngredientEntry.__table__.columns}
    fk_columns = {fk.parent.name for fk in IngredientEntry.__table__.foreign_keys}
    assert Ingredient.__name__ == "Ingredient"
    assert targets == {"ingredient.id"}
    assert fk_columns == {"ingredient_id"}
    assert "user_uuid" in columns
    assert "location_id" in columns
    assert "location_id" not in fk_columns
    assert not any("user" in fk.target_fullname for fk in IngredientEntry.__table__.foreign_keys)
    assert not any("product" in fk.target_fullname for fk in IngredientEntry.__table__.foreign_keys)


def test_ingredient_exit_fk_is_only_to_ingredient() -> None:
    from services.models import Ingredient, IngredientExit

    targets = {fk.target_fullname for fk in IngredientExit.__table__.foreign_keys}
    columns = {column.name for column in IngredientExit.__table__.columns}
    fk_columns = {fk.parent.name for fk in IngredientExit.__table__.foreign_keys}
    assert targets == {"ingredient.id"}
    assert fk_columns == {"ingredient_id"}
    assert columns.issuperset({"id", "ingredient_id", "quantity", "reason", "location_id", "created_at", "user_uuid"})
    assert "location_id" not in fk_columns
    assert not any("user" in fk.target_fullname for fk in IngredientExit.__table__.foreign_keys)
    assert not any("product" in fk.target_fullname for fk in IngredientExit.__table__.foreign_keys)


def test_inventory_outbound_rejects_negative_stock(client: TestClient) -> None:
    from sqlmodel import Session, col, func, select

    from services.database import get_engine
    from services.models import IngredientExit

    token = register_user(client, "ops@brasaland.test")["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    products = {item["sku"]: item for item in client.get("/inventory/products", headers=headers).json()}
    beef_id = products["BRS-BEEF-001"]["id"]

    with Session(get_engine()) as session:
        exits_before = session.exec(
            select(func.count()).select_from(IngredientExit).where(col(IngredientExit.ingredient_id) == beef_id)
        ).one()

    response = client.post(
        "/inventory/orders/outbound",
        headers=headers,
        json={"ingredient_id": beef_id, "quantity": 61, "reason": "consumption", "location_id": 1},
    )
    assert response.status_code == 400
    assert (
        response.json()["detail"]
        == "Insufficient stock for ingredient 'Beef brisket'. Available: 60, requested: 61."
    )
    assert client.get(f"/inventory/products/{beef_id}", headers=headers).json()["current_stock"] == 60

    with Session(get_engine()) as session:
        exits_after = session.exec(
            select(func.count()).select_from(IngredientExit).where(col(IngredientExit.ingredient_id) == beef_id)
        ).one()
    assert exits_after == exits_before


def test_stock_scope_is_global_per_ingredient_not_per_location(client: TestClient) -> None:
    from sqlmodel import Session, col, func, select

    from services.database import get_engine
    from services.models import IngredientExit

    registered = register_user(client, "felipe.scope@brasaland.test")
    tinydb_uuid = str(registered["user"]["id"])
    headers = {"Authorization": f"Bearer {registered['access_token']}"}
    products = {item["sku"]: item for item in client.get("/inventory/products", headers=headers).json()}
    sauce_id = products["BRS-SAUCE-002"]["id"]
    assert products["BRS-SAUCE-002"]["current_stock"] == 0

    inbound = client.post(
        "/inventory/orders/inbound",
        headers=headers,
        json={
            "ingredient_id": sauce_id,
            "quantity": 10,
            "supplier_name": "MiamiMeat Co.",
            "location_id": 10,
        },
    )
    assert inbound.status_code == 201
    assert inbound.json()["user_uuid"] == tinydb_uuid

    with Session(get_engine()) as session:
        exits_before = session.exec(
            select(func.count()).select_from(IngredientExit).where(col(IngredientExit.ingredient_id) == sauce_id)
        ).one()

    overshoot = client.post(
        "/inventory/orders/outbound",
        headers=headers,
        json={"ingredient_id": sauce_id, "quantity": 10.5, "reason": "consumption", "location_id": 14},
    )
    assert overshoot.status_code == 400
    assert (
        overshoot.json()["detail"]
        == "Insufficient stock for ingredient 'House BBQ sauce'. Available: 10, requested: 10.5."
    )
    assert client.get(f"/inventory/products/{sauce_id}", headers=headers).json()["current_stock"] == 10

    with Session(get_engine()) as session:
        exits_after_reject = session.exec(
            select(func.count()).select_from(IngredientExit).where(col(IngredientExit.ingredient_id) == sauce_id)
        ).one()
    assert exits_after_reject == exits_before

    allowed = client.post(
        "/inventory/orders/outbound",
        headers=headers,
        json={"ingredient_id": sauce_id, "quantity": 10, "reason": "consumption", "location_id": 14},
    )
    assert allowed.status_code == 201
    assert allowed.json()["user_uuid"] == tinydb_uuid
    assert allowed.json()["location_id"] == 14
    assert client.get(f"/inventory/products/{sauce_id}", headers=headers).json()["current_stock"] == 0

    with Session(get_engine()) as session:
        exit_row = session.exec(
            select(IngredientExit).where(col(IngredientExit.ingredient_id) == sauce_id)
        ).one()
        assert exit_row.user_uuid == tinydb_uuid
        assert exit_row.location_id == 14


def test_inventory_inbound_and_outbound_store_user_uuid(client: TestClient) -> None:
    registered = register_user(client, "lucia.fernandez@brasaland.test")
    headers = {"Authorization": f"Bearer {registered['access_token']}"}
    products = {item["sku"]: item for item in client.get("/inventory/products", headers=headers).json()}
    yuca_id = products["BRS-PROD-001"]["id"]

    inbound = client.post(
        "/inventory/orders/inbound",
        headers=headers,
        json={
            "ingredient_id": yuca_id,
            "quantity": 12.5,
            "supplier_name": "Huerta Andina",
            "location_id": 2,
        },
    )
    assert inbound.status_code == 201
    assert inbound.json()["user_uuid"] == str(registered["user"]["id"])
    assert inbound.json()["name"] == "Yuca (cassava)"

    outbound = client.post(
        "/inventory/orders/outbound",
        headers=headers,
        json={"ingredient_id": yuca_id, "quantity": 2, "reason": "waste", "location_id": 2},
    )
    assert outbound.status_code == 201
    assert outbound.json()["reason"] == "waste"
    assert client.get(f"/inventory/products/{yuca_id}", headers=headers).json()["current_stock"] == 10.5

    orders = client.get("/inventory/orders", headers=headers).json()
    assert any(order["type"] == "INBOUND" and order["sku"] == "BRS-PROD-001" for order in orders)
    assert any(order["type"] == "OUTBOUND" and order["reason"] == "waste" for order in orders)


def test_brasaland_context_names_and_seed_values(client: TestClient) -> None:
    from sqlmodel import SQLModel

    from services.models import Ingredient, IngredientEntry, IngredientExit
    from services.schemas import IngredientResponse
    from services.seed_inventory import SEED_INGREDIENTS

    assert Ingredient.__name__ == "Ingredient"
    assert IngredientEntry.__name__ == "IngredientEntry"
    assert IngredientExit.__name__ == "IngredientExit"
    assert {column.name for column in Ingredient.__table__.columns} == {
        "id",
        "name",
        "sku",
        "unit",
        "category",
        "country",
    }
    assert {column.name for column in IngredientEntry.__table__.columns} == {
        "id",
        "ingredient_id",
        "quantity",
        "supplier_name",
        "location_id",
        "created_at",
        "user_uuid",
    }
    assert {column.name for column in IngredientExit.__table__.columns} == {
        "id",
        "ingredient_id",
        "quantity",
        "reason",
        "location_id",
        "created_at",
        "user_uuid",
    }
    table_names = {table.name for table in SQLModel.metadata.tables.values()}
    assert "user" not in table_names
    assert "product" not in table_names
    assert "warehouse" not in table_names

    expected_seed = {
        ("Beef brisket", "BRS-BEEF-001", "kg", "meat", "CO"),
        ("Pork ribs", "BRS-PORK-001", "kg", "meat", "US"),
        ("Chimichurri sauce", "BRS-SAUCE-001", "litre", "sauce", "CO"),
        ("House BBQ sauce", "BRS-SAUCE-002", "litre", "sauce", "US"),
        ("Yuca (cassava)", "BRS-PROD-001", "kg", "produce", "CO"),
        ("Takeaway box (M)", "BRS-PKG-001", "unit", "packaging", "CO"),
    }
    assert {
        (row["name"], row["sku"], row["unit"], row["category"], row["country"]) for row in SEED_INGREDIENTS
    } == expected_seed

    headers = _auth_headers(client, "context.names@brasaland.test")
    products = client.get("/inventory/products", headers=headers).json()
    by_sku = {item["sku"]: item for item in products}
    assert set(by_sku) >= {sku for _, sku, *_ in expected_seed}
    for item in products:
        assert set(item) >= set(IngredientResponse.model_fields)
        assert item["country"] in {"CO", "US"}
        assert "product_id" not in item
        assert "warehouse" not in item
    assert by_sku["BRS-BEEF-001"]["name"] == "Beef brisket"
    assert by_sku["BRS-BEEF-001"]["country"] == "CO"
    assert by_sku["BRS-PORK-001"]["country"] == "US"


def test_inventory_schemas_are_standalone_pydantic_models() -> None:
    from pydantic import BaseModel
    from sqlmodel import SQLModel

    from services.models import Ingredient, IngredientEntry, IngredientExit
    from services.schemas import (
        IngredientCreate,
        IngredientEntryCreate,
        IngredientEntryResponse,
        IngredientExitCreate,
        IngredientExitResponse,
        IngredientResponse,
    )

    request_and_response = (
        IngredientCreate,
        IngredientResponse,
        IngredientEntryCreate,
        IngredientEntryResponse,
        IngredientExitCreate,
        IngredientExitResponse,
    )
    for schema in request_and_response:
        assert issubclass(schema, BaseModel)
        assert not issubclass(schema, SQLModel)

    assert set(IngredientCreate.model_fields) == {"name", "sku", "unit", "category", "country"}
    assert "current_stock" in IngredientResponse.model_fields
    assert "current_stock" not in Ingredient.model_fields
    assert "current_stock" not in Ingredient.__table__.columns
    assert set(IngredientEntryCreate.model_fields) == {
        "ingredient_id",
        "quantity",
        "supplier_name",
        "location_id",
    }
    assert set(IngredientExitCreate.model_fields) == {"ingredient_id", "quantity", "reason", "location_id"}
    assert Ingredient is not IngredientResponse
    assert IngredientEntry is not IngredientEntryResponse
    assert IngredientExit is not IngredientExitResponse


def test_inventory_architecture_session_env_and_seeded_net_stock(client: TestClient) -> None:
    import inspect
    from pathlib import Path
    from typing import get_type_hints

    from fastapi.params import Depends
    from pydantic import BaseModel
    from sqlmodel import SQLModel, Session

    from services.database import get_db
    from services.models import Ingredient, IngredientEntry, IngredientExit
    from services.routers import inventory as inventory_routes
    from services.seed_inventory import SEED_NET_STOCK
    import services.database as dual_db

    repo = Path(__file__).resolve().parents[1]
    assert (repo / "services" / "models.py").is_file()
    assert (repo / "services" / "schemas.py").is_file()
    gitignore = (repo / ".gitignore").read_text(encoding="utf-8")
    assert any(line.strip() == ".env" for line in gitignore.splitlines())
    assert not isinstance(getattr(dual_db, "session", None), Session)
    assert inspect.isgeneratorfunction(get_db)

    handlers = (
        inventory_routes.list_ingredients,
        inventory_routes.create_ingredient,
        inventory_routes.get_ingredient,
        inventory_routes.create_ingredient_entry,
        inventory_routes.create_ingredient_exit,
        inventory_routes.list_orders,
    )
    for handler in handlers:
        session_param = inspect.signature(handler).parameters["session"]
        assert isinstance(session_param.default, Depends)
        assert session_param.default.dependency is get_db
        return_type = get_type_hints(handler)["return"]
        origin = getattr(return_type, "__origin__", None)
        inner = return_type.__args__[0] if origin is list else return_type
        assert inner not in {Ingredient, IngredientEntry, IngredientExit}
        assert issubclass(inner, BaseModel)
        assert not issubclass(inner, SQLModel)

    headers = _auth_headers(client, "eval.netstock@brasaland.test")
    products = {item["sku"]: item for item in client.get("/inventory/products", headers=headers).json()}
    for sku, expected in SEED_NET_STOCK.items():
        assert products[sku]["current_stock"] == expected


def test_inventory_router_is_registered_on_fastapi_app() -> None:
    from fastapi import APIRouter

    from api.app import app
    from services.routers.inventory import router as inventory_router

    assert isinstance(inventory_router, APIRouter)
    assert inventory_router.prefix == "/inventory"
    declared = {getattr(route, "path", "") for route in inventory_router.routes}
    assert declared >= {
        "/inventory/products",
        "/inventory/products/{id}",
        "/inventory/orders/inbound",
        "/inventory/orders/outbound",
        "/inventory/orders",
    }
    endpoints = {getattr(route, "endpoint", None) for route in app.routes}
    assert inventory_router.routes
    for route in inventory_router.routes:
        endpoint = getattr(route, "endpoint", None)
        if endpoint is not None:
            assert endpoint in endpoints

    paths = {getattr(route, "path", "") for route in app.routes}
    assert "/inventory/products" in paths
    assert "/inventory/products/{id}" in paths
    assert "/inventory/orders/inbound" in paths
    assert "/inventory/orders/outbound" in paths
    assert "/inventory/orders" in paths
    methods = {
        (getattr(route, "path", ""), method)
        for route in app.routes
        for method in getattr(route, "methods", set())
    }
    assert ("/inventory/products", "GET") in methods
    assert ("/inventory/products", "POST") in methods
    assert ("/inventory/products/{id}", "GET") in methods
    assert ("/inventory/orders/inbound", "POST") in methods
    assert ("/inventory/orders/outbound", "POST") in methods
    assert ("/inventory/orders", "GET") in methods
    from inventory import router as csv_router

    assert csv_router.prefix == "/agent/inventory"
    assert ("/inventory/{product_id}", "PATCH") not in methods
    assert ("/agent/inventory/{product_id}", "PATCH") in methods


def test_current_stock_cannot_be_set_on_create(client: TestClient) -> None:
    headers = _auth_headers(client, "stock.set@brasaland.test")
    response = client.post(
        "/inventory/products",
        headers=headers,
        json={
            "name": "Lime",
            "sku": "BRS-PROD-010",
            "unit": "kg",
            "category": "produce",
            "country": "CO",
            "current_stock": 999,
        },
    )
    assert response.status_code == 422


def test_current_stock_equals_inbound_minus_outbound(client: TestClient) -> None:
    from sqlmodel import Session, col, func, select

    from services.database import get_engine
    from services.models import IngredientEntry, IngredientExit

    headers = _auth_headers(client, "stock.math@brasaland.test")
    products = {item["sku"]: item for item in client.get("/inventory/products", headers=headers).json()}
    beef_id = products["BRS-BEEF-001"]["id"]
    with Session(get_engine()) as session:
        inbound = float(
            session.exec(
                select(func.coalesce(func.sum(IngredientEntry.quantity), 0)).where(
                    col(IngredientEntry.ingredient_id) == beef_id
                )
            ).one()
        )
        outbound = float(
            session.exec(
                select(func.coalesce(func.sum(IngredientExit.quantity), 0)).where(
                    col(IngredientExit.ingredient_id) == beef_id
                )
            ).one()
        )
    assert products["BRS-BEEF-001"]["current_stock"] == inbound - outbound == 60


def test_new_ingredient_starts_at_zero_and_gains_stock_only_via_inbound(client: TestClient) -> None:
    registered = register_user(client, "felipe.inbound@brasaland.test")
    headers = {"Authorization": f"Bearer {registered['access_token']}"}
    tinydb_uuid = str(registered["user"]["id"])
    created = client.post(
        "/inventory/products",
        headers=headers,
        json={
            "name": "Lime",
            "sku": "BRS-PROD-009",
            "unit": "kg",
            "category": "produce",
            "country": "CO",
        },
    )
    assert created.status_code == 201
    ingredient_id = created.json()["id"]
    assert created.json()["current_stock"] == 0
    assert client.get(f"/inventory/products/{ingredient_id}", headers=headers).json()["current_stock"] == 0

    outbound_empty = client.post(
        "/inventory/orders/outbound",
        headers=headers,
        json={"ingredient_id": ingredient_id, "quantity": 1, "reason": "consumption", "location_id": 1},
    )
    assert outbound_empty.status_code == 400
    assert client.get(f"/inventory/products/{ingredient_id}", headers=headers).json()["current_stock"] == 0

    inbound = client.post(
        "/inventory/orders/inbound",
        headers=headers,
        json={
            "ingredient_id": ingredient_id,
            "quantity": 4,
            "supplier_name": "Huerta Andina",
            "location_id": 3,
        },
    )
    assert inbound.status_code == 201
    assert inbound.json()["user_uuid"] == tinydb_uuid
    assert client.get(f"/inventory/products/{ingredient_id}", headers=headers).json()["current_stock"] == 4

    outbound = client.post(
        "/inventory/orders/outbound",
        headers=headers,
        json={"ingredient_id": ingredient_id, "quantity": 1.5, "reason": "waste", "location_id": 3},
    )
    assert outbound.status_code == 201
    assert outbound.json()["user_uuid"] == tinydb_uuid
    assert client.get(f"/inventory/products/{ingredient_id}", headers=headers).json()["current_stock"] == 2.5

    from sqlmodel import Session, select

    from services.database import get_engine
    from services.models import IngredientEntry, IngredientExit

    with Session(get_engine()) as session:
        entry = session.exec(select(IngredientEntry).where(IngredientEntry.ingredient_id == ingredient_id)).one()
        exit_row = session.exec(select(IngredientExit).where(IngredientExit.ingredient_id == ingredient_id)).one()
        assert entry.user_uuid == tinydb_uuid
        assert exit_row.user_uuid == tinydb_uuid


def test_order_create_rejects_client_supplied_user_uuid(client: TestClient) -> None:
    headers = _auth_headers(client, "forged.uuid@brasaland.test")
    products = {item["sku"]: item for item in client.get("/inventory/products", headers=headers).json()}
    yuca_id = products["BRS-PROD-001"]["id"]
    inbound = client.post(
        "/inventory/orders/inbound",
        headers=headers,
        json={
            "ingredient_id": yuca_id,
            "quantity": 1,
            "supplier_name": "Huerta Andina",
            "location_id": 1,
            "user_uuid": "forged-tinydb-id",
        },
    )
    outbound = client.post(
        "/inventory/orders/outbound",
        headers=headers,
        json={
            "ingredient_id": yuca_id,
            "quantity": 1,
            "reason": "consumption",
            "location_id": 1,
            "user_uuid": "forged-tinydb-id",
        },
    )
    assert inbound.status_code == 422
    assert outbound.status_code == 422


def test_inventory_create_and_get_product(client: TestClient) -> None:
    token = register_user(client, "felipe.guerrero@brasaland.test")["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    created = client.post(
        "/inventory/products",
        headers=headers,
        json={
            "name": "Lime",
            "sku": "BRS-PROD-009",
            "unit": "kg",
            "category": "produce",
            "country": "CO",
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["sku"] == "BRS-PROD-009"
    assert body["current_stock"] == 0
    fetched = client.get(f"/inventory/products/{body['id']}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "Lime"
    assert fetched.json()["current_stock"] == 0


def test_inventory_writes_require_auth(client: TestClient) -> None:
    create_product = client.post(
        "/inventory/products",
        json={"name": "Lime", "sku": "BRS-PROD-009", "unit": "kg", "category": "produce", "country": "CO"},
    )
    inbound = client.post(
        "/inventory/orders/inbound",
        json={
            "ingredient_id": 1,
            "quantity": 1,
            "supplier_name": "Carnes del Valle S.A.",
            "location_id": 1,
        },
    )
    outbound = client.post(
        "/inventory/orders/outbound",
        json={"ingredient_id": 1, "quantity": 1, "reason": "consumption", "location_id": 1},
    )
    assert create_product.status_code == 401
    assert inbound.status_code == 401
    assert outbound.status_code == 401
    assert client.get("/inventory/products").status_code == 401
    assert client.get("/inventory/products/1").status_code == 401
    assert client.get("/inventory/orders").status_code == 401


def test_dual_database_tinydb_auth_and_sqlmodel_inventory(client: TestClient) -> None:
    from pathlib import Path

    from tinydb import Query, TinyDB
    from sqlmodel import SQLModel, Session, select

    from services.database import AUTH_DB_PATH, DATABASE_URL, get_auth_db, get_engine
    from services.models import Ingredient, IngredientEntry, IngredientExit
    import users

    auth_db = get_auth_db()
    engine = get_engine()
    assert isinstance(auth_db, TinyDB)
    assert engine is not None
    assert Path(users.DATABASE_PATH) == Path(AUTH_DB_PATH)
    assert not str(DATABASE_URL).lower().endswith(".json")
    table_names = {table.name.lower() for table in SQLModel.metadata.tables.values()}
    assert table_names >= {"ingredient", "ingrediententry", "ingredientexit"}
    assert "user" not in table_names
    assert not any(name.startswith("user") for name in table_names)

    registered = register_user(client, "nicolas.park@brasaland.test")
    tinydb_user = users._users_table().get(Query().email == "nicolas.park@brasaland.test")
    assert tinydb_user is not None
    assert str(registered["user"]["id"]) == str(tinydb_user.doc_id)

    headers = {"Authorization": f"Bearer {registered['access_token']}"}
    created = client.post(
        "/inventory/products",
        headers=headers,
        json={
            "name": "Lime",
            "sku": "BRS-PROD-011",
            "unit": "kg",
            "category": "produce",
            "country": "CO",
        },
    )
    assert created.status_code == 201
    with Session(engine) as session:
        lime = session.exec(select(Ingredient).where(Ingredient.sku == "BRS-PROD-011")).one()
        assert lime.name == "Lime"
        assert session.exec(select(IngredientEntry)).all() is not None
        assert session.exec(select(IngredientExit)).all() is not None
    assert users._users_table().get(Query().email == "nicolas.park@brasaland.test") is not None
    assert not any(key == "sku" for key in dict(tinydb_user))

