"""Feature table builder (runs sql/04_features.sql) and pandas loaders.

The split boundaries live here AND as literals in sql/04_features.sql —
keep the two in sync. tests/test_no_leakage.py verifies the structural
properties of whatever the SQL produces.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SQL_DIR = ROOT / "sql"

# Split boundaries (exclusive upper bounds) — mirror of sql/04_features.sql
WINDOW_START = "2017-01-01"
TRAIN_END = "2018-05-01"   # train: 2017-01 .. 2018-04
VAL_END = "2018-07-01"     # val:   2018-05 .. 2018-06
WINDOW_END = "2018-09-01"  # test:  2018-07 .. 2018-08

SPLITS = ("train", "val", "test")

# Columns that must NEVER appear in a feature table (review/delivery leakage).
FORBIDDEN_COLUMNS = {
    "order_delivered_customer_date",
    "delay_days",
    "bad_review_among_reviewed",
    "on_time_metric",
    "review_score",
    "review_creation_date",
    "review_comment_message",
    "has_comment",
    "n_reviews",
}


def build_features(con: duckdb.DuckDBPyConnection | None = None) -> None:
    """Rebuild seller_history, category_history, features_stage_a/b."""
    own = con is None
    con = con or duckdb.connect(str(ROOT / "data" / "olist.duckdb"))
    try:
        con.execute((SQL_DIR / "04_features.sql").read_text(encoding="utf-8"))
    finally:
        if own:
            con.close()


def load_frame(stage: str, split: str | None = None) -> pd.DataFrame:
    """Load a feature table (optionally one split) as a DataFrame."""
    assert stage in ("stage_a", "stage_b")
    table = f"features_{stage}"
    query = f"SELECT * FROM {table}"
    if split is not None:
        assert split in SPLITS
        query += f" WHERE split = '{split}'"
    con = duckdb.connect(str(ROOT / "data" / "olist.duckdb"))
    try:
        return con.execute(query).df()
    finally:
        con.close()


def feature_columns(df: pd.DataFrame) -> list[str]:
    """Feature matrix columns: everything except the meta/target columns."""
    meta = {"order_id", "purchase_ts", "split", "bad_review"}
    return [c for c in df.columns if c not in meta]


if __name__ == "__main__":
    build_features()
    con = duckdb.connect(str(ROOT / "data" / "olist.duckdb"))
    try:
        stats = con.execute(
            """
            SELECT split, COUNT(*) AS n,
                   AVG(bad_review) AS prevalence,
                   MIN(purchase_ts) AS first_purchase,
                   MAX(purchase_ts) AS last_purchase
            FROM features_stage_a GROUP BY split
            ORDER BY CASE split WHEN 'train' THEN 1 WHEN 'val' THEN 2 ELSE 3 END
            """
        ).df()
        print(stats.to_string(index=False))
        n_b = con.execute("SELECT COUNT(*) FROM features_stage_b").fetchone()[0]
        print(f"\nfeatures_stage_b: {n_b:,} rows (stage_a + carrier-handoff features)")
    finally:
        con.close()
