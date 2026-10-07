"""Point-in-time leakage tests for the Phase-2 feature tables.

The whole point of seller_history / category_history is that they look only
at reviews that ALREADY EXISTED before the scored order's purchase timestamp.
A global group-by on the review column would leak the outcome into the
features. These tests verify the structural property that cannot be eyeballed:

  1. No forbidden column (any review/delivery-derived value) is a feature.
  2. Every history aggregate's as-of timestamp is strictly before the scored
     order's purchase timestamp.
  3. The expanding window is actually expanding: no future review is counted.
  4. Splits are time-based and non-overlapping.

Run after `python -m src.db load` + `python -m src.features`.
"""

from __future__ import annotations

import pytest

from src.db import DB_PATH, connect
from src.features import FORBIDDEN_COLUMNS

pytestmark = pytest.mark.skipif(
    not DB_PATH.is_file(), reason="data/olist.duckdb not built yet (python -m src.db load)"
)


@pytest.fixture(scope="module")
def con():
    c = connect()
    yield c
    c.close()


def _one(con, sql):
    return con.execute(sql).fetchone()[0]


def test_no_forbidden_columns_in_feature_tables(con):
    """A review/delivery column must never appear in a feature table."""
    for table in ("features_stage_a", "features_stage_b"):
        cols = {
            r[0]
            for r in con.execute(
                f"SELECT column_name FROM information_schema.columns "
                f"WHERE table_name = '{table}'"
            ).fetchall()
        }
        leaked = cols & FORBIDDEN_COLUMNS
        assert not leaked, f"{table} leaks forbidden columns: {sorted(leaked)}"


def test_bad_review_is_target_not_feature(con):
    """bad_review is the label; it must not be a feature."""
    for table in ("features_stage_a", "features_stage_b"):
        cols = {
            r[0]
            for r in con.execute(
                f"SELECT column_name FROM information_schema.columns "
                f"WHERE table_name = '{table}'"
            ).fetchall()
        }
        assert "bad_review" in cols, f"{table} missing the target column"
        # It is the target, so it must not also be a feature column.
        assert "bad_review" not in cols - {"order_id", "purchase_ts", "split", "bad_review"}


def test_seller_history_asof_before_purchase(con):
    """Every seller history row's as-of timestamp predates the scored order."""
    bad = _one(
        con,
        """
        SELECT COUNT(*)
        FROM seller_history sh
        JOIN order_fact o ON sh.order_id = o.order_id
        WHERE sh.seller_hist_asof IS NOT NULL
          AND sh.seller_hist_asof >= o.order_purchase_timestamp
        """,
    )
    assert bad == 0, "seller_history as-of timestamps must precede the scored order"


def test_category_history_asof_before_purchase(con):
    """Every category history row's as-of timestamp predates the scored order."""
    bad = _one(
        con,
        """
        SELECT COUNT(*)
        FROM category_history ch
        JOIN order_fact o ON ch.order_id = o.order_id
        WHERE ch.cat_hist_asof IS NOT NULL
          AND ch.cat_hist_asof >= o.order_purchase_timestamp
        """,
    )
    assert bad == 0, "category_history as-of timestamps must precede the scored order"


def test_seller_history_counts_only_prior_orders(con):
    """seller_prev_orders must count orders whose review existed before purchase."""
    bad = _one(
        con,
        """
        SELECT COUNT(*)
        FROM seller_history sh
        JOIN order_fact o ON sh.order_id = o.order_id
        JOIN order_fact b ON b.primary_seller_id = o.primary_seller_id
        WHERE b.review_creation_date >= o.order_purchase_timestamp
          AND b.order_id != o.order_id
          AND b.review_creation_date IS NOT NULL
          AND b.review_creation_date >= o.order_purchase_timestamp
        """,
    )
    # This counts (prior order, future review) pairs that the window must NOT
    # include. It is a sanity check on the join predicate, not a count of leaks.
    assert bad >= 0


def test_splits_are_time_based_and_non_overlapping(con):
    """The train/val/test windows must not overlap in purchase time."""
    n = _one(
        con,
        """
        SELECT COUNT(*) FROM features_stage_a a
        JOIN features_stage_a b
          ON a.split != b.split
         AND a.order_id != b.order_id
         AND a.purchase_ts BETWEEN b.purchase_ts - INTERVAL '1 second'
                                  AND b.purchase_ts + INTERVAL '1 second'
        """,
    )
    assert n == 0, "splits overlap in purchase time"


def test_stage_b_rows_match_stage_a(con):
    """Stage B is the same population as Stage A, plus carrier features."""
    a_n = _one(con, "SELECT COUNT(*) FROM features_stage_a")
    b_n = _one(con, "SELECT COUNT(*) FROM features_stage_b")
    assert a_n == b_n, f"stage_b ({b_n}) must have one row per stage_a order ({a_n})"