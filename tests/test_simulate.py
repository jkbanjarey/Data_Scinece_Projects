import numpy as np

from src.simulate import simulate_interventions


def test_simulation_targets_highest_scores_and_reports_sensitivity():
    result = simulate_interventions(
        [0, 1, 1, 0],
        {"ranked": np.array([0.1, 0.9, 0.8, 0.2])},
        capacity=0.5,
        save_rates=(0.1, 0.3),
    )
    assert list(result["bad_reviews_contacted"]) == [2, 2]
    assert list(result["expected_bad_reviews_averted"]) == [0.2, 0.6]
    assert list(result["contacts"]) == [2, 2]
