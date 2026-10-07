"""Phase-3 LightGBM training, operational reason tags, and outreach queue.

Run with ``python -m src.lightgbm_models`` after building feature tables.
The model is trained only on the historical (time-based) training split and
uses validation exclusively for early stopping.  No review or delivery-outcome
columns are admitted to the feature matrix.
"""

from __future__ import annotations

from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from src.evaluate import evaluate_scores
from src.features import load_frame

ROOT = Path(__file__).resolve().parent.parent
META = {"order_id", "purchase_ts", "split", "bad_review"}


def _matrix(df: pd.DataFrame, columns: list[str] | None = None) -> pd.DataFrame:
    """Create a numeric, consistently encoded matrix without meta/target data."""
    x = df.drop(columns=[c for c in META if c in df], errors="ignore").copy()
    x = x.drop(columns=[c for c in x if pd.api.types.is_datetime64_any_dtype(x[c])])
    x = pd.get_dummies(x, dummy_na=True, dtype=float)
    x = x.replace([np.inf, -np.inf], np.nan)
    if columns is not None:
        x = x.reindex(columns=columns, fill_value=0.0)
    return x


def fit_model(train: pd.DataFrame, val: pd.DataFrame) -> tuple[lgb.LGBMClassifier, list[str]]:
    """Fit a class-balanced LightGBM model with validation early stopping."""
    x_train = _matrix(train)
    x_val = _matrix(val, list(x_train.columns))
    y_train = train["bad_review"].astype(int)
    model = lgb.LGBMClassifier(
        objective="binary",
        n_estimators=2_000,
        learning_rate=0.03,
        num_leaves=31,
        min_child_samples=50,
        colsample_bytree=0.8,
        subsample=0.8,
        reg_lambda=1.0,
        random_state=42,
        n_jobs=-1,
        verbosity=-1,
    )
    model.fit(
        x_train,
        y_train,
        eval_set=[(x_val, val["bad_review"].astype(int))],
        eval_metric="average_precision",
        callbacks=[lgb.early_stopping(100, verbose=False)],
    )
    return model, list(x_train.columns)


def reason_tags(model: lgb.LGBMClassifier, x: pd.DataFrame, max_tags: int = 3) -> list[str]:
    """Turn per-row positive feature contributions into concise action tags."""
    contributions = model.predict(x, pred_contrib=True)[:, :-1]
    feature_names = np.asarray(x.columns)
    groups = (
        ("handoff / delivery promise risk", ("handling_hours", "margin_days", "processing_hours", "approval_lag")),
        ("seller track-record risk", ("seller_hist", "seller_prev")),
        ("category track-record risk", ("cat_hist", "cat_prev")),
        ("long-distance delivery risk", ("distance", "same_state")),
        ("order value / freight risk", ("price_total", "freight", "payment_total")),
        ("product / basket complexity", ("n_items", "n_sellers", "n_products", "product_")),
        ("payment-method risk", ("pay_", "installment", "n_payments")),
    )
    tags: list[str] = []
    for row in contributions:
        weights: dict[str, float] = {}
        for tag, prefixes in groups:
            mask = np.array([any(name.startswith(p) for p in prefixes) for name in feature_names])
            weights[tag] = float(row[mask][row[mask] > 0].sum()) if mask.any() else 0.0
        selected = [tag for tag, value in sorted(weights.items(), key=lambda item: item[1], reverse=True) if value > 0][:max_tags]
        tags.append("; ".join(selected) if selected else "no dominant positive driver")
    return tags


def run() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Train Stage A/B models; return metrics and the Stage-B test outreach queue."""
    metrics: list[dict] = []
    queue: pd.DataFrame | None = None
    for stage in ("stage_a", "stage_b"):
        train, val, test = (load_frame(stage, split) for split in ("train", "val", "test"))
        model, columns = fit_model(train, val)
        for split, frame in (("val", val), ("test", test)):
            x = _matrix(frame, columns)
            scores = model.predict_proba(x)[:, 1]
            metrics.append({"model": "lightgbm", "stage": stage[-1].upper(), "split": split,
                            "best_iteration": model.best_iteration_, **evaluate_scores(frame["bad_review"], scores)})
            if stage == "stage_b" and split == "test":
                n = max(1, int(round(len(frame) * 0.05)))
                queue = frame[["order_id", "purchase_ts", "customer_state", "seller_state"]].copy()
                queue["risk_score"] = scores
                queue["reason_tags"] = reason_tags(model, x)
                queue = queue.sort_values("risk_score", ascending=False, kind="stable").head(n)
    assert queue is not None
    return pd.DataFrame(metrics), queue


def write_results(metrics: pd.DataFrame, queue: pd.DataFrame) -> None:
    out = ROOT / "results"
    out.mkdir(exist_ok=True)
    metrics.to_csv(out / "lightgbm.csv", index=False)
    queue.to_csv(out / "outreach_queue_stage_b_test.csv", index=False)
    cols = ["model", "stage", "split", "best_iteration", "pr_auc", "base_rate", "precision@5%", "recall@5%", "lift@5%", "n"]
    display = metrics[cols].copy()
    for col in ("pr_auc", "base_rate", "precision@5%", "recall@5%", "lift@5%"):
        display[col] = display[col].map(lambda value: f"{value:.3f}")
    (out / "lightgbm.md").write_text(
        "# LightGBM (Phase 3)\n\n"
        "Time-based train/validation/test evaluation. The validation period is used only for early stopping.\n\n"
        f"{display.to_string(index=False)}\n\n"
        "The Stage-B test outreach queue contains the highest-risk 5% of orders and contribution-based reason tags.\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    metric_table, outreach_queue = run()
    write_results(metric_table, outreach_queue)
    print(metric_table.to_string(index=False))
    print(f"\nWrote results/lightgbm.* and {len(outreach_queue):,}-row Stage-B outreach queue")
