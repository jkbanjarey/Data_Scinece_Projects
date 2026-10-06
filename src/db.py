"""DuckDB connection and raw-CSV ingestion for the Olist dataset.

Everything downstream (staging, fact, seller stats) is written in SQL
under sql/ and executed against this database.
"""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb

# Repository root (this file lives in src/)
ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
DB_PATH = ROOT / "data" / "olist.duckdb"

# The 9 expected CSVs and the raw table each becomes.
RAW_FILES: dict[str, str] = {
    "olist_orders_dataset": "orders",
    "olist_order_items_dataset": "order_items",
    "olist_order_payments_dataset": "order_payments",
    "olist_order_reviews_dataset": "order_reviews",
    "olist_customers_dataset": "customers",
    "olist_sellers_dataset": "sellers",
    "olist_products_dataset": "products",
    "olist_geolocation_dataset": "geolocation",
    "product_category_name_translation": "category_translation",
}


def connect() -> duckdb.DuckDBPyConnection:
    """Connect to (or create) the project DuckDB file."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(DB_PATH))


def missing_files() -> list[Path]:
    """CSVs that have not been downloaded yet."""
    return [RAW_DIR / f"{name}.csv" for name in RAW_FILES if not (RAW_DIR / f"{name}.csv").is_file()]


def load_raw_csvs(con: duckdb.DuckDBPyConnection | None = None) -> dict[str, int]:
    """Ingest the Kaggle CSVs into schema `raw` (idempotent: drop-and-recreate).

    Returns a mapping of table name -> row count.
    """
    own = con is None
    con = con or connect()
    missing = missing_files()
    if missing:
        listing = "\n  ".join(str(p) for p in missing)
        raise FileNotFoundError(
            f"{len(missing)} CSV file(s) missing from {RAW_DIR}:\n  {listing}\n"
            "Download the Olist dataset ZIP from "
            "https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce "
            "and extract all CSVs into data/raw/."
        )

    con.execute("CREATE SCHEMA IF NOT EXISTS raw")
    counts: dict[str, int] = {}
    for stem, table in RAW_FILES.items():
        csv_path = (RAW_DIR / f"{stem}.csv").as_posix()
        con.execute(f'DROP TABLE IF EXISTS raw.{table}')
        # All Olist CSVs are UTF-8 with a header row; let DuckDB infer columns.
        con.execute(
            f"CREATE TABLE raw.{table} AS SELECT * FROM read_csv_auto('{csv_path}', header=true)"
        )
        counts[table] = con.execute(f"SELECT COUNT(*) FROM raw.{table}").fetchone()[0]

    if own:
        con.close()
    return counts


def run_sql_file(con: duckdb.DuckDBPyConnection, path: Path) -> None:
    """Execute one of the sql/*.sql scripts (creates or replaces its tables)."""
    con.execute(path.read_text(encoding="utf-8"))


def build_all() -> dict[str, int]:
    """Full rebuild: raw CSVs -> staging -> order_fact -> seller_stats."""
    con = connect()
    try:
        counts = load_raw_csvs(con)
        run_sql_file(con, ROOT / "sql" / "01_staging.sql")
        run_sql_file(con, ROOT / "sql" / "02_order_fact.sql")
        run_sql_file(con, ROOT / "sql" / "03_seller_stats.sql")
        return counts
    finally:
        con.close()


if __name__ == "__main__":
    # `python -m src.db load`  -> rebuild everything and print row counts
    if len(sys.argv) > 1 and sys.argv[1] == "load":
        counts = build_all()
        for table, n in counts.items():
            print(f"raw.{table}: {n:>10,} rows")
        print("Staging, order_fact and seller_stats rebuilt from sql/ scripts.")
    else:
        print("Usage: python -m src.db load")
