from pathlib import Path
import json
from seismicshield_rl.benchmark import run_benchmark
ROOT=Path(__file__).resolve().parents[1]

def test_smoke_benchmark_writes_manifest(tmp_path):
    rows=run_benchmark(ROOT/'configs/experiments/smoke.yaml',tmp_path)
    assert len(rows)==4
    manifest=json.loads((tmp_path/'manifest.json').read_text())
    assert manifest['status']=='software-validation-only'
    assert set(manifest['artifacts'])=={'benchmark.csv','benchmark.json'}
