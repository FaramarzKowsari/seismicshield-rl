"""Pure contract helpers for the preregistered real ground-motion manifest."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
import math
from pathlib import Path
import re
from typing import Iterable

SALT = "SeismicShield-RL-v0.8.0-OSF-2026"
AFAD_TADAS_SOURCE = "AFAD_TADAS"
STANDARD_GRAVITY_M_S2 = 9.80665
PGA_TOLERANCE_CM_S2 = 0.01
PARTITIONS = (("training", 18), ("validation", 6), ("pilot", 4), ("confirmatory", 12))
COLUMNS = (
    "source", "event_id", "raw_header_event_id", "record_id",
    "waveform_detail_id", "stream", "raw_filename", "station_id", "component",
    "sampling_interval_s", "usable_duration_s", "original_units", "normalized_units",
    "ndata", "raw_duration_derivation", "pga_cm_s2", "pga_g", "event_date",
    "event_time_utc", "latitude", "longitude", "partition",
    "source_url_or_access_reference", "preprocessing_status", "raw_sha256",
    "processed_sha256", "data_license", "raw_redistribution_allowed",
    "eligibility_status", "eligibility_reason",
)
PROVENANCE_FIELDS = (
    "source", "event_id", "record_id", "station_id", "event_date", "event_time_utc", "latitude",
    "longitude", "source_url_or_access_reference", "preprocessing_status", "raw_sha256",
    "processed_sha256", "data_license",
)
FORBIDDEN_MARKERS = ("fake", "placeholder", "synthetic", "dummy", "fixture", "example.com", "unknown")
SI_UNITS = {"m/s^2", "m/s2", "m s-2"}
CONVERTIBLE_UNITS = SI_UNITS | {"g", "gal", "cm/s^2", "cm/s2"}
AFAD_RAW_REDISTRIBUTION_LICENSE_ALLOWLIST: frozenset[str] = frozenset()
UTC_TIMESTAMP_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|\+00:00)$"
)


def afad_record_id(waveform_detail_id: str, stream: str) -> str:
    """Return the frozen TADAS component identity, rejecting non-horizontal streams."""
    detail = str(waveform_detail_id).strip()
    stream = str(stream).strip().upper()
    if not detail:
        raise ValueError("blank waveform_detail_id")
    if not re.fullmatch(r"[0-9]+", detail):
        raise ValueError("waveform_detail_id must be a decimal digit string")
    if stream not in {"HNE", "HNN"}:
        raise ValueError(f"AFAD/TADAS stream {stream!r} is not an eligible horizontal stream")
    return f"{detail}:{stream}"


def afad_event_identity(tadas_event_id: str | int, raw_header_event_id: str | int | None) -> tuple[str, str]:
    """Use Event Search/Detail identity while retaining, but never trusting, the raw header."""
    canonical = str(tadas_event_id).strip()
    if not canonical:
        raise ValueError("blank TADAS Event Search/Event Detail identifier")
    raw = "" if raw_header_event_id is None else str(raw_header_event_id).strip()
    return canonical, raw


def derive_usable_duration_s(
    explicit_duration: str | float | None,
    ndata: int | str,
    sampling_interval_s: float | str,
    parsed_sample_count: int,
) -> tuple[float, str]:
    """Preserve a trustworthy duration or derive it from a fully parsed raw series."""
    if explicit_duration is not None and str(explicit_duration).strip():
        duration = float(explicit_duration)
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError("explicit usable duration is invalid")
        return duration, "explicit"
    count, dt = int(ndata), float(sampling_interval_s)
    if count < 2 or parsed_sample_count != count:
        raise ValueError("cannot derive duration: NDATA/sample-count contract failed")
    if not math.isfinite(dt) or dt <= 0:
        raise ValueError("cannot derive duration: sampling interval must be finite and > 0")
    return (count - 1) * dt, "(NDATA - 1) * SAMPLING_INTERVAL_S"


def validate_component_pga(samples_cm_s2: Iterable[float], header_pga_cm_s2: float | str) -> float:
    """Validate raw component PGA and return its derived value in standard gravity."""
    samples = [float(value) for value in samples_cm_s2]
    if not samples or not all(math.isfinite(value) for value in samples):
        raise ValueError("raw acceleration samples must be nonempty and finite")
    parsed_pga = max(abs(value) for value in samples)
    header_pga = abs(float(header_pga_cm_s2))
    difference = abs(parsed_pga - header_pga)
    if not math.isfinite(header_pga) or (
        difference > PGA_TOLERANCE_CM_S2
        and not math.isclose(difference, PGA_TOLERANCE_CM_S2, abs_tol=1e-12)
    ):
        raise ValueError("parsed PGA disagrees with PGA_CM/S^2 by more than 0.01 cm/s^2")
    return header_pga / (STANDARD_GRAVITY_M_S2 * 100.0)


def raw_redistribution_allowed(data_license: str | None) -> bool:
    """Allow raw bytes only for a license explicitly frozen in the allowlist."""
    license_text = "" if data_license is None else str(data_license).strip()
    return license_text in AFAD_RAW_REDISTRIBUTION_LICENSE_ALLOWLIST


def is_valid_utc_timestamp(value: str) -> bool:
    """Return whether value is a real ISO-8601 timestamp explicitly representing UTC."""
    if not UTC_TIMESTAMP_PATTERN.fullmatch(value):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() == timezone.utc.utcoffset(parsed)


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
    is_afad = row.get("source") == AFAD_TADAS_SOURCE
    if (row.get("waveform_detail_id", "").strip() or row.get("stream", "").strip()) and not is_afad:
        errors.append("AFAD/TADAS metadata requires exact canonical source AFAD_TADAS")
    if is_afad:
        for field in ("waveform_detail_id", "stream", "raw_filename", "ndata", "raw_duration_derivation", "pga_cm_s2"):
            if not row.get(field, "").strip():
                errors.append(f"blank {field}")
        try:
            expected_record_id = afad_record_id(row.get("waveform_detail_id", ""), row.get("stream", ""))
            if row.get("record_id") != expected_record_id:
                errors.append("AFAD/TADAS record_id is not waveform_detail_id:stream")
        except ValueError as exc:
            errors.append(str(exc))
        if not row.get("event_id", "").strip():
            errors.append("blank canonical TADAS event_id")
        if not is_valid_utc_timestamp(row.get("event_time_utc", "")):
            errors.append("AFAD/TADAS event_time_utc is not a valid ISO-8601 UTC timestamp")
        if row.get("raw_redistribution_allowed", "").lower() != "false":
            errors.append("AFAD/TADAS raw redistribution is not explicitly licensed")
    for field in PROVENANCE_FIELDS:
        value = row.get(field, "").strip()
        if not value:
            errors.append(f"blank {field}")
        elif (
            not allow_test_fixtures
            and not (
                is_afad
                and field == "data_license"
                and value == "U (unknown license)"
            )
            and any(marker in value.lower() for marker in FORBIDDEN_MARKERS)
        ):
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
