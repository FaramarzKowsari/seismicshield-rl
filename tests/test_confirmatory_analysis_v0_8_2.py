import numpy as np
import pytest

from seismicshield_rl.confirmatory_analysis_v0_8_2 import (
    bootstrap_mean_ci,
    exact_sign_flip_pvalue,
    holm_adjust,
    hypervolume_3d,
    nondominated,
    paired_event_inference,
    select_cost_slice,
)


def test_nondominated_removes_duplicates_and_dominated_points():
    points = [
        [0.2, 1.0, 1.0],
        [0.2, 1.0, 1.0],
        [0.3, 1.2, 1.2],
        [0.4, 0.8, 1.1],
    ]
    observed = nondominated(points)
    assert observed.shape == (2, 3)
    assert np.any(np.all(np.isclose(observed, [0.2, 1.0, 1.0]), axis=1))
    assert np.any(np.all(np.isclose(observed, [0.4, 0.8, 1.1]), axis=1))


def test_hypervolume_single_box_and_union_are_exact():
    assert hypervolume_3d([[0.0, 0.0, 0.0]], [1.0, 1.0, 1.0]) == pytest.approx(1.0)
    observed = hypervolume_3d(
        [[0.0, 0.5, 0.5], [0.5, 0.0, 0.5]],
        [1.0, 1.0, 1.0],
    )
    assert observed == pytest.approx(0.375)


def test_hypervolume_point_outside_reference_contributes_zero():
    assert hypervolume_3d([[1.1, 1.0, 1.0]], [1.05, 5.0, 5.0]) == 0.0


def test_cost_slice_uses_discrete_tie_break_without_interpolation():
    rows = [
        {"normalized_cost": 0.20, "MIDR": 0.012, "PFA_g": 0.70, "seed": 2207},
        {"normalized_cost": 0.25, "MIDR": 0.012, "PFA_g": 0.60, "seed": 3313},
        {"normalized_cost": 0.30, "MIDR": 0.005, "PFA_g": 0.40, "seed": 1103},
    ]
    selected = select_cost_slice(rows, ceiling=0.25, metric="MIDR")
    assert selected["seed"] == 3313
    selected_pfa = select_cost_slice(rows, ceiling=0.25, metric="PFA_g")
    assert selected_pfa["seed"] == 3313


def test_exact_sign_flip_is_two_sided_and_exact():
    assert exact_sign_flip_pvalue([1.0, 1.0]) == pytest.approx(0.5)
    assert exact_sign_flip_pvalue([0.0, 0.0]) == pytest.approx(1.0)


def test_bootstrap_is_replayable_with_frozen_seed():
    differences = np.linspace(-0.2, 0.4, 12)
    first = bootstrap_mean_ci(differences, repetitions=2000, seed=998035145)
    second = bootstrap_mean_ci(differences, repetitions=2000, seed=998035145)
    assert first == second
    assert first[0] <= float(np.mean(differences)) <= first[1]


def test_holm_adjustment_is_monotone_and_stable():
    adjusted = holm_adjust({"c": 0.04, "a": 0.01, "b": 0.03})
    assert adjusted["a"] == pytest.approx(0.03)
    assert adjusted["b"] == pytest.approx(0.06)
    assert adjusted["c"] == pytest.approx(0.06)


def test_primary_inference_requires_exactly_twelve_events():
    with pytest.raises(ValueError):
        paired_event_inference(np.ones(11))
    result = paired_event_inference(np.linspace(0.01, 0.12, 12))
    assert result.effect == pytest.approx(0.065)
    assert 0.0 <= result.p_raw <= 1.0
