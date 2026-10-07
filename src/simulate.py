"""Capacity-constrained intervention simulation for a scored outreach queue."""

from __future__ import annotations

import numpy as np
import pandas as pd


def simulate_interventions(y_true, strategies: dict[str, np.ndarray], capacity: float = 0.05,
                           save_rates: tuple[float, ...] = (0.10, 0.20, 0.30)) -> pd.DataFrame:
    """Estimate bad reviews averted if a contacted bad-review order is saved.

    ``save_rate`` is explicitly an assumption, not a causal estimate from the
    observational Olist data. Ties are resolved stably for reproducibility.
    """
    y = np.asarray(y_true, dtype=int)
    n_contacts = max(1, int(round(len(y) * capacity)))
    rows: list[dict] = []
    for name, scores in strategies.items():
        selected = np.argsort(-np.asarray(scores), kind="stable")[:n_contacts]
        bad_reviews_contacted = int(y[selected].sum())
        for save_rate in save_rates:
            rows.append({
                "strategy": name, "capacity": capacity, "contacts": n_contacts,
                "save_rate_assumption": save_rate,
                "bad_reviews_contacted": bad_reviews_contacted,
                "expected_bad_reviews_averted": bad_reviews_contacted * save_rate,
                "expected_bad_reviews_remaining": float(y.sum() - bad_reviews_contacted * save_rate),
            })
    return pd.DataFrame(rows)
