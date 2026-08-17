from pathlib import Path
import numpy as np
from seismicshield_rl.config import BuildingConfig
from seismicshield_rl.physics.base import DamperDesign
from seismicshield_rl.physics.ground_motion import load_csv_ground_motion
from seismicshield_rl.physics.shear_building import ShearBuildingSimulator
from seismicshield_rl.evaluator import DesignEvaluator
from seismicshield_rl.baselines.random_search import random_search

ROOT=Path(__file__).resolve().parents[1]

def evaluator():
    b=BuildingConfig.from_yaml(ROOT/'configs/buildings/3story.yaml')
    gm=load_csv_ground_motion(ROOT/'data/fixtures/synthetic_pulse.csv')
    return DesignEvaluator(ShearBuildingSimulator(b),gm,max_dampers_per_story=4,max_slip_force_n=350000.0)

def test_zero_design_has_unit_response_ratios():
    e=evaluator(); n=e.simulator.building.n_stories
    ev=e.evaluate(DamperDesign(np.zeros(n,dtype=int),np.zeros(n)))
    assert np.isclose(ev.midr_ratio,1.0)
    assert np.isclose(ev.pfa_ratio,1.0)
    assert np.isclose(ev.cost,0.0)

def test_random_search_reproducible():
    e=evaluator(); kwargs=dict(n_stories=3,max_dampers_per_story=4,slip_force_levels_n=[0,50000,100000],budget=8,seed=11)
    a=random_search(e,**kwargs); b=random_search(e,**kwargs)
    assert np.array_equal(a.design.counts,b.design.counts)
    assert np.array_equal(a.design.slip_force_n,b.design.slip_force_n)
    assert a.objective==b.objective
