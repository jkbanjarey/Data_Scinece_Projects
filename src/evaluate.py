"""Ranking-aware evaluation metrics.

A support team with fixed capacity cares about the TOP of the ranked list,
so precision@k / recall@k lead; PR-AUC summarizes the whole curve.
Accuracy and ROC-AUC are deliberately not used (spec section 10).
"""

from __future__ import annotations

import numpy as np

K_FRACTIONS = (0.01, 0.05, 0.10)


def _top_k_mean(y_true: np.ndarray, scores: np.ndarray, k_frac: float) -> tuple[float, int]:
    """Mean of y among the top k_frac of scores; returns (value, k)."""
    n = len(scores)
    k = max(1, int(round(n * k_frac)))
    # stable sort on negated scores: ties keep original (row) order
    idx = np.argsort(-scores, kind="stable")[:k]
    return float(y_true[idx].mean()), k


def precision_at_k(y_true, scores, k_frac: float) -> float:
    return _top_k_mean(np.asarray(y_true, dtype=float), np.asarray(scores, dtype=float), k_frac)[0]


def recall_at_k(y_true, scores, k_frac: float) -> float:
    y = np.asarray(y_true, dtype=float)
    s = np.asarray(scores, dtype=float)
    n = len(s)
    k = max(1, int(round(n * k_frac)))
    idx = np.argsort(-s, kind="stable")[:k]
    total = y.sum()
    return float(y[idx].sum() / total) if total > 0 else 0.0


def evaluate_scores(y_true, scores, k_fractions=K_FRACTIONS) -> dict:
    """Full metric dict: PR-AUC, precision@k, recall@k, lift@k."""
    from sklearn.metrics import average_precision_score

    y = np.asarray(y_true, dtype=float)
    s = np.asarray(scores, dtype=float)
    out: dict = {"pr_auc": float(average_precision_score(y, s)), "n": int(len(y))}
    base_rate = float(y.mean())
    out["base_rate"] = base_rate
    for k in k_fractions:
        p = precision_at_k(y, s, k)
        out[f"precision@{k:.0%}"] = p
        out[f"recall@{k:.0%}"] = recall_at_k(y, s, k)
        out[f"lift@{k:.0%}"] = p / base_rate if base_rate > 0 else float("nan")
    return out


def format_metrics(m: dict) -> str:
    """Compact one-line rendering for logs/tables."""
    ks = [k for k in m if k.startswith("precision@")]
    parts = [f"PR-AUC {m['pr_auc']:.3f}"]
    for pk in sorted(ks, key=lambda c: float(c.split("@")[1].rstrip('%'))):
        frac = pk.split("@")[1]
        parts.append(f"P@{frac} {m[pk]:.3f} (x{m[pk.replace('precision', 'lift')]:.1f})")
        parts.append(f"R@{frac} {m[pk.replace('precision', 'recall')]:.3f}")
    return " | ".join(parts)
