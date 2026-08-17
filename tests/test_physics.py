from pathlib import Path
import numpy as np
from seismicshield_rl.config import BuildingConfig
from seismicshield_rl.physics.base import DamperDesign
from seismicshield_rl.physics.ground_motion import load_csv_ground_motion
from seismicshield_rl.physics.shear_building import ShearBuildingSimulator

ROOT=Path(__file__).resolve().parents[1]

def setup_case():
    b=BuildingConfig.from_yaml(ROOT/'configs/buildings/3story.yaml')
    gm=load_csv_ground_motion(ROOT/'data/fixtures/synthetic_pulse.csv')
    return b,gm,ShearBuildingSimulator(b)

def test_zero_design_is_finite_and_shaped():
    b,gm,sim=setup_case(); d=DamperDesign(np.zeros(b.n_stories,dtype=int),np.zeros(b.n_stories))
    r=sim.simulate(d,gm)
    assert r.converged
    assert r.displacement_m.shape==(gm.time_s.size,b.n_stories)
    assert r.story_drift_ratio.shape==r.displacement_m.shape
    assert r.metrics['midr']>0 and r.metrics['pfa_g']>0

def test_simulation_is_deterministic():
    b,gm,sim=setup_case(); d=DamperDesign(np.ones(b.n_stories,dtype=int),np.full(b.n_stories,100000.0))
    a=sim.simulate(d,gm); c=sim.simulate(d,gm)
    assert np.array_equal(a.displacement_m,c.displacement_m)
    assert a.metrics==c.metrics

def test_damper_energy_nonnegative():
    b,gm,sim=setup_case(); d=DamperDesign(np.ones(b.n_stories,dtype=int),np.full(b.n_stories,100000.0))
    r=sim.simulate(d,gm)
    assert r.metrics['dissipated_energy_j']>=0
