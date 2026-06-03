from __future__ import annotations

from pathlib import Path

import duckdb

SQL_DIR = Path(__file__).parent / "sql"


def connect(db_path: Path | str = "data/sf-public-record.duckdb") -> duckdb.DuckDBPyConnection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(path))


def init_db(db_path: Path | str = "data/sf-public-record.duckdb") -> None:
    with connect(db_path) as conn:
        for migration in ("001_init.sql", "002_indexes.sql"):
            conn.execute((SQL_DIR / migration).read_text())
