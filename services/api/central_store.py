"""SQLite persistence for Technology central-API nouns.

CONTEXT.md Technology needs locations, menus, sales, customers, and suppliers
on one API. Those routers used process memory; a restart wiped any writes
(including POST /sales tickets that clear no-sales alerts).

This module stores the five nouns in the same SQLite file as staff users
(`users.DATABASE_PATH` → `data/company_api.db`) via stdlib sqlite3 — the same
pattern as `users.py`, without new lockfile dependencies.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any

import users

_SCHEMA_READY = False


def database_path():
    """Resolve at call time so tests can point users.DATABASE_PATH at a temp file."""
    return users.DATABASE_PATH


def connect() -> sqlite3.Connection:
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def ensure_schema() -> None:
    global _SCHEMA_READY
    with connect() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS locations (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                city TEXT NOT NULL,
                country TEXT NOT NULL,
                currency TEXT NOT NULL,
                region TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS menu_items (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                name_es TEXT NOT NULL,
                category TEXT NOT NULL,
                description TEXT NOT NULL,
                allergens_json TEXT NOT NULL,
                gluten_free INTEGER NOT NULL,
                dairy_free INTEGER NOT NULL,
                price_cop INTEGER NOT NULL,
                price_usd REAL NOT NULL,
                available_in_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sales (
                id TEXT PRIMARY KEY,
                location_id TEXT NOT NULL,
                location_name TEXT NOT NULL,
                country TEXT NOT NULL,
                region TEXT NOT NULL,
                currency TEXT NOT NULL,
                amount REAL NOT NULL,
                amount_cop REAL NOT NULL,
                amount_usd REAL NOT NULL,
                covers INTEGER NOT NULL,
                occurred_at TEXT NOT NULL,
                channel TEXT NOT NULL,
                menu_item_id TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS customers (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                market TEXT NOT NULL,
                preferred_location_id TEXT NOT NULL,
                preferences_json TEXT NOT NULL,
                order_history_json TEXT NOT NULL,
                loyalty_program TEXT NOT NULL,
                loyalty_medium TEXT NOT NULL,
                uses_stamp_card INTEGER NOT NULL,
                brasa_points_balance INTEGER NOT NULL,
                loyalty_tier TEXT NOT NULL,
                digital_loyalty INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS suppliers (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                country TEXT NOT NULL,
                market TEXT NOT NULL,
                categories_json TEXT NOT NULL,
                status TEXT NOT NULL,
                emergency_surcharge_pct INTEGER NOT NULL,
                currency TEXT NOT NULL,
                price_history_json TEXT NOT NULL,
                price_alert INTEGER NOT NULL,
                latest_unit_price REAL NOT NULL,
                latest_currency TEXT NOT NULL
            );
            """
        )
    _SCHEMA_READY = True


def _table_count(connection: sqlite3.Connection, table: str) -> int:
    row = connection.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
    return int(row["count"])


def seed_locations(rows: list[dict[str, Any]]) -> None:
    ensure_schema()
    with connect() as connection:
        if _table_count(connection, "locations") > 0:
            return
        connection.executemany(
            """
            INSERT INTO locations (id, name, city, country, currency, region)
            VALUES (:id, :name, :city, :country, :currency, :region)
            """,
            rows,
        )


def list_locations() -> list[dict[str, Any]]:
    ensure_schema()
    with connect() as connection:
        return [dict(row) for row in connection.execute(
            "SELECT id, name, city, country, currency, region FROM locations ORDER BY id"
        )]


def get_location(location_id: str) -> dict[str, Any] | None:
    ensure_schema()
    with connect() as connection:
        row = connection.execute(
            "SELECT id, name, city, country, currency, region FROM locations WHERE id = ?",
            (location_id,),
        ).fetchone()
    return dict(row) if row is not None else None


def seed_menu_items(rows: list[dict[str, Any]]) -> None:
    ensure_schema()
    with connect() as connection:
        if _table_count(connection, "menu_items") > 0:
            return
        payload = [
            {
                **row,
                "allergens_json": json.dumps(row["allergens"]),
                "available_in_json": json.dumps(row["available_in"]),
                "gluten_free": int(row["gluten_free"]),
                "dairy_free": int(row["dairy_free"]),
            }
            for row in rows
        ]
        connection.executemany(
            """
            INSERT INTO menu_items (
                id, name, name_es, category, description, allergens_json,
                gluten_free, dairy_free, price_cop, price_usd, available_in_json
            ) VALUES (
                :id, :name, :name_es, :category, :description, :allergens_json,
                :gluten_free, :dairy_free, :price_cop, :price_usd, :available_in_json
            )
            """,
            payload,
        )


