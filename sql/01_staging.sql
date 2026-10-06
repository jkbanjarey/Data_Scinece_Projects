-- 01_staging.sql — clean views over raw tables, handling known data quirks.
-- Each quirk from the project spec (section 2) has a RULE comment.
-- All models are CREATE OR REPLACE so the whole file is idempotent.

------------------------------------------------------------------------
-- stg_products: product attributes + English category name
-- RULE: category names arrive in Portuguese; join the translation table.
--       Products with an untranslated category keep the Portuguese name.
------------------------------------------------------------------------
CREATE OR REPLACE VIEW stg_products AS
SELECT
    p.product_id,
    p.product_category_name,
    COALESCE(t.product_category_name_english, p.product_category_name) AS category_en,
    p.product_name_lenght,
    p.product_description_lenght,
    p.product_photos_qty,
    p.product_weight_g,
    p.product_length_cm,
    p.product_height_cm,
    p.product_width_cm,
    -- volume in liters (cm^3 / 1000); NULLs propagate naturally
    p.product_length_cm * p.product_height_cm * p.product_width_cm / 1000.0 AS product_volume_l
FROM raw.products p
LEFT JOIN raw.category_translation t
    ON p.product_category_name = t.product_category_name;

------------------------------------------------------------------------
-- stg_reviews: one review per order
-- RULE: some orders have multiple reviews. Keep the latest by creation
--       date (tie-break: answer timestamp), and record how many there were.
------------------------------------------------------------------------
CREATE OR REPLACE VIEW stg_reviews AS
WITH ranked AS (
    SELECT
        r.*,
        ROW_NUMBER() OVER (
            PARTITION BY order_id
            ORDER BY review_creation_date DESC, review_answer_timestamp DESC
        ) AS rn,
        COUNT(*) OVER (PARTITION BY order_id) AS n_reviews
    FROM raw.order_reviews r
)
SELECT
    order_id,
    review_id,
    review_score,
    review_comment_title,
    review_comment_message,
    review_creation_date,
    review_answer_timestamp,
    n_reviews
FROM ranked
WHERE rn = 1;

------------------------------------------------------------------------
-- stg_geolocation: one centroid per zip prefix
-- RULE: the geolocation file has many rows per zip prefix (and city-name
--       spelling variants). Average lat/lng per prefix for distance math.
------------------------------------------------------------------------
CREATE OR REPLACE VIEW stg_geolocation AS
SELECT
    geolocation_zip_code_prefix AS zip_prefix,
    AVG(geolocation_lat) AS lat,
    AVG(geolocation_lng) AS lng
FROM raw.geolocation
GROUP BY geolocation_zip_code_prefix;

------------------------------------------------------------------------
-- stg_customers: customer info per order.
-- RULE: customer_id is unique per ORDER; customer_unique_id identifies the
--       person. Most people order once — do not build features on repeat
--       history (documented in the spec, section 4).
------------------------------------------------------------------------
CREATE OR REPLACE VIEW stg_customers AS
SELECT
    customer_id,
    customer_unique_id,
    customer_zip_code_prefix AS zip_prefix,
    customer_city,
    customer_state
FROM raw.customers;

------------------------------------------------------------------------
-- stg_sellers
------------------------------------------------------------------------
CREATE OR REPLACE VIEW stg_sellers AS
SELECT
    seller_id,
    seller_zip_code_prefix AS zip_prefix,
    seller_city,
    seller_state
FROM raw.sellers;

------------------------------------------------------------------------
-- stg_order_payments: order-level payment aggregates.
-- RULE: an order can have several payment rows (installments, multiple
--       cards). Aggregate here so the fact table joins 1:1.
------------------------------------------------------------------------
CREATE OR REPLACE VIEW stg_order_payments AS
SELECT
    order_id,
    SUM(payment_value)                          AS payment_total,
    MAX(payment_installments)                   AS max_installments,
    COUNT(*)                                    AS n_payments,
    -- distinct types collapsed to a comma list, most used order is alphabetical
    STRING_AGG(DISTINCT payment_type, ',' ORDER BY payment_type) AS payment_types,
    -- flag: any installment plan > 1 (credit behaviour proxy)
    MAX(CASE WHEN payment_installments > 1 THEN 1 ELSE 0 END) AS has_installments
FROM raw.order_payments
GROUP BY order_id;

------------------------------------------------------------------------
-- stg_order_items: order-level item aggregates.
-- RULE: an order can have multiple items / sellers / products. Aggregate
--       to order grain; keep the primary (first-listed) item's product
--       and seller as the order's representative.
------------------------------------------------------------------------
CREATE OR REPLACE VIEW stg_order_items AS
WITH agg AS (
    SELECT
        order_id,
        SUM(price)         AS price_total,
        SUM(freight_value) AS freight_total,
        COUNT(*)           AS n_items,
        COUNT(DISTINCT seller_id) AS n_sellers,
        COUNT(DISTINCT product_id) AS n_products,
        MIN(order_item_id) AS primary_item_id
    FROM raw.order_items
    GROUP BY order_id
),
primary_item AS (
    SELECT i.order_id, i.product_id, i.seller_id, i.shipping_limit_date
    FROM raw.order_items i
    JOIN agg a
      ON i.order_id = a.order_id AND i.order_item_id = a.primary_item_id
)
SELECT
    a.order_id,
    a.price_total,
    a.freight_total,
    a.n_items,
    a.n_sellers,
    a.n_products,
    pi.product_id  AS primary_product_id,
    pi.seller_id   AS primary_seller_id,
    pi.shipping_limit_date
FROM agg a
JOIN primary_item pi ON a.order_id = pi.order_id;
