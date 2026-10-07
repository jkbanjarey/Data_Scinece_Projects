-- 04_features.sql — point-in-time correct feature tables for Stage A / Stage B.
--
-- LEAKAGE RULES (spec section 4) enforced here:
--   * No column derived from order_delivered_customer_date or any review
--     field enters a feature table (bad_review is the target, not a feature).
--   * Seller/category history aggregates use ONLY orders whose review
--     already existed before the scored order's purchase timestamp
--     (b.review_creation_date < s.order_purchase_timestamp) — an expanding
--     window, not a global group-by. The max contributing review timestamp
--     is stored as *_hist_asof so tests/test_no_leakage.py can verify it.
--   * Carrier-derived features (handling, margin at handoff) exist ONLY in
--     Stage B — the scoring event is the carrier handoff itself.
--
-- SPLIT DESIGN (keep in sync with BOUNDARIES in src/features.py):
--   modeling window 2017-01-01 .. 2018-08-31 (sparse 2016 / 2018-09+ excluded)
--   train: purchase < 2018-05-01 | val: 2018-05 .. 2018-06 | test: 2018-07 .. 2018-08
--
-- Population: delivered orders with a review (target is defined).

CREATE OR REPLACE VIEW modeling_orders AS
SELECT *
FROM order_fact
WHERE is_delivered
  AND review_score IS NOT NULL
  AND order_purchase_timestamp >= TIMESTAMP '2017-01-01'
  AND order_purchase_timestamp <  TIMESTAMP '2018-09-01';

------------------------------------------------------------------------
-- seller_history: expanding-window seller stats as of each order's purchase
-- b = any prior order by the same seller whose review already existed.
-- Order PLACEMENT is observable (counts in volume); the OUTCOME only counts
-- once its review existed (counts in rates).
------------------------------------------------------------------------
CREATE OR REPLACE TABLE seller_history AS
SELECT
    s.order_id,
    COUNT(b.order_id)                              AS seller_prev_orders,
    COUNT(b.bad_review)                            AS seller_prev_reviewed,
    AVG(b.bad_review)                              AS seller_hist_bad_rate,
    AVG(CASE WHEN b.order_delivered_customer_date < s.order_purchase_timestamp
             THEN CASE WHEN b.delay_days <= 0 THEN 1.0 ELSE 0.0 END END) AS seller_hist_on_time_rate,
    AVG(CASE WHEN b.order_delivered_customer_date < s.order_purchase_timestamp
             THEN b.delay_days END)                AS seller_hist_avg_delay,
    AVG(CASE WHEN b.order_delivered_carrier_date < s.order_purchase_timestamp
             THEN CASE WHEN b.shipped_late THEN 1.0
                       WHEN b.shipped_late IS NOT NULL THEN 0.0 END END) AS seller_hist_late_ship_rate,
    MAX(b.review_creation_date)                    AS seller_hist_asof
FROM modeling_orders s
LEFT JOIN order_fact b
       ON b.primary_seller_id = s.primary_seller_id
      AND b.review_creation_date < s.order_purchase_timestamp
GROUP BY s.order_id;

------------------------------------------------------------------------
-- category_history: same expanding-window logic per category
------------------------------------------------------------------------
CREATE OR REPLACE TABLE category_history AS
SELECT
    s.order_id,
    COUNT(b.order_id)                              AS cat_prev_orders,
    COUNT(b.bad_review)                            AS cat_prev_reviewed,
    AVG(b.bad_review)                              AS cat_hist_bad_rate,
    MAX(b.review_creation_date)                    AS cat_hist_asof
FROM modeling_orders s
LEFT JOIN order_fact b
       ON b.category_en = s.category_en
      AND b.category_en IS NOT NULL
      AND b.review_creation_date < s.order_purchase_timestamp
GROUP BY s.order_id;