def _menu_row(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    return {
        "id": data["id"],
        "name": data["name"],
        "name_es": data["name_es"],
        "category": data["category"],
        "description": data["description"],
        "allergens": json.loads(data["allergens_json"]),
        "gluten_free": bool(data["gluten_free"]),
        "dairy_free": bool(data["dairy_free"]),
        "price_cop": data["price_cop"],
        "price_usd": data["price_usd"],
        "available_in": json.loads(data["available_in_json"]),
    }


def list_menu_items() -> list[dict[str, Any]]:
    ensure_schema()
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT id, name, name_es, category, description, allergens_json,
                   gluten_free, dairy_free, price_cop, price_usd, available_in_json
            FROM menu_items
            ORDER BY id
            """
        ).fetchall()
    return [_menu_row(row) for row in rows]


def get_menu_item(item_id: str) -> dict[str, Any] | None:
    ensure_schema()
    with connect() as connection:
        row = connection.execute(
            """
            SELECT id, name, name_es, category, description, allergens_json,
                   gluten_free, dairy_free, price_cop, price_usd, available_in_json
            FROM menu_items
            WHERE id = ?
            """,
            (item_id,),
        ).fetchone()
    return _menu_row(row) if row is not None else None


def seed_sales(rows: list[dict[str, Any]]) -> None:
    ensure_schema()
    with connect() as connection:
        if _table_count(connection, "sales") > 0:
            return
        connection.executemany(
            """
            INSERT INTO sales (
                id, location_id, location_name, country, region, currency,
                amount, amount_cop, amount_usd, covers, occurred_at, channel, menu_item_id
            ) VALUES (
                :id, :location_id, :location_name, :country, :region, :currency,
                :amount, :amount_cop, :amount_usd, :covers, :occurred_at, :channel, :menu_item_id
            )
            """,
            rows,
        )


def list_sales(
    *,
    location_id: str | None = None,
    currency: str | None = None,
) -> list[dict[str, Any]]:
    ensure_schema()
    clauses: list[str] = []
    params: list[Any] = []
    if location_id is not None:
        clauses.append("location_id = ?")
        params.append(location_id)
    if currency is not None:
        clauses.append("currency = ?")
        params.append(currency)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with connect() as connection:
        rows = connection.execute(
            f"""
            SELECT id, location_id, location_name, country, region, currency,
                   amount, amount_cop, amount_usd, covers, occurred_at, channel, menu_item_id
            FROM sales
            {where}
            ORDER BY occurred_at, id
            """,
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def get_sale(sale_id: str) -> dict[str, Any] | None:
    ensure_schema()
    with connect() as connection:
        row = connection.execute(
            """
            SELECT id, location_id, location_name, country, region, currency,
                   amount, amount_cop, amount_usd, covers, occurred_at, channel, menu_item_id
            FROM sales
            WHERE id = ?
            """,
            (sale_id,),
        ).fetchone()
    return dict(row) if row is not None else None


def next_sale_id(location_id: str) -> str:
    ensure_schema()
    prefix = f"sal-{location_id}-"
    with connect() as connection:
        rows = connection.execute(
            "SELECT id FROM sales WHERE id LIKE ?",
            (f"{prefix}%",),
        ).fetchall()
    taken = {row["id"] for row in rows}
    index = 1
    while f"{prefix}{index}" in taken:
        index += 1
    return f"{prefix}{index}"


def insert_sale(row: dict[str, Any]) -> None:
    ensure_schema()
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO sales (
                id, location_id, location_name, country, region, currency,
                amount, amount_cop, amount_usd, covers, occurred_at, channel, menu_item_id
            ) VALUES (
                :id, :location_id, :location_name, :country, :region, :currency,
                :amount, :amount_cop, :amount_usd, :covers, :occurred_at, :channel, :menu_item_id
            )
            """,
            row,
        )


def delete_sale(sale_id: str) -> None:
    ensure_schema()
    with connect() as connection:
        connection.execute("DELETE FROM sales WHERE id = ?", (sale_id,))


