from pathlib import Path
import hashlib, json
from seismicshield_rl.benchmark import run_benchmark
ROOT=Path(__file__).resolve().parents[1]

def test_smoke_benchmark_writes_manifest(tmp_path):
    rows=run_benchmark(ROOT/'configs/experiments/smoke.yaml',tmp_path)
    assert len(rows)==4
    manifest=json.loads((tmp_path/'manifest.json').read_text())
    assert manifest['status']=='software-validation-only'
    assert set(manifest['artifacts'])=={'benchmark.csv','benchmark.json'}
    for name, digest in manifest['artifacts'].items():
        assert hashlib.sha256((tmp_path/name).read_bytes()).hexdigest()==digest

def test_smoke_benchmark_is_byte_reproducible(tmp_path):
    first=tmp_path/'first'; second=tmp_path/'second'
    run_benchmark(ROOT/'configs/experiments/smoke.yaml',first)
    run_benchmark(ROOT/'configs/experiments/smoke.yaml',second)
    for name in ['benchmark.csv','benchmark.json','manifest.json']:
        assert (first/name).read_bytes()==(second/name).read_bytes()
