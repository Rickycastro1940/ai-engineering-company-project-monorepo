#!/usr/bin/env python3
"""Replay edutrack.sql + queries.sql in DuckDB (PostgreSQL-compatible subset)."""

from __future__ import annotations

import re
from pathlib import Path

import duckdb

HERE = Path(__file__).resolve().parent


def load_seed(con: duckdb.DuckDBPyConnection) -> None:
    sql = (HERE / "edutrack.sql").read_text()
    sql = sql.replace("SERIAL PRIMARY KEY", "INTEGER PRIMARY KEY")
    statements = [s.strip() for s in sql.split(";") if s.strip() and not _comment_only(s)]
    for stmt in statements:
        con.execute(stmt)


def _comment_only(chunk: str) -> bool:
    lines = [ln.strip() for ln in chunk.splitlines()]
    return all(not ln or ln.startswith("--") for ln in lines)


def print_result(result: duckdb.DuckDBPyConnection) -> None:
    desc = result.description
    rows = result.fetchall()
    if not desc:
        print("(no result set)")
        return
    headers = [col[0] for col in desc]
    print(" | ".join(headers))
    print("-" * max(20, len(" | ".join(headers))))
    for row in rows:
        print(" | ".join("NULL" if v is None else str(v) for v in row))
    print(f"({len(rows)} rows)")


def split_statements(sql: str) -> list[str]:
    cleaned = re.sub(r"--[^\n]*", "", sql)
    return [s.strip() for s in cleaned.split(";") if s.strip()]


def main() -> None:
    con = duckdb.connect(":memory:")
    load_seed(con)
    print("=== VERIFY SELECT * FROM enrollments LIMIT 5 ===")
    print_result(con.execute("SELECT * FROM enrollments LIMIT 5"))
    print()

    statements = split_statements((HERE / "queries.sql").read_text())
    n = 0
    for stmt in statements:
        n += 1
        print(f"=== STMT {n} ===")
        print(stmt)
        try:
            result = con.execute(stmt)
            print_result(result)
        except Exception as exc:  # noqa: BLE001 — surface engine errors for the audit log
            print(f"ERROR: {exc}")
        print()

    print("=== POST-AUDIT COUNTS ===")
    print_result(
        con.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM enrollments) AS enrollments,
                (SELECT COUNT(*) FROM students) AS students,
                (SELECT COUNT(*) FROM courses) AS courses,
                (SELECT COUNT(*) FROM enrollments WHERE instructor IS NULL) AS null_instructors,
                (SELECT COUNT(*) FROM enrollments WHERE student_email LIKE '%@test.com') AS test_emails
            """
        )
    )


if __name__ == "__main__":
    main()
