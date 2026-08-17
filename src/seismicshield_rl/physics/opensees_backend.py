from __future__ import annotations

class OpenSeesBackend:
    """Validation gate for the primary high-fidelity structural backend.

    v0.1 deliberately refuses to return structural results. Implementing a model that merely
    executes is not enough: v0.2 must document element/material choices, unit conventions,
    recorder parsing, convergence policy and matched-case parity tests before this backend is
    enabled for research claims.
    """
    status = "gated-until-v0.2-parity"

    def __init__(self, *args, **kwargs):
        try:
            import openseespy.opensees as _ops  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "OpenSeesPy is optional. Use Python 3.12 and install the 'opensees' extra."
            ) from exc

    def simulate(self, design, ground_motion):
        raise NotImplementedError(
            "OpenSees execution is intentionally gated until v0.2 parity tests are implemented."
        )
