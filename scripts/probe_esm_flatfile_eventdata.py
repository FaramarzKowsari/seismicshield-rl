#!/usr/bin/env python3
"""Probe ESM flatfile metadata and public ASCII event-data for one selected waveform.

Source-discovery/provenance infrastructure only. This script reads the private output of
``probe_esm_dataset_selection.py``, chooses one returned waveform deterministically (the first
record in the probe response), then queries two documented public ESM services:

* Flatfile Web-Service, to inspect authoritative engineering metadata and intensity-measure fields;
* Event-Data Web-Service, to download the matching processed acceleration waveform as a DYNA 1.2
  ASCII ZIP and inspect its header shape.

It does not change the frozen 40-event/160-record design, does not create a final manifest, and
does not run confirmatory simulations. Returned bytes remain under ``data/private``.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import zipfile

DATASET_SELECTION_PROBE = Path("data/private/esm/dataset-selection-probe.json")
DEFAULT_FLATFILE = Path("data/private/esm/flatfile-probe.csv")
DEFAULT_EVENTDATA = Path("data/private/esm/eventdata-probe.zip")
DEFAULT_SUMMARY = Path("data/private/esm/flatfile-eventdata-probe-summary.json")

FLATFILE_BASE = "https://esm-db.eu/esmws/flatfile/1/query"
EVENTDATA_BASE = "https://esm-db.eu/esmws/eventdata/1/query"
SENSITIVE_TOKENS = ("authorization", "cookie", "csrf", "xsrf", "token", "password", "secret")


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
    required = ("event_id", "net_name", "station_code", "instr_code")
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


def build_flatfile_url(row: dict[str, Any]) -> str:
    query = {
        "eventid": str(row["event_id"]),
        "network": str(row["net_name"]),
        "station": str(row["station_code"]),
        "channel": str(row["instr_code"]),
        "unprocessed": "N",
        "discarded": "N",
        "processing-type": normalize_processing(row.get("processing_type")),
        "quality-class": "BEST,GOOD",
        "output-format": "csv",
        "contains-string": "False",
    }
    return FLATFILE_BASE + "?" + urlencode(query)


def build_eventdata_url(row: dict[str, Any]) -> str:
    query = {
        "eventid": str(row["event_id"]),
        "catalog": "ESM",
        "network": str(row["net_name"]),
        "station": str(row["station_code"]),
        "location": normalize_location(row.get("location_code")),
        "channel": str(row["instr_code"]),
        "format": "ascii",
        "processing-type": normalize_processing(row.get("processing_type")),
        "data-type": "ACC",
        "quality-class": "BEST,GOOD",
    }
    return EVENTDATA_BASE + "?" + urlencode(query)


def fetch_bytes(url: str, timeout_s: float) -> tuple[int, str, bytes]:
    req = Request(url, headers={"User-Agent": "SeismicShield-RL/0.8 ESM source probe"})
    with urlopen(req, timeout=timeout_s) as response:  # noqa: S310 - fixed HTTPS ESM services
        body = response.read()
        status = int(getattr(response, "status", response.getcode()))
        content_type = response.headers.get("Content-Type", "")
    return status, content_type, body


def parse_flatfile(body: bytes) -> tuple[list[str], dict[str, str]]:
    text = body.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    rows = list(reader)
    if not reader.fieldnames:
        raise ValueError("ESM flatfile response has no CSV header")
    if not rows:
        raise ValueError("ESM flatfile response has no data rows")
    return list(reader.fieldnames), dict(rows[0])


def inspect_ascii_zip(body: bytes) -> dict[str, Any]:
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        names = archive.namelist()
        if not names:
            raise ValueError("ESM event-data ZIP is empty")
        ascii_names = [name for name in names if not name.endswith("/")]
        if not ascii_names:
            raise ValueError("ESM event-data ZIP contains no files")
        header_keys: set[str] = set()
        previews: dict[str, list[str]] = {}
        for name in ascii_names[:12]:
            raw = archive.read(name)
            text = raw.decode("utf-8-sig", errors="replace")
            lines = text.splitlines()
            header_lines: list[str] = []
            for line in lines[:120]:
                stripped = line.strip()
                if not stripped:
                    continue
                if ":" in stripped:
                    key = stripped.split(":", 1)[0].strip()
                    if key and len(key) <= 80:
                        header_keys.add(key)
                        header_lines.append(stripped[:240])
            previews[name] = header_lines[:30]
        return {
            "file_count": len(ascii_names),
            "file_names": ascii_names[:50],
            "header_keys": sorted(header_keys),
            "header_previews": previews,
        }


def _redacted_preview(row: dict[str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key in sorted(row)[:80]:
        if any(token in key.lower() for token in SENSITIVE_TOKENS):
            out[key] = "<redacted>"
        else:
            out[key] = row[key]
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection-probe", type=Path, default=DATASET_SELECTION_PROBE)
    parser.add_argument("--flatfile-out", type=Path, default=DEFAULT_FLATFILE)
    parser.add_argument("--eventdata-out", type=Path, default=DEFAULT_EVENTDATA)
    parser.add_argument("--summary-out", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--timeout-s", type=float, default=90.0)
    args = parser.parse_args()
    if args.timeout_s <= 0:
        parser.error("--timeout-s must be > 0")
    if not args.selection_probe.exists():
        parser.error(f"dataset-selection probe not found: {args.selection_probe}")

    parsed = json.loads(args.selection_probe.read_text(encoding="utf-8"))
    row = choose_probe_record(parsed)
    flat_url = build_flatfile_url(row)
    event_url = build_eventdata_url(row)

    flat_status, flat_type, flat_body = fetch_bytes(flat_url, args.timeout_s)
    if flat_status != 200:
        raise RuntimeError(f"ESM flatfile returned HTTP {flat_status}")
    fields, first_flat_row = parse_flatfile(flat_body)

    event_status, event_type, event_body = fetch_bytes(event_url, args.timeout_s)
    if event_status != 200:
        raise RuntimeError(f"ESM event-data returned HTTP {event_status}")
    if not zipfile.is_zipfile(io.BytesIO(event_body)):
        raise RuntimeError("ESM event-data ASCII response is not a ZIP archive")
    zip_info = inspect_ascii_zip(event_body)

    args.flatfile_out.parent.mkdir(parents=True, exist_ok=True)
    args.flatfile_out.write_bytes(flat_body)
    args.eventdata_out.parent.mkdir(parents=True, exist_ok=True)
    args.eventdata_out.write_bytes(event_body)

    summary = {
        "probe_type": "ESM_FLATFILE_EVENTDATA_SOURCE_DISCOVERY_ONLY",
        "final_manifest": False,
        "fetched_at_utc": _now_utc(),
        "dataset_selection_identity": {
            "event_id": row.get("event_id"),
            "network": row.get("net_name"),
            "station": row.get("station_code"),
            "location": row.get("location_code"),
            "instrument": row.get("instr_code"),
            "processing_type": normalize_processing(row.get("processing_type")),
            "quality_class": row.get("class"),
            "corr_hz_PGA_as_returned": row.get("corr_hz_PGA"),
            "uncorr_PGA_as_returned": row.get("uncorr_PGA"),
        },
        "flatfile": {
            "request_url": flat_url,
            "http_status": flat_status,
            "content_type": flat_type,
            "sha256": hashlib.sha256(flat_body).hexdigest(),
            "bytes": len(flat_body),
            "field_count": len(fields),
            "fields": fields,
            "first_row_preview": _redacted_preview(first_flat_row),
        },
        "eventdata": {
            "request_url": event_url,
            "http_status": event_status,
            "content_type": event_type,
            "sha256": hashlib.sha256(event_body).hexdigest(),
            "bytes": len(event_body),
            **zip_info,
        },
        "notes": [
            "Dataset-selection corr_hz_PGA/uncorr_PGA units are not assumed by this probe.",
            "Flatfile/Event-Data metadata and ASCII headers are inspected before any second-source design amendment.",
            "No final source ordering, event selection, manifest, OSF registration, or confirmatory result is produced.",
        ],
    }
    args.summary_out.parent.mkdir(parents=True, exist_ok=True)
    args.summary_out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"Probe identity: {row['event_id']} {row['net_name']}.{row['station_code']}.{row.get('location_code','')}.{row['instr_code']}")
    print(f"ESM flatfile HTTP {flat_status}; fields={len(fields)}; bytes={len(flat_body)}")
    print(f"ESM event-data HTTP {event_status}; ZIP files={zip_info['file_count']}; bytes={len(event_body)}")
    print(f"ASCII header keys: {zip_info['header_keys'] or '-'}")
    print(f"Wrote private flatfile: {args.flatfile_out}")
    print(f"Wrote private event-data ZIP: {args.eventdata_out}")
    print(f"Wrote private probe summary: {args.summary_out}")
    print("No final manifest or confirmatory result was produced.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