def seed_customers(rows: list[dict[str, Any]]) -> None:
    ensure_schema()
    with connect() as connection:
        if _table_count(connection, "customers") > 0:
            return
        payload = [
            {
                **row,
                "preferences_json": json.dumps(row["preferences"]),
                "order_history_json": json.dumps(row["order_history"]),
                "uses_stamp_card": int(row["uses_stamp_card"]),
                "digital_loyalty": int(row["digital_loyalty"]),
            }
            for row in rows
        ]
        connection.executemany(
            """
            INSERT INTO customers (
                id, name, market, preferred_location_id, preferences_json,
                order_history_json, loyalty_program, loyalty_medium, uses_stamp_card,
                brasa_points_balance, loyalty_tier, digital_loyalty
            ) VALUES (
                :id, :name, :market, :preferred_location_id, :preferences_json,
                :order_history_json, :loyalty_program, :loyalty_medium, :uses_stamp_card,
                :brasa_points_balance, :loyalty_tier, :digital_loyalty
            )
            """,
            payload,
        )


def _customer_row(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    history = json.loads(data["order_history_json"])
    return {
        "id": data["id"],
        "name": data["name"],
        "market": data["market"],
        "preferred_location_id": data["preferred_location_id"],
        "preferences": json.loads(data["preferences_json"]),
        "order_history": history,
        "last_order": history[0] if history else None,
        "loyalty_program": data["loyalty_program"],
        "loyalty_medium": data["loyalty_medium"],
        "uses_stamp_card": bool(data["uses_stamp_card"]),
        "brasa_points_balance": data["brasa_points_balance"],
        "loyalty_tier": data["loyalty_tier"],
        "digital_loyalty": bool(data["digital_loyalty"]),
    }


def list_customers() -> list[dict[str, Any]]:
    ensure_schema()
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT id, name, market, preferred_location_id, preferences_json,
                   order_history_json, loyalty_program, loyalty_medium, uses_stamp_card,
                   brasa_points_balance, loyalty_tier, digital_loyalty
            FROM customers
            ORDER BY id
            """
        ).fetchall()
    return [_customer_row(row) for row in rows]


def get_customer(customer_id: str) -> dict[str, Any] | None:
    ensure_schema()
    with connect() as connection:
        row = connection.execute(
            """
            SELECT id, name, market, preferred_location_id, preferences_json,
                   order_history_json, loyalty_program, loyalty_medium, uses_stamp_card,
                   brasa_points_balance, loyalty_tier, digital_loyalty
            FROM customers
            WHERE id = ?
            """,
            (customer_id,),
        ).fetchone()
    return _customer_row(row) if row is not None else None


def seed_suppliers(rows: list[dict[str, Any]]) -> None:
    ensure_schema()
    with connect() as connection:
        if _table_count(connection, "suppliers") > 0:
            return
        payload = [
            {
                **row,
                "categories_json": json.dumps(row["categories"]),
                "price_history_json": json.dumps(row["price_history"]),
                "price_alert": int(row["price_alert"]),
            }
            for row in rows
        ]
        connection.executemany(
            """
            INSERT INTO suppliers (
                id, name, country, market, categories_json, status,
                emergency_surcharge_pct, currency, price_history_json,
                price_alert, latest_unit_price, latest_currency
            ) VALUES (
                :id, :name, :country, :market, :categories_json, :status,
                :emergency_surcharge_pct, :currency, :price_history_json,
                :price_alert, :latest_unit_price, :latest_currency
            )
            """,
            payload,
        )


def _supplier_row(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    return {
        "id": data["id"],
        "name": data["name"],
        "country": data["country"],
        "market": data["market"],
        "categories": json.loads(data["categories_json"]),
        "status": data["status"],
        "emergency_surcharge_pct": data["emergency_surcharge_pct"],
        "currency": data["currency"],
        "price_history": json.loads(data["price_history_json"]),
        "price_alert": bool(data["price_alert"]),
        "latest_unit_price": data["latest_unit_price"],
        "latest_currency": data["latest_currency"],
    }


def list_suppliers() -> list[dict[str, Any]]:
    ensure_schema()
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT id, name, country, market, categories_json, status,
                   emergency_surcharge_pct, currency, price_history_json,
                   price_alert, latest_unit_price, latest_currency
            FROM suppliers
            ORDER BY id
            """
        ).fetchall()
    return [_supplier_row(row) for row in rows]


def get_supplier(supplier_id: str) -> dict[str, Any] | None:
    ensure_schema()
    with connect() as connection:
        row = connection.execute(
            """
            SELECT id, name, country, market, categories_json, status,
                   emergency_surcharge_pct, currency, price_history_json,
                   price_alert, latest_unit_price, latest_currency
            FROM suppliers
            WHERE id = ?
            """,
            (supplier_id,),
        ).fetchone()
    return _supplier_row(row) if row is not None else None
