#!/usr/bin/env python3
"""Robust ESM Flatfile/Event-Data probe using Dataset Selection identity crosswalk.

Source-discovery/provenance infrastructure only. Dataset Selection ``event_id`` values are treated
as legacy/source identifiers, not assumed to be ESM Flatfile ``eventid`` identifiers. The Flatfile
query is therefore anchored by event time, network, station and normalized two-letter channel code.
The authoritative ``ESM_event_id`` returned by Flatfile is then used for Event-Data.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timedelta, timezone
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
DEFAULT_FLATFILE = Path("data/private/esm/flatfile-probe.csv")
DEFAULT_EVENTDATA = Path("data/private/esm/eventdata-probe.zip")
DEFAULT_SUMMARY = Path("data/private/esm/flatfile-eventdata-probe-summary.json")
FLATFILE_BASE = "https://esm-db.eu/esmws/flatfile/1/query"
EVENTDATA_BASE = "https://esm-db.eu/esmws/eventdata/1/query"
VALID_FLATFILE_CHANNELS = {"HN", "HG", "HL", "EH", "HH"}


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
    required = ("event_id", "event_time", "net_name", "station_code", "instr_code")
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


def normalize_flatfile_channel(value: Any) -> str:
    raw = str(value or "").strip().upper()
    candidate = raw[:2]
    if candidate not in VALID_FLATFILE_CHANNELS:
        raise ValueError(f"unsupported ESM Flatfile channel family: {value!r}")
    return candidate


def parse_event_time(value: Any) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise ValueError("missing Dataset Selection event_time")
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def build_flatfile_url(row: dict[str, Any], pad_seconds: int = 60) -> str:
    if pad_seconds < 0:
        raise ValueError("pad_seconds must be >= 0")
    event_time = parse_event_time(row["event_time"])
    start = (event_time - timedelta(seconds=pad_seconds)).strftime("%Y-%m-%dT%H:%M:%S")
    end = (event_time + timedelta(seconds=pad_seconds)).strftime("%Y-%m-%dT%H:%M:%S")
    query = {
        "starttime": start,
        "endtime": end,
        "network": str(row["net_name"]),
        "station": str(row["station_code"]),
        "channel": normalize_flatfile_channel(row["instr_code"]),
        "unprocessed": "N",
        "discarded": "N",
        "processing-type": normalize_processing(row.get("processing_type")),
        "quality-class": "BEST,GOOD",
        "output-format": "csv",
        "contains-string": "False",
    }
    return FLATFILE_BASE + "?" + urlencode(query)


def build_eventdata_url(row: dict[str, Any], esm_event_id: str) -> str:
    if not str(esm_event_id).strip():
        raise ValueError("authoritative ESM_event_id is required")
    query = {
        "eventid": str(esm_event_id).strip(),
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
    try:
        with urlopen(req, timeout=timeout_s) as response:
            body = response.read()
            status = int(getattr(response, "status", response.getcode()))
            content_type = response.headers.get("Content-Type", "")
        return status, content_type, body
    except HTTPError as exc:
        body = exc.read()
        excerpt = body.decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"HTTP {exc.code} for {url}\nESM response: {excerpt}") from exc


def parse_flatfile(body: bytes) -> tuple[list[str], list[dict[str, str]]]:
    text = body.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    rows = [dict(row) for row in reader]
    if not reader.fieldnames:
        raise ValueError("ESM flatfile response has no CSV header")
    if not rows:
        raise ValueError("ESM flatfile response has no data rows")
    return list(reader.fieldnames), rows


def authoritative_esm_event_id(rows: list[dict[str, str]]) -> str:
    values = {str(row.get("ESM_event_id", "")).strip() for row in rows if str(row.get("ESM_event_id", "")).strip()}
    if not values:
        raise ValueError("Flatfile rows contain no ESM_event_id")
    if len(values) != 1:
        raise ValueError(f"Flatfile crosswalk is ambiguous: multiple ESM_event_id values {sorted(values)}")
    return next(iter(values))


def inspect_ascii_zip(body: bytes) -> dict[str, Any]:
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        names = [name for name in archive.namelist() if not name.endswith("/")]
        if not names:
            raise ValueError("ESM event-data ZIP contains no files")
        header_keys: set[str] = set()
        previews: dict[str, list[str]] = {}
        for name in names[:12]:
            text = archive.read(name).decode("utf-8-sig", errors="replace")
            header_lines: list[str] = []
            for line in text.splitlines()[:120]:
                stripped = line.strip()
                if stripped and ":" in stripped:
                    key = stripped.split(":", 1)[0].strip()
                    if key and len(key) <= 80:
                        header_keys.add(key)
                        header_lines.append(stripped[:240])
            previews[name] = header_lines[:30]
        return {"file_count": len(names), "file_names": names[:50], "header_keys": sorted(header_keys), "header_previews": previews}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection-probe", type=Path, default=DATASET_SELECTION_PROBE)
    parser.add_argument("--flatfile-out", type=Path, default=DEFAULT_FLATFILE)
    parser.add_argument("--eventdata-out", type=Path, default=DEFAULT_EVENTDATA)
    parser.add_argument("--summary-out", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--timeout-s", type=float, default=90.0)
    parser.add_argument("--pad-seconds", type=int, default=60)
    args = parser.parse_args()

    parsed = json.loads(args.selection_probe.read_text(encoding="utf-8"))
    row = choose_probe_record(parsed)
    flat_url = build_flatfile_url(row, args.pad_seconds)
    flat_status, flat_type, flat_body = fetch_bytes(flat_url, args.timeout_s)
    fields, flat_rows = parse_flatfile(flat_body)
    esm_event_id = authoritative_esm_event_id(flat_rows)
    event_url = build_eventdata_url(row, esm_event_id)
    event_status, event_type, event_body = fetch_bytes(event_url, args.timeout_s)
    if not zipfile.is_zipfile(io.BytesIO(event_body)):
        raise RuntimeError("ESM event-data ASCII response is not a ZIP archive")
    zip_info = inspect_ascii_zip(event_body)

    args.flatfile_out.parent.mkdir(parents=True, exist_ok=True)
    args.flatfile_out.write_bytes(flat_body)
    args.eventdata_out.write_bytes(event_body)
    summary = {
        "probe_type": "ESM_FLATFILE_EVENTDATA_SOURCE_DISCOVERY_ONLY_V2",
        "final_manifest": False,
        "fetched_at_utc": _now_utc(),
        "dataset_selection_event_id": row.get("event_id"),
        "authoritative_esm_event_id": esm_event_id,
        "flatfile": {"request_url": flat_url, "http_status": flat_status, "content_type": flat_type, "sha256": hashlib.sha256(flat_body).hexdigest(), "bytes": len(flat_body), "field_count": len(fields), "row_count": len(flat_rows), "fields": fields},
        "eventdata": {"request_url": event_url, "http_status": event_status, "content_type": event_type, "sha256": hashlib.sha256(event_body).hexdigest(), "bytes": len(event_body), **zip_info},
        "notes": [
            "Dataset Selection event_id is not assumed to be an ESM Flatfile ESM-ID.",
            "Flatfile crosswalk uses event time + network + station + normalized channel family.",
            "No final source ordering, event selection, manifest, OSF registration, or confirmatory result is produced.",
        ],
    }
    args.summary_out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Dataset Selection identity: {row['event_id']} {row['net_name']}.{row['station_code']}.{row.get('location_code','')}.{row['instr_code']}")
    print(f"Flatfile crosswalk ESM_event_id: {esm_event_id}")
    print(f"ESM flatfile HTTP {flat_status}; rows={len(flat_rows)}; fields={len(fields)}; bytes={len(flat_body)}")
    print(f"ESM event-data HTTP {event_status}; ZIP files={zip_info['file_count']}; bytes={len(event_body)}")
    print(f"ASCII header keys: {zip_info['header_keys'] or '-'}")
    print(f"Wrote private probe summary: {args.summary_out}")
    print("No final manifest or confirmatory result was produced.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
