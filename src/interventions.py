"""Run the Phase-3 intervention sensitivity analysis.

    python -m src.interventions
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from src.features import load_frame
from src.lightgbm_models import _matrix, fit_model
from src.simulate import simulate_interventions


def run():
    train, val, test = (load_frame("stage_b", split) for split in ("train", "val", "test"))
    model, columns = fit_model(train, val)
    model_scores = model.predict_proba(_matrix(test, columns))[:, 1]
    already_late = -test["margin_days_at_handoff"].fillna(0.0).to_numpy()
    # Fixed RNG makes the random-outreach comparator reproducible.
    random_scores = np.random.default_rng(42).random(len(test))
    return simulate_interventions(
        test["bad_review"],
        {"lightgbm-ranked": model_scores, "already-late": already_late, "random": random_scores},
    )


if __name__ == "__main__":
    table = run()
    output = Path(__file__).resolve().parent.parent / "results" / "intervention_simulation.csv"
    output.parent.mkdir(exist_ok=True)
    table.to_csv(output, index=False)
    print(table.to_string(index=False))
    print(f"\nWrote {output}")
