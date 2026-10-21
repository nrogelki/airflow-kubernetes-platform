"""PostgreSQL helpers resolved from an Airflow Connection (``conn_id``).

Credentials never appear in DAG code: they live in Admin -> Connections
(encrypted in the metadata DB) and are resolved at task runtime, inside the
isolated environment.
"""

from __future__ import annotations

from urllib.parse import quote_plus

from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.sdk import BaseHook


def run_statement(conn_id: str, sql: str, parameters: dict | None = None) -> bool:
    """Execute a statement that returns no rows (DDL / DELETE / UPDATE).

    Returns ``True`` so it can be used as an XCom gate for downstream tasks.
    A failing statement raises and therefore fails the task.
    """
    PostgresHook(postgres_conn_id=conn_id).run(sql, parameters=parameters)
    return True


def get_sqlalchemy_engine(conn_id: str, database: str | None = None, **engine_kwargs):
    """SQLAlchemy engine built from a Connection, with NoneType shields.

    The Airflow UI may persist empty login/port/schema fields; ``or`` defaults
    avoid building URIs such as ``postgresql://None:None@host:None/None``.
    """
    from sqlalchemy import create_engine

    conn = BaseHook.get_connection(conn_id)
    user = quote_plus(conn.login or "")
    password = quote_plus(conn.password or "")
    port = conn.port or 5432
    dbname = database or conn.schema or "postgres"
    uri = f"postgresql+psycopg://{user}:{password}@{conn.host}:{port}/{dbname}"
    return create_engine(uri, pool_pre_ping=True, **engine_kwargs)


def copy_csv(conn_id: str, table: str, csv_path: str, delimiter: str = ",", header: bool = True) -> int:
    """Bulk-load a CSV with ``COPY ... FROM STDIN`` (orders of magnitude faster than INSERTs).

    Returns the number of data lines in the file (quoted multi-line fields
    count once per line). ``table`` is an identifier you control
    (never user input); columns must match the CSV order.
    """
    hook = PostgresHook(postgres_conn_id=conn_id)
    options = f"FORMAT csv, DELIMITER '{delimiter}', HEADER {'true' if header else 'false'}"
    hook.copy_expert(f"COPY {table} FROM STDIN WITH ({options})", csv_path)
    with open(csv_path, encoding="utf-8") as fh:
        rows = sum(1 for _ in fh) - (1 if header else 0)
    print(f"COPY {rows} rows into {table}")
    return rows
