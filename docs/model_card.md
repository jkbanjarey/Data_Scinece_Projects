# LightGBM CX Risk Model Card

## Intended use

Rank in-progress Olist orders for proactive support outreach. It is a triage tool, not an automated decision system: agents decide whether and how to contact a customer.

## Prediction target and timing

The target is a bad review (`review_score <= 2`) for delivered orders that received a review. Stage A scores at order placement; Stage B scores at carrier handoff. The 2017-01 through 2018-08 population is split strictly by purchase time: train through April 2018, validation in May--June, and test in July--August.

## Inputs and safeguards

Inputs include basket, payment, product, geography, purchase timing, and point-in-time seller/category history. Stage B additionally includes handoff and promised-delivery margin features. Review text, review fields, actual delivery outcomes, and post-purchase information are excluded. The leakage tests verify the feature-table constraints.

## Performance

On the held-out Stage-B test period, LightGBM reaches PR-AUC 0.255 and precision@5% 0.395 (246 bad-review orders among 622 contacts). This is better than the already-late rule at precision@5% 0.240. See `results/lightgbm.md` for the full metric table.

## Explanations

Each Stage-B queue row receives up to three reason tags based on positive LightGBM feature contributions. Tags summarize risk drivers (for example, handoff/delivery-promise risk or seller track-record risk); they are explanations of the model's ranking, not proof of customer dissatisfaction or causal mechanisms.

## Intervention simulation

The simulation compares model-ranked, already-late, and random outreach at a fixed 5% capacity. Its 10%, 20%, and 30% save-rate scenarios are assumptions, not estimates of treatment effect. A controlled outreach experiment is required before using the expected-averted figures for operational planning.

## Limitations

The dataset is historical, Brazilian, and limited to orders with reviews, so it may not represent unreviewed customers or a current marketplace. Model performance can drift as seller mix, logistics, and support policy change. Re-evaluate calibration, ranking quality, and subgroup behavior before deployment and on a recurring schedule afterward.
