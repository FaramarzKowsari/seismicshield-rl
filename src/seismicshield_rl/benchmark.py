from __future__ import annotations
from dataclasses import asdict
import csv, hashlib, json
from pathlib import Path
import yaml
from .config import BuildingConfig
from .physics.ground_motion import load_csv_ground_motion
from .physics.shear_building import ShearBuildingSimulator
from .evaluator import DesignEvaluator
from .baselines.heuristics import no_damper, uniform_design, drift_proportional_design
from .baselines.random_search import random_search


def _resolve(base: Path, value: str) -> Path:
    p=Path(value)
    return p if p.is_absolute() else base / p


def run_benchmark(config_path: str | Path, output_dir: str | Path) -> list[dict]:
    config_path=Path(config_path).resolve(); repo_root=config_path.parents[2]
    cfg=yaml.safe_load(config_path.read_text(encoding='utf-8'))
    building=BuildingConfig.from_yaml(_resolve(repo_root,cfg['building']))
    gm=load_csv_ground_motion(_resolve(repo_root,cfg['ground_motion']), motion_id='synthetic-pulse-v1')
    sim=ShearBuildingSimulator(building)
    levels=cfg['slip_force_levels_n']; max_d=int(cfg['max_dampers_per_story'])
    evaluator=DesignEvaluator(sim,gm,max_dampers_per_story=max_d,max_slip_force_n=max(levels))
    n=building.n_stories
    candidates=[]
    candidates.append(('no_damper',no_damper(n)))
    candidates.append(('uniform_1x100k',uniform_design(n,count=1,slip_force_n=100_000.0)))
    candidates.append(('drift_proportional',drift_proportional_design(evaluator.reference,total_dampers=n,slip_force_n=100_000.0,max_per_story=max_d)))
    rs=random_search(evaluator,n_stories=n,max_dampers_per_story=max_d,slip_force_levels_n=levels,budget=int(cfg['random_search_budget']),seed=int(cfg['seed']))
    candidates.append((f"random_search_budget_{cfg['random_search_budget']}",rs.design))
    rows=[]
    for method,design in candidates:
        ev=evaluator.evaluate(design)
        rows.append({
            'method':method,'counts':' '.join(map(str,design.counts.tolist())),
            'slip_force_n':' '.join(str(float(x)) for x in design.slip_force_n.tolist()),
            'cost':ev.cost,'midr':ev.midr,'pfa_g':ev.pfa_g,
            'midr_ratio':ev.midr_ratio,'pfa_ratio':ev.pfa_ratio,
            'objective':ev.objective,'reward':ev.reward,'converged':ev.converged,
            'status':'software-validation-only',
        })
    out=Path(output_dir); out.mkdir(parents=True,exist_ok=True)
    with (out/'benchmark.csv').open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0].keys())); writer.writeheader(); writer.writerows(rows)
    (out/'benchmark.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
    manifest={'experiment_id':cfg['id'],'config':str(config_path.relative_to(repo_root)),'status':cfg['status'],'artifacts':{}}
    for name in ['benchmark.csv','benchmark.json']:
        data=(out/name).read_bytes(); manifest['artifacts'][name]=hashlib.sha256(data).hexdigest()
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    return rows
