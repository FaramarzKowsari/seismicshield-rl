from __future__ import annotations
from pathlib import Path
import tempfile
import numpy as np
from fastapi import FastAPI
from pydantic import BaseModel, Field
from seismicshield_rl.config import BuildingConfig
from seismicshield_rl.physics.base import DamperDesign
from seismicshield_rl.physics.ground_motion import load_csv_ground_motion
from seismicshield_rl.physics.shear_building import ShearBuildingSimulator
from seismicshield_rl.benchmark import run_benchmark

app=FastAPI(title='SeismicShield-RL Research API',version='0.1.0',description='Exploratory research API. Not for structural certification.')
REPO=Path(__file__).resolve().parents[3]

class DesignRequest(BaseModel):
    counts: list[int]=Field(default=[1,1,1])
    slip_force_n: list[float]=Field(default=[100000,100000,100000])

@app.get('/health')
def health():
    return {'status':'ok','version':'0.1.0','scientific_status':'exploratory'}

@app.post('/simulate')
def simulate(req: DesignRequest):
    building=BuildingConfig.from_yaml(REPO/'configs/buildings/3story.yaml')
    gm=load_csv_ground_motion(REPO/'data/fixtures/synthetic_pulse.csv',motion_id='synthetic-pulse-v1')
    design=DamperDesign(np.asarray(req.counts,dtype=int),np.asarray(req.slip_force_n,dtype=float))
    result=ShearBuildingSimulator(building).simulate(design,gm)
    return {'backend':result.backend,'converged':result.converged,'metrics':result.metrics,'status':'synthetic-exploratory'}

@app.post('/benchmark/smoke')
def smoke_benchmark():
    with tempfile.TemporaryDirectory() as td:
        rows=run_benchmark(REPO/'configs/experiments/smoke.yaml',td)
    return {'status':'software-validation-only','rows':rows}
