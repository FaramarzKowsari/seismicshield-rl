"""Pure contract helpers for the preregistered real ground-motion manifest."""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path
from typing import Iterable

SALT = "SeismicShield-RL-v0.8.0-OSF-2026"
PARTITIONS = (("training", 18), ("validation", 6), ("pilot", 4), ("confirmatory", 12))
COLUMNS = (
    "source", "event_id", "record_id", "station_id", "component",
    "sampling_interval_s", "usable_duration_s", "original_units", "normalized_units",
    "pga_g", "event_date", "latitude", "longitude", "partition",
    "source_url_or_access_reference", "preprocessing_status", "raw_sha256",
    "processed_sha256", "eligibility_status", "eligibility_reason",
)
PROVENANCE_FIELDS = (
    "source", "event_id", "record_id", "station_id", "event_date", "latitude",
    "longitude", "source_url_or_access_reference", "preprocessing_status", "raw_sha256",
    "processed_sha256",
)
FORBIDDEN_MARKERS = ("fake", "placeholder", "synthetic", "dummy", "fixture", "example.com", "unknown")
SI_UNITS = {"m/s^2", "m/s2", "m s-2"}
CONVERTIBLE_UNITS = SI_UNITS | {"g", "gal", "cm/s^2", "cm/s2"}


def sha_key(kind: str, row: dict[str, str]) -> str:
    if kind == "event":
        identity = f"{row['source']}:{row['event_id']}"
    elif kind == "record":
        identity = f"{row['source']}:{row['event_id']}:{row['record_id']}"
    else:
        raise ValueError(f"Unsupported hash-key kind: {kind}")
    return hashlib.sha256(f"{SALT}:{kind}:{identity}".encode()).hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing = set(COLUMNS) - set(reader.fieldnames or ()) - {"partition", "eligibility_status", "eligibility_reason"}
        if missing:
            raise ValueError(f"Missing required columns: {', '.join(sorted(missing))}")
        return [{key: (value or "").strip() for key, value in row.items()} for row in reader]


def eligibility_errors(row: dict[str, str], *, allow_test_fixtures: bool = False) -> list[str]:
    errors: list[str] = []
    for field in PROVENANCE_FIELDS:
        value = row.get(field, "").strip()
        if not value:
            errors.append(f"blank {field}")
        elif not allow_test_fixtures and any(marker in value.lower() for marker in FORBIDDEN_MARKERS):
            errors.append(f"non-real/placeholder {field}")
    if row.get("component", "").strip().lower() not in {
        "horizontal acceleration", "horizontal_acceleration", "horizontal",
    }:
        errors.append("component is not horizontal acceleration")
    original = row.get("original_units", "").strip().lower()
    normalized = row.get("normalized_units", "").strip().lower()
    if original not in CONVERTIBLE_UNITS:
        errors.append("original units are not deterministically convertible to SI")
    if normalized not in SI_UNITS:
        errors.append("normalized units are not SI acceleration")
    for field, predicate, message in (
        ("sampling_interval_s", lambda x: 0 < x <= 0.020, "sampling interval must be in (0, 0.020] s"),
        ("usable_duration_s", lambda x: x >= 10, "usable duration must be >= 10 s"),
        ("pga_g", lambda x: abs(x) >= 0.15, "absolute PGA must be >= 0.15 g"),
    ):
        try:
            if not predicate(float(row.get(field, ""))):
                errors.append(message)
        except ValueError:
            errors.append(f"invalid numeric {field}")
    for field in ("latitude", "longitude"):
        try:
            float(row.get(field, ""))
        except ValueError:
            errors.append(f"invalid numeric {field}")
    for field in ("raw_sha256", "processed_sha256"):
        value = row.get(field, "").lower()
        if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
            errors.append(f"invalid {field}")
    return errors


def write_manifest(rows: Iterable[dict[str, str]], path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    path.with_suffix(path.suffix + ".sha256").write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    return digest
