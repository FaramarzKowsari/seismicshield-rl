from __future__ import annotations
from pathlib import Path
import csv
import numpy as np
from .base import GroundMotion


def load_csv_ground_motion(path: str | Path, *, motion_id: str | None = None, source: str = "synthetic") -> GroundMotion:
    path = Path(path)
    t, a = [], []
    with path.open("r", encoding="utf-8", newline="") as f:
        rows = csv.DictReader(f)
        for row in rows:
            t.append(float(row["time_s"]))
            a.append(float(row["accel_mps2"]))
    return GroundMotion(id=motion_id or path.stem, time_s=np.asarray(t), accel_mps2=np.asarray(a), source=source)
