"""Reconciliation tests: the fact table must match the raw data.

These run the Phase-1 "done when" checks. They require data/olist.duckdb
to exist (run `python -m src.db load` first). The Phase-2 leakage test
(test_no_leakage.py) builds on this file.
"""

from __future__ import annotations

import pytest

from src.db import DB_PATH, connect

pytestmark = pytest.mark.skipif(
    not DB_PATH.is_file(), reason="data/olist.duckdb not built yet (python -m src.db load)"
)


@pytest.fixture(scope="module")
def con():
    c = connect()
    yield c
    c.close()


def _one(con, sql: str):
    return con.execute(sql).fetchone()[0]


def test_raw_tables_present(con):
    n = _one(con, "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'raw'")
    assert n == 9, f"expected 9 raw tables, found {n}"


def test_order_fact_row_count_matches_raw(con):
    raw_n = _one(con, "SELECT COUNT(*) FROM raw.orders")
    fact_n = _one(con, "SELECT COUNT(*) FROM order_fact")
    assert fact_n == raw_n, "order_fact must be exactly one row per raw order"


def test_no_duplicate_orders_in_fact(con):
    dupes = _one(con, "SELECT COUNT(*) FROM (SELECT order_id FROM order_fact GROUP BY order_id HAVING COUNT(*) > 1)")
    assert dupes == 0


def test_reviews_deduplicated_one_per_order(con):
    dupes = _one(
        con,
        "SELECT COUNT(*) FROM (SELECT order_id FROM stg_reviews GROUP BY order_id HAVING COUNT(*) > 1)",
    )
    assert dupes == 0


def test_review_scores_match_dedup_rule(con):
    """Spot check: for orders with >1 raw review, fact must hold the latest one."""
    mismatches = _one(
        con,
        """
        WITH latest AS (
            SELECT order_id, review_score,
                   ROW_NUMBER() OVER (PARTITION BY order_id
                                      ORDER BY review_creation_date DESC, review_answer_timestamp DESC) AS rn
            FROM raw.order_reviews
        )
        SELECT COUNT(*)
        FROM order_fact f
        JOIN latest l USING (order_id)
        WHERE l.rn = 1
          AND f.review_score IS DISTINCT FROM l.review_score
        """,
    )
    assert mismatches == 0


def test_payment_totals_match_raw(con):
    """Sum of order_fact payment_total must equal sum of raw payment_value."""
    raw_sum = _one(con, "SELECT SUM(payment_value) FROM raw.order_payments")
    fact_sum = _one(con, "SELECT SUM(payment_total) FROM order_fact")
    assert fact_sum == pytest.approx(raw_sum, rel=1e-9)


def test_item_price_totals_match_raw(con):
    raw_sum = _one(con, "SELECT SUM(price) FROM raw.order_items")
    fact_sum = _one(con, "SELECT SUM(price_total) FROM order_fact")
    assert fact_sum == pytest.approx(raw_sum, rel=1e-9)


def test_delay_days_sign_matches_dates(con):
    """delay_days > 0 must mean delivered after the estimate."""
    bad = _one(
        con,
        """
        SELECT COUNT(*) FROM order_fact
        WHERE order_delivered_customer_date IS NOT NULL
          AND delay_days != DATE_DIFF('day', order_estimated_delivery_date, order_delivered_customer_date)
        """,
    )
    assert bad == 0


def test_bad_review_definition(con):
    """bad_review must be 1 iff review_score <= 2, NULL iff no review."""
    bad = _one(
        con,
        """
        SELECT COUNT(*) FROM order_fact
        WHERE (review_score IS NULL AND bad_review IS NOT NULL)
           OR (review_score IS NOT NULL AND bad_review IS DISTINCT FROM (CASE WHEN review_score <= 2 THEN 1 ELSE 0 END))
        """,
    )
    assert bad == 0


def test_geolocation_centroid_unique(con):
    dupes = _one(
        con,
        "SELECT COUNT(*) FROM (SELECT zip_prefix FROM stg_geolocation GROUP BY zip_prefix HAVING COUNT(*) > 1)",
    )
    assert dupes == 0
