from pathlib import Path
from seismicshield_rl.benchmark import run_benchmark

ROOT=Path(__file__).resolve().parents[1]
rows=run_benchmark(ROOT/'configs/experiments/smoke.yaml',ROOT/'results/smoke_v0.1')
for row in rows:
    print(row['method'], f"objective={row['objective']:.6f}", f"MIDR={row['midr']:.6g}", f"PFA(g)={row['pfa_g']:.4f}")
print('Wrote results/smoke_v0.1/{benchmark.csv,benchmark.json,manifest.json}')
