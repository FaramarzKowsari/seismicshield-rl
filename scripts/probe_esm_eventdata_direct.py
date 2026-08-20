#!/usr/bin/env python3
"""Validate the direct ESM Dataset-Selection -> Event-Data path on one waveform.

Source-discovery / data-selection infrastructure only. This script deliberately bypasses the
Flatfile service because the public Event-Data service accepts the Dataset Selection identity
(event_id + network + station + location + instrument wildcard) directly and returns a DYNA 1.2
ASCII ZIP.

The probe parses all returned component headers, verifies cross-service identity, reports frozen
component checks (horizontal acceleration, dt <= 0.020 s, duration >= 10 s, |PGA| >= 0.15 g), and
records SHA-256 provenance. It does NOT amend the frozen design, create a final manifest, submit an
OSF registration, or run confirmatory simulations.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import zipfile

DATASET_SELECTION_PROBE = Path("data/private/esm/dataset-selection-probe.json")
DEFAULT_ZIP = Path("data/private/esm/eventdata-direct-probe.zip")
DEFAULT_SUMMARY = Path("data/private/esm/eventdata-direct-probe-summary.json")
EVENTDATA_BASE = "https://esm-db.eu/esmws/eventdata/1/query"
STANDARD_GRAVITY_M_S2 = 9.80665
PGA_THRESHOLD_CM_S2 = 0.15 * STANDARD_GRAVITY_M_S2 * 100.0
PGA_ROUNDTRIP_TOLERANCE_CM_S2 = 0.01


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _records(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [row for row in value if isinstance(row, dict)]
    if isinstance(value, dict):
        for key in ("records", "results", "data", "waveforms", "items"):
            rows = value.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
    return []


def choose_probe_record(parsed: Any) -> dict[str, Any]:
    rows = _records(parsed)
    if not rows:
        raise ValueError("dataset-selection probe contains no records")
    row = rows[0]
    required = ("event_id", "net_name", "station_code", "instr_code", "processing_type")
    missing = [key for key in required if not str(row.get(key, "")).strip()]
    if missing:
        raise ValueError(f"dataset-selection first record missing required keys: {missing}")
    return row


def normalize_processing(value: Any) -> str:
    processing = str(value or "").strip().upper()
    if processing not in {"CV", "MP", "AP", "MB"}:
        raise ValueError(f"unsupported or missing ESM processing type: {value!r}")
    return processing


def normalize_location(value: Any) -> str:
    location = str(value or "").strip()
    return location if location else "--"


def normalize_instrument_pattern(value: Any) -> str:
    instrument = str(value or "").strip().upper()
    if len(instrument) < 2:
        raise ValueError(f"invalid ESM instrument code: {value!r}")
    family = instrument[:2]
    if family not in {"HN", "HG", "HL"}:
        raise ValueError(f"non-accelerometric ESM instrument family: {value!r}")
    # Dataset Selection commonly returns HN*. Preserve a supplied wildcard because Event-Data
    # explicitly supports wildcard channel matching; add one only for a bare two-letter family.
    return instrument if len(instrument) > 2 else family + "*"


def build_eventdata_url(row: dict[str, Any]) -> str:
    query = {
        "eventid": str(row["event_id"]),
        "catalog": "ESM",
        "network": str(row["net_name"]),
        "station": str(row["station_code"]),
        "location": normalize_location(row.get("location_code")),
        "channel": normalize_instrument_pattern(row.get("instr_code")),
        "format": "ascii",
        "processing-type": normalize_processing(row.get("processing_type")),
        "data-type": "ACC",
        "quality-class": "BEST,GOOD",
    }
    return EVENTDATA_BASE + "?" + urlencode(query)


def fetch_bytes(url: str, timeout_s: float) -> tuple[int, str, bytes]:
    request = Request(url, headers={"User-Agent": "SeismicShield-RL/0.8 ESM direct Event-Data probe"})
    try:
        with urlopen(request, timeout=timeout_s) as response:  # noqa: S310 - fixed HTTPS ESM service
            body = response.read()
            status = int(getattr(response, "status", response.getcode()))
            content_type = response.headers.get("Content-Type", "")
        return status, content_type, body
    except HTTPError as exc:
        excerpt = exc.read(1200).decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} for {url}; ESM response: {excerpt}") from exc


def parse_header(text: str) -> dict[str, str]:
    header: dict[str, str] = {}
    for line in text.splitlines()[:180]:
        stripped = line.strip()
        if not stripped or ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        key = key.strip().upper()
        if key and len(key) <= 100:
            header[key] = value.strip()
    return header


def _float(header: dict[str, str], key: str) -> float | None:
    raw = header.get(key, "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _int(header: dict[str, str], key: str) -> int | None:
    raw = header.get(key, "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def is_horizontal(stream: str) -> bool:
    stream = stream.strip().upper()
    return bool(stream) and stream[-1:] in {"E", "N", "1", "2", "X", "Y"}


def inspect_ascii_zip(body: bytes, row: dict[str, Any]) -> dict[str, Any]:
    expected_event = str(row["event_id"]).strip()
    expected_network = str(row["net_name"]).strip()
    expected_station = str(row["station_code"]).strip()
    expected_location = normalize_location(row.get("location_code"))
    components: list[dict[str, Any]] = []

    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        names = [name for name in archive.namelist() if not name.endswith("/")]
        if not names:
            raise ValueError("ESM Event-Data ZIP contains no files")
        for name in names:
            text = archive.read(name).decode("utf-8-sig", errors="replace")
            header = parse_header(text)
            stream = header.get("STREAM", "").upper()
            units = header.get("UNITS", "")
            dt = _float(header, "SAMPLING_INTERVAL_S")
            ndata = _int(header, "NDATA")
            duration = _float(header, "DURATION_S")
            pga = _float(header, "PGA_CM/S^2")
            if pga is None:
                pga = _float(header, "PGA_CM_S2")
            if duration is None and dt is not None and ndata is not None and ndata >= 1:
                duration = (ndata - 1) * dt

            identity_ok = (
                header.get("EVENT_ID", "").strip() == expected_event
                and header.get("NETWORK", "").strip() == expected_network
                and header.get("STATION_CODE", "").strip() == expected_station
                and header.get("LOCATION", "").strip() == expected_location
            )
            checks = {
                "identity": identity_ok,
                "horizontal_orientation": is_horizontal(stream),
                "acceleration_units": units.strip().lower().replace(" ", "") in {"cm/s^2", "cm/s2"},
                "sampling_interval": dt is not None and dt <= 0.020,
                "usable_duration": duration is not None and duration >= 10.0,
                "component_pga": pga is not None and abs(pga) >= PGA_THRESHOLD_CM_S2,
                "required_provenance": bool(
                    header.get("EVENT_ID", "").strip()
                    and header.get("STATION_CODE", "").strip()
                    and header.get("DATA_LICENSE", "").strip()
                    and header.get("DATA_CITATION", "").strip()
                ),
            }
            component_pass = all(checks.values())
            components.append(
                {
                    "file_name": name,
                    "stream": stream,
                    "event_id": header.get("EVENT_ID"),
                    "network": header.get("NETWORK"),
                    "station_code": header.get("STATION_CODE"),
                    "location": header.get("LOCATION"),
                    "sampling_interval_s": dt,
                    "ndata": ndata,
                    "usable_duration_s": duration,
                    "units": units,
                    "pga_cm_s2": pga,
                    "data_license": header.get("DATA_LICENSE"),
                    "data_citation": header.get("DATA_CITATION"),
                    "checks": checks,
                    "component_pass": component_pass,
                }
            )

    horizontals = [c for c in components if is_horizontal(str(c["stream"]))]
    horizontal_pgas = [float(c["pga_cm_s2"]) for c in horizontals if c["pga_cm_s2"] is not None]
    max_horizontal_pga = max(horizontal_pgas) if horizontal_pgas else None
    returned_corr = row.get("corr_hz_PGA")
    returned_corr_float: float | None = None
    try:
        if returned_corr is not None and str(returned_corr).strip():
            returned_corr_float = float(returned_corr)
    except (TypeError, ValueError):
        returned_corr_float = None
    roundtrip_diff = (
        abs(max_horizontal_pga - returned_corr_float)
        if max_horizontal_pga is not None and returned_corr_float is not None
        else None
    )

    return {
        "file_count": len(components),
        "components": components,
        "horizontal_count": len(horizontals),
        "passing_horizontal_count": sum(1 for c in components if c["component_pass"]),
        "max_horizontal_header_pga_cm_s2": max_horizontal_pga,
        "dataset_selection_corr_hz_PGA_as_returned": returned_corr,
        "dataset_selection_to_header_abs_diff": roundtrip_diff,
        "dataset_selection_to_header_within_0p01": (
            roundtrip_diff is not None and roundtrip_diff <= PGA_ROUNDTRIP_TOLERANCE_CM_S2
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection-probe", type=Path, default=DATASET_SELECTION_PROBE)
    parser.add_argument("--zip-out", type=Path, default=DEFAULT_ZIP)
    parser.add_argument("--summary-out", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--timeout-s", type=float, default=90.0)
    args = parser.parse_args()
    if args.timeout_s <= 0:
        parser.error("--timeout-s must be > 0")
    if not args.selection_probe.exists():
        parser.error(f"dataset-selection probe not found: {args.selection_probe}")

    parsed = json.loads(args.selection_probe.read_text(encoding="utf-8"))
    row = choose_probe_record(parsed)
    url = build_eventdata_url(row)
    status, content_type, body = fetch_bytes(url, args.timeout_s)
    if status != 200:
        raise RuntimeError(f"ESM Event-Data returned HTTP {status}")
    if not zipfile.is_zipfile(io.BytesIO(body)):
        raise RuntimeError("ESM Event-Data response is not a ZIP archive")

    inspection = inspect_ascii_zip(body, row)
    args.zip_out.parent.mkdir(parents=True, exist_ok=True)
    args.zip_out.write_bytes(body)
    summary = {
        "probe_type": "ESM_DIRECT_EVENTDATA_COMPONENT_AUDIT_SOURCE_DISCOVERY_ONLY",
        "final_manifest": False,
        "fetched_at_utc": _now_utc(),
        "request_url": url,
        "http_status": status,
        "content_type": content_type,
        "sha256": hashlib.sha256(body).hexdigest(),
        "bytes": len(body),
        "dataset_selection_identity": {
            "event_id": row.get("event_id"),
            "network": row.get("net_name"),
            "station": row.get("station_code"),
            "location": row.get("location_code"),
            "instrument": row.get("instr_code"),
            "processing_type": normalize_processing(row.get("processing_type")),
            "quality_class": row.get("class"),
        },
        "frozen_component_thresholds_reported_only": {
            "pga_min_cm_s2": PGA_THRESHOLD_CM_S2,
            "dt_max_s": 0.020,
            "duration_min_s": 10.0,
        },
        **inspection,
        "notes": [
            "Direct Event-Data access is validated without relying on the ESM Flatfile service.",
            "Dataset Selection corr_hz_PGA is only round-trip compared with authoritative ASCII header PGA; it is not silently assumed to have units.",
            "No second-source ordering, cross-source deduplication, final manifest, OSF registration, or confirmatory result is produced.",
        ],
    }
    args.summary_out.parent.mkdir(parents=True, exist_ok=True)
    args.summary_out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"Dataset-selection identity: {row['event_id']} {row['net_name']}.{row['station_code']}.{row.get('location_code','')}.{row['instr_code']}")
    print(f"ESM Event-Data HTTP {status}; ZIP files={inspection['file_count']}; bytes={len(body)}")
    for component in inspection["components"]:
        failed = [name for name, ok in component["checks"].items() if not ok]
        print(
            f"  {component['stream'] or '?'} dt={component['sampling_interval_s']} "
            f"duration={component['usable_duration_s']} PGA={component['pga_cm_s2']} "
            f"pass={component['component_pass']} failed={failed or '-'}"
        )
    print(f"Passing horizontals: {inspection['passing_horizontal_count']}")
    print(
        "Dataset-selection corr_hz_PGA round-trip: "
        f"returned={inspection['dataset_selection_corr_hz_PGA_as_returned']} "
        f"header_max={inspection['max_horizontal_header_pga_cm_s2']} "
        f"diff={inspection['dataset_selection_to_header_abs_diff']}"
    )
    print(f"Wrote private Event-Data ZIP: {args.zip_out}")
    print(f"Wrote private probe summary: {args.summary_out}")
    print("No final manifest or confirmatory result was produced.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
