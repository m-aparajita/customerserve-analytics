import os
import threading
import duckdb
from pathlib import Path

_DB_PATH = os.getenv("DB_PATH", str(Path(__file__).parent.parent / "Data" / "customerserve.duckdb"))

_conn: duckdb.DuckDBPyConnection | None = None
_lock = threading.Lock()


def get_connection() -> tuple[duckdb.DuckDBPyConnection, threading.Lock]:
    global _conn
    if _conn is None:
        _conn = duckdb.connect(_DB_PATH)
    return _conn, _lock


def get_db_path() -> str:
    return _DB_PATH
