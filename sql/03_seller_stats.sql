-- 03_seller_stats.sql — per-seller CX aggregates.
--
-- EDA VERSION: full-period aggregates. Good for the Phase-1 breakdown
-- ("where do bad experiences concentrate?").
--
-- DO NOT USE AS MODEL FEATURES. The modeling version (Phase 2/3) must be
-- point-in-time: only orders whose reviews existed BEFORE the scored
-- order's timestamp (expanding window with a lag). A global group-by on
-- the review column leaks the outcome into the features.

CREATE OR REPLACE TABLE seller_stats AS
WITH flagged AS (
    SELECT
        f.*,
        -- on-time = delivered on or before the estimated date (NULL if not delivered)
        CASE
            WHEN f.order_delivered_customer_date IS NOT NULL
            THEN f.delay_days <= 0
        END AS on_time_metric,
        CASE WHEN f.review_score IS NOT NULL
            THEN CASE WHEN f.bad_review = 1 THEN 1.0 ELSE 0.0 END
        END AS bad_review_among_reviewed
    FROM order_fact f
)
SELECT
    s.seller_id,
    s.seller_state,
    s.seller_city,
    COUNT(DISTINCT f.order_id)                            AS n_orders,
    COUNT(DISTINCT CASE WHEN f.review_score IS NOT NULL THEN f.order_id END) AS n_reviewed_orders,
    AVG(f.review_score)                                   AS avg_review_score,
    -- rates among reviewed orders only (NULL if the seller was never reviewed)
    AVG(f.bad_review_among_reviewed)                      AS bad_review_rate,
    -- rates among delivered orders only
    AVG(CASE WHEN f.on_time_metric THEN 1.0
             WHEN f.on_time_metric IS NOT NULL THEN 0.0
             ELSE NULL END)                               AS on_time_rate,
    AVG(CASE WHEN f.shipped_late THEN 1.0
             WHEN f.shipped_late IS NOT NULL THEN 0.0
             ELSE NULL END)                               AS late_shipment_rate,
    AVG(f.delay_days)                                     AS avg_delay_days,
    AVG(f.freight_ratio)                                  AS avg_freight_ratio,
    SUM(f.price_total)                                    AS revenue_total
FROM flagged f
JOIN stg_sellers s ON f.primary_seller_id = s.seller_id
GROUP BY s.seller_id, s.seller_state, s.seller_city;
