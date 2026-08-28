from scripts.run_softwarex_example import run_example


def test_softwarex_example_is_validation_only(tmp_path):
    summary = run_example(tmp_path / "softwarex-example")

    assert summary["seismicshield_rl_version"] == "0.8.3"
    assert summary["status"] == "software-validation-only"
    assert summary["confirmatory_data_used"] is False
    assert summary["paper_level_efficacy_claim"] is False
    assert summary["all_converged"] is True
    assert set(summary["artifacts"]) == {"benchmark.csv", "benchmark.json", "manifest.json"}
