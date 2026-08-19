import subprocess
import sys


def test_kendo_entrypoint_supports_direct_script_execution():
    completed = subprocess.run(
        [sys.executable, "scripts/screen_afad_tadas_station_summaries_kendo.py", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert "deterministic event_candidate_queue.csv" in completed.stdout
