"""Phase-2 baselines, reproducible with one command:

    uv run python -m src.baselines

Baselines (spec section 7, phase 2):
  * majority      - constant score at the train-set prevalence
  * already-late  - Stage B rule: rank by remaining margin at handoff
                    (most negative first); the operational heuristic
  * logistic      - logistic regression on Stage A features (and on Stage B
                    for a first look at what the handoff information adds)

LightGBM at both stages is Phase 3. Results are written to results/baselines.md.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from src.evaluate import evaluate_scores
from src.features import load_frame

CATEGORICAL = ["category_en", "customer_state", "seller_state"]
RESULTS_DIR = "results"


def _logistic_model() -> Pipeline:
    """Unfitted preprocessing + balanced logistic regression."""
    numeric = Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
    ])
    categorical = Pipeline([
        ("impute", SimpleImputer(strategy="most_frequent")),
        ("onehot", OneHotEncoder(handle_unknown="ignore", min_frequency=20)),
    ])
    return Pipeline([
        ("prep", ColumnTransformer([
            ("num", numeric, []),
            ("cat", categorical, []),
        ], remainder="drop")),
        ("clf", LogisticRegression(max_iter=2000, class_weight="balanced", C=0.5)),
    ])


def _fit_logistic(train: pd.DataFrame, target_cols: list[str]) -> Pipeline:
    """Fit a logistic model on all non-meta, non-datetime columns."""
    drop = [c for c in target_cols if c in train.columns]
    # Metadata / history-asof timestamps are not model features.
    drop += [c for c in train.columns if c not in drop and pd.api.types.is_datetime64_any_dtype(train[c])]
    X = train.drop(columns=drop)
    cat = [c for c in CATEGORICAL if c in X.columns]
    num = [c for c in X.columns if c not in cat]

    numeric = Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
    ])
    categorical = Pipeline([
        ("impute", SimpleImputer(strategy="most_frequent")),
        ("onehot", OneHotEncoder(handle_unknown="ignore", min_frequency=20)),
    ])
    prep = ColumnTransformer([
        ("num", numeric, num),
        ("cat", categorical, cat),
    ], remainder="drop")
    pipe = Pipeline([
        ("prep", prep),
        ("clf", LogisticRegression(max_iter=2000, class_weight="balanced", C=0.5)),
    ])
    pipe.fit(X, train["bad_review"].astype(int))
    return pipe


def _scores(pipe: Pipeline, df: pd.DataFrame, target_cols: list[str]) -> np.ndarray:
    drop = [c for c in target_cols if c in df.columns]
    drop += [c for c in df.columns if c not in drop and pd.api.types.is_datetime64_any_dtype(df[c])]
    X = df.drop(columns=drop)
    return pipe.predict_proba(X)[:, 1]


def run() -> pd.DataFrame:
    a = {s: load_frame("stage_a", s) for s in ("train", "val", "test")}
    b = {s: load_frame("stage_b", s) for s in ("val", "test")}
    train_prev = float(a["train"]["bad_review"].mean())

    rows: list[dict] = []

    def record(model: str, stage: str, split: str, y, scores):
        m = evaluate_scores(y, scores)
        rows.append({"model": model, "stage": stage, "split": split, **m})

    # --- majority: constant train prevalence (identical for both stages)
    for stage, frames in (("A", a), ("B", {**a, **b})):
        for split in ("val", "test"):
            df = frames[split]
            record("majority", stage, split, df["bad_review"],
                   np.full(len(df), train_prev))

    # --- already-late: operational rule, Stage B only
    # margin_days_at_handoff < 0 means the promise is already blown at handoff
    for split in ("val", "test"):
        df = b[split]
        scores = -df["margin_days_at_handoff"].fillna(0.0)
        record("already-late", "B", split, df["bad_review"], scores)

    # --- logistic on Stage A
    target_cols_a = ["order_id", "purchase_ts", "split", "bad_review"]
    pipe_a = _fit_logistic(a["train"], target_cols_a)
    for split in ("val", "test"):
        record("logistic", "A", split,
               a[split]["bad_review"],
               _scores(pipe_a, a[split], target_cols_a))

    # --- logistic on Stage B (richer information at carrier handoff)
    b_train = load_frame("stage_b", "train")
    pipe_b = _fit_logistic(b_train, target_cols_a)
    for split in ("val", "test"):
        record("logistic", "B", split,
               b[split]["bad_review"],
               _scores(pipe_b, b[split], target_cols_a))

    return pd.DataFrame(rows)


def write_results(table: pd.DataFrame) -> None:
    from pathlib import Path

    out_dir = Path(__file__).resolve().parent.parent / RESULTS_DIR
    out_dir.mkdir(exist_ok=True)
    table.to_csv(out_dir / "baselines.csv", index=False)

    cols = ["model", "stage", "split", "pr_auc", "base_rate",
            "precision@1%", "precision@5%", "precision@10%",
            "recall@1%", "recall@5%", "recall@10%", "n"]
    t = table[cols].copy()
    for c in cols[3:-1]:
        t[c] = t[c].map(lambda v: f"{v:.3f}")
    lines = [
        "# Baselines (Phase 2)",
        "",
        "Time-based split: train 2017-01..2018-04, val 2018-05..06, test 2018-07..08.",
        "Metrics computed on the stated split; ranking metrics are threshold-free.",
        "",
        t.to_string(index=False),
        "",
        "Notes:",
        "- `majority` scores every order at the train-set prevalence; its PR-AUC equals the base rate by construction.",
        "- `already-late` is the operational heuristic available at Stage B: rank by remaining margin at handoff.",
        "- Logistic regression uses one-hot category/states + median-imputed, scaled numerics (class_weight=balanced).",
    ]
    (out_dir / "baselines.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    table = run()
    show_cols = ["model", "stage", "split", "pr_auc", "base_rate",
                 "precision@5%", "recall@5%", "lift@5%", "n"]
    print(table[show_cols].to_string(index=False))
    write_results(table)
    print("\nWrote results/baselines.md and results/baselines.csv")
