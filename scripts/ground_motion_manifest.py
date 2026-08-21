"""Pure contract helpers for the preregistered real ground-motion manifest."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
import math
from pathlib import Path, PurePosixPath
import re
from typing import Iterable
from urllib.parse import urlsplit

SALT = "SeismicShield-RL-v0.8.0-OSF-2026"
AFAD_TADAS_SOURCE = "AFAD_TADAS"
ESM_SOURCE = "ESM"
STANDARD_GRAVITY_M_S2 = 9.80665
PGA_TOLERANCE_CM_S2 = 0.01
PARTITIONS = (("training", 18), ("validation", 6), ("pilot", 4), ("confirmatory", 12))
ESM_ACCELEROMETRIC_FAMILIES = frozenset({"HN", "HG", "HL"})
ESM_HORIZONTAL_AXIS_SUFFIXES = frozenset({"E", "N", "1", "2", "X", "Y"})
COLUMNS = (
    "source", "event_id", "raw_header_event_id", "record_id",
    "waveform_detail_id", "stream", "raw_filename", "network_code", "station_id", "location_code",
    "component", "sampling_interval_s", "usable_duration_s", "original_units", "normalized_units",
    "ndata", "parsed_sample_count", "raw_duration_derivation", "pga_cm_s2", "source_header_pga_cm_s2",
    "pga_g", "event_date", "event_time_utc", "latitude", "longitude", "partition",
    "source_url_or_access_reference", "preprocessing_status", "source_processing_type", "source_quality_class",
    "raw_sha256", "processed_sha256", "data_license", "data_citation", "raw_redistribution_allowed",
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


def esm_record_id(source_member_basename: str) -> str:
    """Return the frozen ESM record identity: exact source-distributed ASCII basename."""
    text = str(source_member_basename).strip()
    if not text:
        raise ValueError("blank ESM source member basename")
    normalized = text.replace("\\", "/")
    basename = PurePosixPath(normalized).name
    if basename != text or "/" in text or "\\" in text or basename in {".", ".."}:
        raise ValueError("ESM raw_filename must be an exact basename without path components")
    return basename


def esm_horizontal_stream(stream: str) -> bool:
    """Return whether stream is a frozen eligible ESM accelerometric horizontal channel."""
    value = str(stream).strip().upper()
    return (
        len(value) == 3
        and value[:2] in ESM_ACCELEROMETRIC_FAMILIES
        and value[-1] in ESM_HORIZONTAL_AXIS_SUFFIXES
    )


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
        return duration, "explicit:DURATION_S"
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
    """Allow AFAD raw bytes only for a license explicitly frozen in the allowlist."""
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


def _esm_manifest_errors(row: dict[str, str]) -> list[str]:
    errors: list[str] = []
    event_id = row.get("event_id", "").strip()
    raw_event_id = row.get("raw_header_event_id", "").strip()
    if not event_id:
        errors.append("blank canonical ESM event_id")
    if not raw_event_id:
        errors.append("blank ESM ASCII EVENT_ID")
    elif event_id and raw_event_id != event_id:
        errors.append("ESM event_id does not match ASCII EVENT_ID")

    if row.get("waveform_detail_id", "").strip():
        errors.append("ESM row must not contain AFAD waveform_detail_id")
    try:
        expected_record_id = esm_record_id(row.get("raw_filename", ""))
        if row.get("record_id", "").strip() != expected_record_id:
            errors.append("ESM record_id is not the exact source-distributed ASCII basename")
    except ValueError as exc:
        errors.append(str(exc))

    stream = row.get("stream", "").strip().upper()
    if not esm_horizontal_stream(stream):
        errors.append("ESM stream is not an eligible HN/HG/HL horizontal channel")

    for field in ("network_code", "station_id", "source_processing_type", "source_quality_class", "data_citation"):
        if not row.get(field, "").strip():
            errors.append(f"blank {field}")
    quality = row.get("source_quality_class", "").strip().upper()
    if quality and quality not in {"BEST", "GOOD", "BAD", "UNDEF"}:
        errors.append("invalid ESM source_quality_class")

    if row.get("original_units", "").strip().lower() not in {"cm/s^2", "cm/s2"}:
        errors.append("ESM original_units must preserve authoritative cm/s^2 acceleration units")

    try:
        ndata = int(row.get("ndata", ""))
        parsed_count = int(row.get("parsed_sample_count", ""))
        if ndata < 2:
            errors.append("ESM NDATA must be >= 2")
        if parsed_count != ndata:
            errors.append("ESM parsed_sample_count does not equal NDATA")
    except ValueError:
        errors.append("invalid ESM NDATA/parsed_sample_count")
        ndata = 0

    try:
        parsed_pga = abs(float(row.get("pga_cm_s2", "")))
        header_pga = abs(float(row.get("source_header_pga_cm_s2", "")))
        if not math.isfinite(parsed_pga) or not math.isfinite(header_pga):
            raise ValueError
        difference = abs(parsed_pga - header_pga)
        if difference > PGA_TOLERANCE_CM_S2 and not math.isclose(
            difference, PGA_TOLERANCE_CM_S2, abs_tol=1e-12
        ):
            errors.append("ESM parsed PGA disagrees with source header by more than 0.01 cm/s^2")
        expected_g = parsed_pga / (STANDARD_GRAVITY_M_S2 * 100.0)
        actual_g = abs(float(row.get("pga_g", "")))
        if not math.isclose(actual_g, expected_g, rel_tol=1e-9, abs_tol=1e-9):
            errors.append("ESM pga_g is inconsistent with parsed pga_cm_s2 and standard gravity")
    except ValueError:
        errors.append("invalid ESM parsed/header PGA evidence")

    derivation = row.get("raw_duration_derivation", "").strip()
    if derivation == "explicit:DURATION_S":
        try:
            actual_duration = float(row.get("usable_duration_s", ""))
            if not math.isfinite(actual_duration) or actual_duration <= 0:
                raise ValueError
        except ValueError:
            errors.append("invalid ESM explicit DURATION_S evidence")
    elif derivation == "(NDATA - 1) * SAMPLING_INTERVAL_S":
        try:
            parsed_count = int(row.get("parsed_sample_count", ""))
            sampling_interval = float(row.get("sampling_interval_s", ""))
            actual_duration = float(row.get("usable_duration_s", ""))
            if ndata < 2 or parsed_count != ndata:
                raise ValueError
            if not math.isfinite(sampling_interval) or sampling_interval <= 0:
                raise ValueError
            expected_duration = (ndata - 1) * sampling_interval
            if not math.isfinite(actual_duration):
                raise ValueError
            if not math.isclose(actual_duration, expected_duration, rel_tol=1e-9, abs_tol=1e-9):
                errors.append("ESM fallback usable_duration_s is inconsistent with NDATA and sampling interval")
        except ValueError:
            errors.append("invalid ESM duration fallback evidence")
    elif not derivation:
        errors.append("blank raw_duration_derivation")
    else:
        errors.append("unsupported ESM raw_duration_derivation")

    timestamp = row.get("event_time_utc", "")
    if not is_valid_utc_timestamp(timestamp):
        errors.append("ESM event_time_utc is not a valid ISO-8601 UTC timestamp")
    elif row.get("event_date", "").strip() != timestamp[:10]:
        errors.append("ESM event_date does not match event_time_utc date")

    try:
        source_url = urlsplit(row.get("source_url_or_access_reference", ""))
        raw_path = source_url.path
        valid_source_url = (
            source_url.scheme == "https"
            and source_url.hostname == "esm-db.eu"
            and source_url.username is None
            and source_url.password is None
            and source_url.port is None
            and "%" not in raw_path
            and raw_path == "/esmws/eventdata/1/query"
        )
    except ValueError:
        valid_source_url = False
    if not valid_source_url:
        errors.append("ESM source_url_or_access_reference is not an Event-Data service reference")
    if row.get("raw_redistribution_allowed", "").strip().lower() != "false":
        errors.append("ESM raw redistribution must remain false without explicit license permission")
    return errors


def eligibility_errors(row: dict[str, str], *, allow_test_fixtures: bool = False) -> list[str]:
    errors: list[str] = []
    source = row.get("source", "").strip()
    is_afad = source == AFAD_TADAS_SOURCE
    is_esm = source == ESM_SOURCE
    if row.get("waveform_detail_id", "").strip() and not is_afad:
        errors.append("AFAD/TADAS waveform_detail_id requires exact canonical source AFAD_TADAS")
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
    elif is_esm:
        errors.extend(_esm_manifest_errors(row))

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
