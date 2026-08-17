from __future__ import annotations
import numpy as np
from seismicshield_rl.config import BuildingConfig
from .base import DamperDesign, GroundMotion, SimulationResult

class ShearBuildingSimulator:
    """Fast nonlinear research surrogate.

    The damper model is a smooth Coulomb-like force law
    F = F_slip * tanh(v_rel / v_eps). It is useful for algorithm development,
    not a substitute for a validated friction-device model in OpenSees.
    """

    def __init__(self, building: BuildingConfig, *, velocity_eps_mps: float = 0.004, max_substep_s: float = 0.0025):
        self.building = building
        self.velocity_eps_mps = float(velocity_eps_mps)
        self.max_substep_s = float(max_substep_s)
        self.M = np.diag(building.masses_kg)
        self.Minv = np.diag(1.0 / building.masses_kg)
        self.B = self._incidence(building.n_stories)
        self.K = self.B @ np.diag(building.stiffness_n_per_m) @ self.B.T
        self.C = self._rayleigh_damping(building.damping_ratio)

    @staticmethod
    def _incidence(n: int) -> np.ndarray:
        # story relative deformation r = B.T @ x
        B = np.zeros((n, n), dtype=float)
        for story in range(n):
            B[story, story] = 1.0
            if story > 0:
                B[story - 1, story] = -1.0
        return B

    def _rayleigh_damping(self, zeta: float) -> np.ndarray:
        eig = np.linalg.eigvals(self.Minv @ self.K)
        omega = np.sqrt(np.sort(np.real(eig[eig > 0])))
        if omega.size == 0:
            return np.zeros_like(self.K)
        w1, w2 = float(omega[0]), float(omega[-1])
        if abs(w2 - w1) < 1e-12:
            alpha = 2.0 * zeta * w1
            beta = 0.0
        else:
            # solve zeta = alpha/(2w) + beta*w/2 at first/last mode
            A = np.array([[1/(2*w1), w1/2], [1/(2*w2), w2/2]], dtype=float)
            alpha, beta = np.linalg.solve(A, np.array([zeta, zeta]))
        return alpha * self.M + beta * self.K

    def _rhs(self, state: np.ndarray, ag: float, capacity: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        n = self.building.n_stories
        x = state[:n]
        v = state[n:]
        rel_v = self.B.T @ v
        f_story = capacity * np.tanh(rel_v / self.velocity_eps_mps)
        external = -self.building.masses_kg * ag
        a = self.Minv @ (external - self.C @ v - self.K @ x - self.B @ f_story)
        return np.concatenate([v, a]), f_story

    def simulate(self, design: DamperDesign, ground_motion: GroundMotion) -> SimulationResult:
        n = self.building.n_stories
        if design.counts.size != n:
            raise ValueError(f"design must have {n} stories")
        t = ground_motion.time_s
        ag = ground_motion.accel_mps2
        state = np.zeros(2*n, dtype=float)
        x_hist = np.zeros((t.size, n)); v_hist = np.zeros_like(x_hist)
        ar_hist = np.zeros_like(x_hist); f_hist = np.zeros_like(x_hist)
        cap = design.total_story_capacity_n.astype(float)

        # deterministic fixed-step RK4 with interpolation of ground acceleration
        for i in range(t.size):
            x_hist[i] = state[:n]; v_hist[i] = state[n:]
            rhs, f = self._rhs(state, float(ag[i]), cap)
            ar_hist[i] = rhs[n:]; f_hist[i] = f
            if i == t.size - 1:
                break
            dt_total = float(t[i+1] - t[i])
            steps = max(1, int(np.ceil(dt_total / self.max_substep_s)))
            h = dt_total / steps
            for s in range(steps):
                frac0 = s / steps
                fracm = (s + 0.5) / steps
                frac1 = (s + 1.0) / steps
                a0 = float(ag[i] + frac0 * (ag[i+1] - ag[i]))
                am = float(ag[i] + fracm * (ag[i+1] - ag[i]))
                a1 = float(ag[i] + frac1 * (ag[i+1] - ag[i]))
                k1, _ = self._rhs(state, a0, cap)
                k2, _ = self._rhs(state + 0.5*h*k1, am, cap)
                k3, _ = self._rhs(state + 0.5*h*k2, am, cap)
                k4, _ = self._rhs(state + h*k3, a1, cap)
                state = state + h*(k1 + 2*k2 + 2*k3 + k4)/6.0

        story_def = x_hist @ self.B
        drift = story_def / self.building.story_height_m
        abs_acc = ar_hist + ag[:, None]
        rel_v_story = v_hist @ self.B
        power = np.abs(f_hist * rel_v_story)
        dissipated = float(np.trapezoid(power.sum(axis=1), t))
        metrics = {
            "midr": float(np.max(np.abs(drift))),
            "pfa_mps2": float(np.max(np.abs(abs_acc))),
            "pfa_g": float(np.max(np.abs(abs_acc)) / 9.80665),
            "max_displacement_m": float(np.max(np.abs(x_hist))),
            "dissipated_energy_j": dissipated,
        }
        finite = all(np.isfinite(v) for v in metrics.values()) and np.all(np.isfinite(x_hist))
        return SimulationResult(
            time_s=t.copy(), displacement_m=x_hist, velocity_mps=v_hist,
            relative_accel_mps2=ar_hist, absolute_accel_mps2=abs_acc,
            story_drift_ratio=drift, damper_force_n=f_hist, metrics=metrics,
            converged=bool(finite), backend="shear-surrogate-v0.1",
        )
