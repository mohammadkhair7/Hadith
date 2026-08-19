"""Postgres connection pool (psycopg3)."""
from contextlib import contextmanager

from psycopg_pool import ConnectionPool
from psycopg.rows import dict_row

from .config import settings

pool = ConnectionPool(
    settings.database_url,
    min_size=1,
    max_size=10,
    kwargs={"row_factory": dict_row},
    open=False,
)


def open_pool() -> None:
    pool.open()


def close_pool() -> None:
    pool.close()


@contextmanager
def db():
    with pool.connection() as conn:
        yield conn


def q(conn, sql: str, params=None):
    return conn.execute(sql, params or ()).fetchall()


def q1(conn, sql: str, params=None):
    return conn.execute(sql, params or ()).fetchone()
