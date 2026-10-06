# Proactive CX Risk Engine

Flag Olist marketplace orders likely to end in a bad review (score ≤ 2) **while the order is still in progress**, explain the likely reason, and rank them so a capacity-limited support team contacts the right customers first.

> **Status: Phase 1 (data model + CX metrics).** Model results below are targets to fill in, not claims.

## Headline result (placeholder)

- Contacting the top 5% riskiest orders captures **[X]%** of bad reviews, vs **[Y]%** for random outreach.
- Stage-B (shipment) model vs Stage-A (order placement): **[delta]**.

## Data

[Olist Brazilian E-commerce Public Dataset](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) (~100k orders, 2016–2018, anonymized).

**Manual download (one-time):**

1. Download the ZIP from the Kaggle page above (needs a free Kaggle account).
2. Extract all 9 CSVs into `data/raw/`:

```
data/raw/
  olist_orders_dataset.csv
  olist_order_items_dataset.csv
  olist_order_payments_dataset.csv
  olist_order_reviews_dataset.csv
  olist_customers_dataset.csv
  olist_sellers_dataset.csv
  olist_products_dataset.csv
  olist_geolocation_dataset.csv
  product_category_name_translation.csv
```

`data/` is gitignored — the CSVs are never committed (license: CC BY-NC-SA 4.0, cited here).

## How to run

```bash
uv sync                                   # create venv from pyproject.toml
uv run python -m src.db load              # ingest CSVs -> data/olist.duckdb + staging + fact tables
uv run pytest                             # reconciliation tests
uv run jupyter lab notebooks/             # open 01_eda_and_cx_metrics.ipynb
```

## Approach (in 5 bullets)

1. **Two scoring stages** — A: order placed, B: order shipped — to show *when* support can act and what each stage adds.
2. **Point-in-time feature correctness** — seller/category history features use only reviews that existed before the scored order; enforced by an automated leakage test.
3. **Reason tags from Portuguese review text** (multilingual embeddings), validated against hand labels.
4. **Delay → satisfaction impact** quantified with controls, reported as association.
5. **Capacity-constrained intervention simulation** — model-ranked vs random vs "already late" outreach, with sensitivity bands on assumed save rate.

## Repo map

```
sql/        staging -> order_fact -> seller stats (DuckDB)
notebooks/  EDA, split/leakage, modeling, reasons, delay impact, simulation
src/        db loader, features, training, evaluation, simulation
tests/      reconciliation + no-leakage tests
docs/       decision memo, model card
app/        FastAPI /score + Streamlit queue (Phase 7)
```
