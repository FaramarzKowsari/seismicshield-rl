#!/usr/bin/env python3
"""Audit local AFAD/TADAS DYNA ASCII components without extracting raw bytes."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import zipfile

if __package__:
    from scripts.ground_motion_manifest import (
        AFAD_TADAS_SOURCE, CONVERTIBLE_UNITS, STANDARD_GRAVITY_M_S2,
        afad_event_identity, afad_record_id, derive_usable_duration_s,
        is_valid_utc_timestamp, raw_redistribution_allowed, validate_component_pga,
    )
else:
    from ground_motion_manifest import (
        AFAD_TADAS_SOURCE, CONVERTIBLE_UNITS, STANDARD_GRAVITY_M_S2,
        afad_event_identity, afad_record_id, derive_usable_duration_s,
        is_valid_utc_timestamp, raw_redistribution_allowed, validate_component_pga,
    )

DEFAULT_AUDIT_DIR = Path("results/local/afad_tadas/raw_audits")
MIN_PGA_CM_S2 = 0.15 * STANDARD_GRAVITY_M_S2 * 100
_NUMBER = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?$")

# Real AFAD RawAcc ASCII exports observed in TADAS use STATION_CODE and
# STATION_*_DEGREE names. Keep the older aliases for compatibility with
# synthetic fixtures and any legacy exports, but prefer no inferred values.
STATION_ID_HEADERS = ("STATION_ID", "STATION_CODE")
STATION_LATITUDE_HEADERS = ("STATION_LATITUDE", "STATION_LAT", "STATION_LATITUDE_DEGREE")
STATION_LONGITUDE_HEADERS = ("STATION_LONGITUDE", "STATION_LON", "STATION_LONGITUDE_DEGREE")


def parse_dyna_ascii(raw: bytes) -> tuple[dict[str, str], list[float]]:
    """Parse colon headers and the following whitespace/comma-separated series."""
    text = raw.decode("utf-8-sig")
    headers: dict[str, str] = {}
    samples: list[float] = []
    series_started = False
    for source_line in text.splitlines():
        line = source_line.strip()
        if not line:
            continue
        tokens = line.replace(",", " ").split()
        numeric = bool(tokens) and all(_NUMBER.fullmatch(token) for token in tokens)
        if numeric:
            series_started = True
            samples.extend(float(token) for token in tokens)
        elif not series_started and ":" in line:
            key, value = line.split(":", 1)
            headers[key.strip().upper()] = value.strip()
        elif series_started:
            raise ValueError("non-numeric content encountered after acceleration series began")
    if not samples:
        raise ValueError("no numeric acceleration series found")
    return headers, samples


def _header(headers: dict[str, str], *names: str) -> str:
    return next((headers[name] for name in names if headers.get(name, "") != ""), "")


def _utc(headers: dict[str, str]) -> str:
    date, time = _header(headers, "EVENT_DATE_YYYYMMDD"), _header(headers, "EVENT_TIME_HHMMSS")
    if not (re.fullmatch(r"\d{8}", date) and re.fullmatch(r"\d{6}(?:\.\d+)?", time)):
        return ""
    try:
        value = datetime.strptime(date + time[:6], "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return ""
    if "." in time:
        fraction = time.split(".", 1)[1]
        value = value.replace(microsecond=int((fraction + "000000")[:6]))
    return value.isoformat().replace("+00:00", "Z")


def audit_component(raw: bytes, filename: str, event_id: str, waveform_detail_id: str,
                    zip_sha256: str, source_reference: str) -> dict[str, object]:
    headers, samples = parse_dyna_ascii(raw)
    stream = _header(headers, "STREAM", "COMPONENT").upper() or Path(filename).suffix.lstrip(".").upper()
    canonical_event_id, raw_event_id = afad_event_identity(event_id, headers.get("EVENT_ID"))
    checks: dict[str, bool] = {}
    checks["known_canonical_event_id"] = bool(canonical_event_id)
    checks["known_waveform_detail_id"] = bool(waveform_detail_id.strip())
    checks["horizontal_orientation"] = stream in {"HNE", "HNN"}
    units = _header(headers, "UNITS", "ACCELERATION_UNITS", "ORIGINAL_UNITS")
    checks["valid_acceleration_units"] = units.lower() in CONVERTIBLE_UNITS
    try:
        dt = float(_header(headers, "SAMPLING_INTERVAL_S", "SAMPLING_INTERVAL"))
    except ValueError:
        dt = math.nan
    checks["valid_sampling_interval"] = math.isfinite(dt) and 0 < dt <= .020
    try:
        ndata = int(_header(headers, "NDATA"))
    except ValueError:
        ndata = -1
    checks["sample_count_consistency"] = ndata == len(samples)
    duration, derivation = math.nan, "invalid"
    try:
        duration, derivation = derive_usable_duration_s(headers.get("DURATION_S"), ndata, dt, len(samples))
    except (ValueError, OverflowError):
        pass
    checks["usable_duration"] = math.isfinite(duration) and duration >= 10
    parsed_pga = max(abs(value) for value in samples)
    try:
        header_pga = abs(float(_header(headers, "PGA_CM/S^2", "PGA_CM_S2")))
    except ValueError:
        header_pga = math.nan
    checks["component_pga"] = math.isfinite(parsed_pga) and parsed_pga >= MIN_PGA_CM_S2
    try:
        pga_g = validate_component_pga(samples, header_pga)
        checks["pga_header_data_agreement"] = True
    except ValueError:
        pga_g = parsed_pga / (STANDARD_GRAVITY_M_S2 * 100)
        checks["pga_header_data_agreement"] = False
    event_time = _utc(headers)
    checks["valid_utc_event_time"] = bool(event_time) and is_valid_utc_timestamp(event_time)
    license_text = headers.get("DATA_LICENSE", "")
    raw_hash = hashlib.sha256(raw).hexdigest()
    station_id = _header(headers, *STATION_ID_HEADERS)
    checks["required_provenance"] = all((
        station_id, _header(headers, "EVENT_DATE_YYYYMMDD"),
        _header(headers, "EVENT_LATITUDE", "EVENT_LAT"),
        _header(headers, "EVENT_LONGITUDE", "EVENT_LON"), source_reference,
    ))
    checks["raw_sha256"] = bool(re.fullmatch(r"[0-9a-f]{64}", raw_hash))
    checks["license_preservation"] = "DATA_LICENSE" in headers
    reasons = [name for name, passed in checks.items() if not passed]
    record_id = afad_record_id(waveform_detail_id, stream) if stream in {"HNE", "HNN"} else f"{waveform_detail_id.strip()}:{stream}"
    return {
        "source": AFAD_TADAS_SOURCE, "event_id": canonical_event_id,
        "raw_header_event_id": raw_event_id, "waveform_detail_id": waveform_detail_id.strip(),
        "record_id": record_id, "stream": stream, "raw_filename": filename,
        "station_id": station_id,
        "event_date": _header(headers, "EVENT_DATE_YYYYMMDD"), "event_time_utc": event_time,
        "event_latitude": _header(headers, "EVENT_LATITUDE", "EVENT_LAT"),
        "event_longitude": _header(headers, "EVENT_LONGITUDE", "EVENT_LON"),
        "station_latitude": _header(headers, *STATION_LATITUDE_HEADERS),
        "station_longitude": _header(headers, *STATION_LONGITUDE_HEADERS),
        "sampling_interval_s": dt if math.isfinite(dt) else None, "ndata": ndata,
        "parsed_sample_count": len(samples),
        "usable_duration_s": duration if math.isfinite(duration) else None,
        "raw_duration_derivation": derivation,
        "original_units": units, "pga_header_cm_s2": header_pga if math.isfinite(header_pga) else None,
        "pga_parsed_cm_s2": parsed_pga,
        "pga_difference_cm_s2": abs(parsed_pga - header_pga) if math.isfinite(header_pga) else None,
        "pga_g": pga_g,
        "data_license": license_text,
        "raw_redistribution_allowed": raw_redistribution_allowed(license_text),
        "raw_sha256": raw_hash, "zip_sha256": zip_sha256,
        "source_reference": source_reference, "eligibility_checks": checks,
        "eligibility_status": "PASS" if not reasons else "FAIL", "eligibility_reasons": reasons,
    }


def audit_zip(zip_path: Path, event_id: str, waveform_detail_id: str,
              source_reference: str = "") -> dict[str, object]:
    if not event_id.strip():
        raise ValueError("canonical event_id must be a nonblank external input")
    detail = waveform_detail_id.strip()
    if not detail:
        raise ValueError("waveform_detail_id must be a nonblank decimal digit string")
    if not re.fullmatch(r"[0-9]+", detail):
        raise ValueError("waveform_detail_id must be a decimal digit string")
    zip_hash = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    components = []
    with zipfile.ZipFile(zip_path) as archive:
        for info in sorted(archive.infolist(), key=lambda item: item.filename):
            if info.is_dir():
                continue
            raw = archive.read(info)
            filename_looks_like_component = bool(
                re.search(r"(?:^|[_.-])HN[ENZ](?:[_.-]|$)", info.filename, re.IGNORECASE)
            )
            raw_declares_component = bool(re.search(
                rb"(?im)(?:^|\n)(?:\xef\xbb\xbf)?[ \t]*(?:STREAM|COMPONENT)[ \t]*:", raw
            ))
            try:
                headers, _ = parse_dyna_ascii(raw)
            except (UnicodeDecodeError, ValueError) as exc:
                if filename_looks_like_component or raw_declares_component:
                    raise ValueError(f"malformed waveform component {info.filename!r}: {exc}") from exc
                continue
            stream = _header(headers, "STREAM", "COMPONENT").strip().upper()
            if not stream:
                # Legacy extension-only naming remains supported, but metadata wins whenever present.
                stream = Path(info.filename).suffix.lstrip(".").upper()
            if stream in {"HNE", "HNN", "HNZ"}:
                components.append(audit_component(raw, info.filename, event_id, detail,
                                                  zip_hash, source_reference))
            elif raw_declares_component or filename_looks_like_component:
                raise ValueError(
                    f"waveform component {info.filename!r} has unsupported stream {stream!r}"
                )
    if not components:
        raise ValueError("ZIP contains no HNE, HNN, or HNZ DYNA components")
    return {"audit_type": "AFAD_TADAS_LOCAL_RAW_COMPONENT_STAGING_AUDIT",
            "final_manifest": False, "zip_path": str(zip_path), "zip_sha256": zip_hash,
            "components": components}


def write_audit(audit: dict[str, object], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(audit, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip", required=True, type=Path)
    parser.add_argument("--event-id", required=True)
    parser.add_argument("--waveform-detail-id", required=True)
    parser.add_argument("--source-reference", default="")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    audit = audit_zip(args.zip, args.event_id, args.waveform_detail_id, args.source_reference)
    out = args.out or DEFAULT_AUDIT_DIR / f"{args.event_id}_{args.waveform_detail_id}.json"
    write_audit(audit, out)
    print(f"Wrote local staging audit: {out}")


if __name__ == "__main__":
    main()
