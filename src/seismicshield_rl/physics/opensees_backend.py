from __future__ import annotations

import math

import numpy as np

from seismicshield_rl.config import BuildingConfig
from .base import DamperDesign, GroundMotion, SimulationResult


class OpenSeesBackend:
    """Tier-2 nonlinear reference backend for the frozen shear-building archetype.

    The structural springs are elastic and the retrofit devices use OpenSees' native
    ``CoulombDamper`` uniaxial material. UniformExcitation produces relative nodal
    accelerations; absolute floor acceleration is reconstructed by adding the input
    ground acceleration at the same analysis time.

    This class is usable only after the dedicated Tier-2 validation workflow passes.
    The confirmatory gate remains the authority on whether research runs are allowed.
    """

    status = "implemented-pending-tier2-validation"

    def __init__(
        self,
        building: BuildingConfig,
        *,
        max_substep_s: float = 0.0025,
        convergence_tolerance: float = 1e-10,
        convergence_iterations: int = 50,
        damper_capacity_scale: float = 1.0,
    ):
        try:
            import openseespy.opensees as ops
        except ImportError as exc:
            raise RuntimeError(
                "OpenSeesPy is required for Tier-2. Use Python 3.12 and install the 'opensees' extra."
            ) from exc
        if max_substep_s <= 0:
            raise ValueError("max_substep_s must be positive")
        if convergence_tolerance <= 0 or convergence_iterations <= 0:
            raise ValueError("invalid convergence settings")
        if damper_capacity_scale <= 0:
            raise ValueError("damper_capacity_scale must be positive")
        self.ops = ops
        self.building = building
        self.max_substep_s = float(max_substep_s)
        self.convergence_tolerance = float(convergence_tolerance)
        self.convergence_iterations = int(convergence_iterations)
        self.damper_capacity_scale = float(damper_capacity_scale)

    def _rayleigh_coefficients(self) -> tuple[float, float]:
        n = self.building.n_stories
        incidence = np.zeros((n, n), dtype=float)
        for story in range(n):
            incidence[story, story] = 1.0
            if story > 0:
                incidence[story - 1, story] = -1.0
        stiffness = incidence @ np.diag(self.building.stiffness_n_per_m) @ incidence.T
        inv_mass = np.diag(1.0 / self.building.masses_kg)
        eig = np.linalg.eigvals(inv_mass @ stiffness)
        omega = np.sqrt(np.sort(np.real(eig[eig > 0])))
        if omega.size == 0:
            return 0.0, 0.0
        w1, w2 = float(omega[0]), float(omega[-1])
        zeta = float(self.building.damping_ratio)
        if math.isclose(w1, w2, rel_tol=0.0, abs_tol=1e-12):
            return 2.0 * zeta * w1, 0.0
        matrix = np.array([[1.0 / (2.0 * w1), w1 / 2.0], [1.0 / (2.0 * w2), w2 / 2.0]])
        alpha, beta = np.linalg.solve(matrix, np.array([zeta, zeta]))
        return float(alpha), float(beta)

    def _build_model(self, design: DamperDesign, ground_motion: GroundMotion) -> list[int | None]:
        ops = self.ops
        n = self.building.n_stories
        if design.counts.size != n:
            raise ValueError(f"design must have {n} stories")
        ops.wipe()
        ops.model("basic", "-ndm", 1, "-ndf", 1)

        # ZeroLength elements are an abstract story-DOF network, so all nodes share a coordinate.
        for node in range(1, n + 2):
            ops.node(node, 0.0)
        ops.fix(1, 1)
        for story in range(n):
            ops.mass(story + 2, float(self.building.masses_kg[story]))

        damper_elements: list[int | None] = []
        capacities = design.total_story_capacity_n.astype(float) * self.damper_capacity_scale
        for story in range(n):
            lower, upper = story + 1, story + 2
            elastic_mat = 1000 + story
            elastic_ele = 2000 + story
            ops.uniaxialMaterial("Elastic", elastic_mat, float(self.building.stiffness_n_per_m[story]))
            ops.element(
                "zeroLength",
                elastic_ele,
                lower,
                upper,
                "-mat",
                elastic_mat,
                "-dir",
                1,
                "-doRayleigh",
                1,
            )
            capacity = float(capacities[story])
            if capacity > 0.0:
                damper_mat = 3000 + story
                damper_ele = 4000 + story
                try:
                    ops.uniaxialMaterial("CoulombDamper", damper_mat, 0.0, capacity)
                except Exception as exc:  # OpenSees raises implementation-specific exception types.
                    raise RuntimeError("OpenSees build does not provide the required CoulombDamper material") from exc
                ops.element(
                    "zeroLength",
                    damper_ele,
                    lower,
                    upper,
                    "-mat",
                    damper_mat,
                    "-dir",
                    1,
                    "-doRayleigh",
                    0,
                )
                damper_elements.append(damper_ele)
            else:
                damper_elements.append(None)

        alpha, beta = self._rayleigh_coefficients()
        ops.rayleigh(alpha, beta, 0.0, 0.0)

        times = np.asarray(ground_motion.time_s, dtype=float)
        times = times - times[0]
        accel = np.asarray(ground_motion.accel_mps2, dtype=float)
        ops.timeSeries("Path", 1, "-time", *times.tolist(), "-values", *accel.tolist())
        ops.pattern("UniformExcitation", 1, 1, "-accel", 1)
        ops.constraints("Plain")
        ops.numberer("Plain")
        ops.system("BandGeneral")
        ops.test("NormDispIncr", self.convergence_tolerance, self.convergence_iterations, 0)
        ops.algorithm("Newton")
        ops.integrator("Newmark", 0.5, 0.25)
        ops.analysis("Transient")
        return damper_elements

    def simulate(self, design: DamperDesign, ground_motion: GroundMotion) -> SimulationResult:
        ops = self.ops
        n = self.building.n_stories
        t = np.asarray(ground_motion.time_s, dtype=float)
        ag = np.asarray(ground_motion.accel_mps2, dtype=float)
        x_hist = np.zeros((t.size, n), dtype=float)
        v_hist = np.zeros_like(x_hist)
        ar_hist = np.zeros_like(x_hist)
        f_hist = np.zeros_like(x_hist)
        converged = True
        damper_elements: list[int | None] = []

        try:
            damper_elements = self._build_model(design, ground_motion)
            # At zero displacement/velocity, relative acceleration satisfies M*a = -M*ag.
            ar_hist[0, :] = -float(ag[0])
            for index in range(t.size - 1):
                dt_total = float(t[index + 1] - t[index])
                steps = max(1, int(math.ceil(dt_total / self.max_substep_s)))
                h = dt_total / steps
                for _ in range(steps):
                    if ops.analyze(1, h) != 0:
                        converged = False
                        break
                if not converged:
                    x_hist[index + 1 :, :] = np.nan
                    v_hist[index + 1 :, :] = np.nan
                    ar_hist[index + 1 :, :] = np.nan
                    f_hist[index + 1 :, :] = np.nan
                    break
                for story in range(n):
                    node = story + 2
                    x_hist[index + 1, story] = float(ops.nodeDisp(node, 1))
                    v_hist[index + 1, story] = float(ops.nodeVel(node, 1))
                    ar_hist[index + 1, story] = float(ops.nodeAccel(node, 1))
                    element = damper_elements[story]
                    if element is not None:
                        response = ops.eleForce(element)
                        if isinstance(response, (list, tuple, np.ndarray)):
                            f_hist[index + 1, story] = float(response[-1])
                        else:
                            f_hist[index + 1, story] = float(response)
        finally:
            ops.wipe()

        incidence = np.zeros((n, n), dtype=float)
        for story in range(n):
            incidence[story, story] = 1.0
            if story > 0:
                incidence[story - 1, story] = -1.0
        story_def = x_hist @ incidence
        drift = story_def / float(self.building.story_height_m)
        abs_acc = ar_hist + ag[:, None]
        rel_v_story = v_hist @ incidence
        power = np.abs(f_hist * rel_v_story)

        if converged:
            dissipated = float(np.trapezoid(power.sum(axis=1), t))
            metrics = {
                "midr": float(np.max(np.abs(drift))),
                "pfa_mps2": float(np.max(np.abs(abs_acc))),
                "pfa_g": float(np.max(np.abs(abs_acc)) / 9.80665),
                "max_displacement_m": float(np.max(np.abs(x_hist))),
                "dissipated_energy_j": dissipated,
            }
        else:
            metrics = {
                "midr": float("inf"),
                "pfa_mps2": float("inf"),
                "pfa_g": float("inf"),
                "max_displacement_m": float("inf"),
                "dissipated_energy_j": float("inf"),
            }
        return SimulationResult(
            time_s=t.copy(),
            displacement_m=x_hist,
            velocity_mps=v_hist,
            relative_accel_mps2=ar_hist,
            absolute_accel_mps2=abs_acc,
            story_drift_ratio=drift,
            damper_force_n=f_hist,
            metrics=metrics,
            converged=converged,
            backend="opensees-coulomb-shear-v0.8.1",
        )
