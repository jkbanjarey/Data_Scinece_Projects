-- 02_order_fact.sql — one row per order with CX metrics.
-- Non-delivered statuses are KEPT and flagged (is_delivered), not dropped:
-- canceled/unavailable orders get separate handling downstream.
--
-- LEAKAGE NOTE (spec section 4): delay_days / on_time use
-- order_delivered_customer_date, which exists only AFTER delivery.
-- They are CX METRICS for Phase-1 analysis ONLY. The Phase-2/3 feature
-- builder must NOT expose them as model features at either scoring stage.

CREATE OR REPLACE TABLE order_fact AS
SELECT
    o.order_id,
    o.customer_id,
    c.customer_unique_id,
    o.order_status,
    o.order_purchase_timestamp,
    o.order_approved_at,
    o.order_delivered_carrier_date,
    o.order_delivered_customer_date,
    o.order_estimated_delivery_date,

    -- customer geography
    c.zip_prefix            AS customer_zip_prefix,
    c.customer_city         AS customer_city,
    c.customer_state        AS customer_state,

    -- item aggregates (from stg_order_items)
    i.price_total,
    i.freight_total,
    i.n_items,
    i.n_sellers,
    i.n_products,
    CASE WHEN i.price_total > 0 THEN i.freight_total / i.price_total END AS freight_ratio,
    i.primary_product_id,
    i.primary_seller_id,
    i.shipping_limit_date,

    -- payment aggregates (from stg_order_payments)
    p.payment_total,
    p.max_installments,
    p.n_payments,
    p.payment_types,
    p.has_installments,

    -- product / category of the primary item
    pr.category_en,
    pr.product_weight_g,
    pr.product_volume_l,
    pr.product_photos_qty,
    pr.product_description_lenght,

    -- review (deduplicated in stg_reviews)
    r.review_score,
    r.review_creation_date,
    r.review_comment_message IS NOT NULL AND LENGTH(TRIM(r.review_comment_message)) > 0 AS has_comment,
    r.n_reviews,

    -- derived CX metrics ----------------------------------------------
    -- delivery delay vs promise, in days (positive = late)
    DATE_DIFF('day', o.order_estimated_delivery_date, o.order_delivered_customer_date) AS delay_days,
    DATE_DIFF('day', o.order_purchase_timestamp, o.order_estimated_delivery_date) AS promised_window_days,
    -- approval lag in hours
    DATE_DIFF('second', o.order_purchase_timestamp, o.order_approved_at) / 3600.0 AS approval_lag_hours,

    o.order_delivered_customer_date IS NOT NULL AS is_delivered,
    o.order_delivered_carrier_date <= o.order_estimated_delivery_date AS delivered_by_estimate,
    -- seller handed off to carrier after the shipping limit date
    i.shipping_limit_date IS NOT NULL
        AND o.order_delivered_carrier_date > i.shipping_limit_date AS shipped_late,

    -- target definition (spec section 4): bad = score <= 2, only where reviewed
    CASE WHEN r.review_score <= 2 THEN 1 ELSE 0 END AS bad_review   -- NULL propagates where no review

FROM raw.orders o
JOIN stg_customers c ON o.customer_id = c.customer_id
LEFT JOIN stg_order_items i ON o.order_id = i.order_id
LEFT JOIN stg_order_payments p ON o.order_id = p.order_id
LEFT JOIN stg_products pr ON i.primary_product_id = pr.product_id
LEFT JOIN stg_reviews r ON o.order_id = r.order_id;