------------------------------------------------------------------------
-- features_stage_a: everything known at ORDER PLACEMENT
------------------------------------------------------------------------
CREATE OR REPLACE TABLE features_stage_a AS
SELECT
    -- meta (not features: id, scoring timestamp, split, target)
    m.order_id,
    m.order_purchase_timestamp AS purchase_ts,
    CASE
        WHEN m.order_purchase_timestamp < TIMESTAMP '2018-05-01' THEN 'train'
        WHEN m.order_purchase_timestamp < TIMESTAMP '2018-07-01' THEN 'val'
        ELSE 'test'
    END AS split,
    m.bad_review,

    -- price / freight / basket
    m.price_total,
    m.freight_total,
    m.freight_ratio,
    m.n_items,
    m.n_sellers,
    m.n_products,

    -- payment
    m.payment_total,
    m.max_installments,
    m.n_payments,
    m.has_installments,
    STRPOS(m.payment_types, 'credit_card') > 0 AS pay_credit_card,
    STRPOS(m.payment_types, 'boleto')      > 0 AS pay_boleto,
    STRPOS(m.payment_types, 'voucher')     > 0 AS pay_voucher,
    STRPOS(m.payment_types, 'debit_card')  > 0 AS pay_debit_card,

    -- product / category
    m.category_en,
    m.product_weight_g,
    m.product_volume_l,
    m.product_photos_qty,
    m.product_description_lenght,

    -- geography (customer vs primary seller)
    m.customer_state,
    sl.seller_state,
    m.customer_state = sl.seller_state AS same_state,
    -- haversine distance between zip-prefix centroids; NULL if prefix unknown
    CASE
        WHEN gc.lat IS NULL OR gs.lat IS NULL THEN NULL
        ELSE 6371.0 * 2 * asin(sqrt(
            pow(sin(radians(gs.lat - gc.lat) / 2), 2) +
            cos(radians(gc.lat)) * cos(radians(gs.lat)) *
            pow(sin(radians(gs.lng - gc.lng) / 2), 2)
        ))
    END AS distance_km,
    gc.lat IS NULL OR gs.lat IS NULL AS distance_missing,

    -- timing known at placement
    m.promised_window_days,
    dayofweek(m.order_purchase_timestamp) AS purchase_dow,
    month(m.order_purchase_timestamp)     AS purchase_month,
    hour(m.order_purchase_timestamp)      AS purchase_hour,

    -- expanding-window seller history (point-in-time, see seller_history)
    sh.seller_prev_orders,
    sh.seller_prev_reviewed,
    sh.seller_hist_bad_rate,
    sh.seller_hist_on_time_rate,
    sh.seller_hist_avg_delay,
    sh.seller_hist_late_ship_rate,
    sh.seller_hist_asof,
    COALESCE(sh.seller_prev_reviewed, 0) > 0 AS seller_history_available,

    -- expanding-window category history
    ch.cat_prev_orders,
    ch.cat_prev_reviewed,
    ch.cat_hist_bad_rate,
    ch.cat_hist_asof
FROM modeling_orders m
JOIN stg_sellers sl ON m.primary_seller_id = sl.seller_id
LEFT JOIN stg_geolocation gc ON m.customer_zip_prefix = gc.zip_prefix
LEFT JOIN stg_geolocation gs ON sl.zip_prefix = gs.zip_prefix
LEFT JOIN seller_history sh ON m.order_id = sh.order_id
LEFT JOIN category_history ch ON m.order_id = ch.order_id;

------------------------------------------------------------------------
-- features_stage_b: Stage A + information revealed at CARRIER HANDOFF
-- (the scoring event is the handoff itself, so carrier timestamps are legal)
------------------------------------------------------------------------
CREATE OR REPLACE TABLE features_stage_b AS
SELECT
    a.*,
    DATE_DIFF('second', f.order_delivered_carrier_date, f.shipping_limit_date) / 3600.0
        AS handling_hours,                       -- >0 = handed off after the shipping limit
    DATE_DIFF('second', f.order_delivered_carrier_date, f.order_estimated_delivery_date) / 86400.0
        AS margin_days_at_handoff,               -- time left vs the promise
    DATE_DIFF('second', f.order_delivered_carrier_date, f.order_purchase_timestamp) / 3600.0
        AS processing_hours,                     -- purchase -> handoff
    f.approval_lag_hours
FROM features_stage_a a
JOIN modeling_orders f ON a.order_id = f.order_id;
