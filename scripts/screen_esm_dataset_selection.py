#!/usr/bin/env python3
"""Build a broad, source-specific ESM prescreen inventory without changing the frozen design.

This is source-discovery/data-selection infrastructure only. It queries the public ESM Dataset
Selection service for processed accelerometric families (HN/HG/HL), keeps all public quality
classes, and uses corr_hz_PGA only as a necessary-condition prescreen. The direct Event-Data probe
validated on 2026-08-20 that corr_hz_PGA round-trips to the authoritative ASCII horizontal PGA in
cm/s^2 for the tested waveform. Final component eligibility must still be established from Event-
Data ASCII headers.

No cross-source ordering, AFAD/ESM deduplication, final 40-event selection, manifest, OSF
registration, source tag, or confirmatory result is produced here.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE_URL = "https://esm-db.eu/esmws/dataset-selection/1/query"
FAMILIES = ("HN*", "HG*", "HL*")
STANDARD_GRAVITY_M_S2 = 9.80665
PGA_THRESHOLD_CM_S2 = 0.15 * STANDARD_GRAVITY_M_S2 * 100.0
DEFAULT_RAW_DIR = Path("data/private/esm/dataset-selection-full")
DEFAULT_SUMMARY = Path("results/local/esm/dataset_selection_prescreen_summary.json")
DEFAULT_CANDIDATES = Path("results/local/esm/dataset_selection_event_candidates.json")


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


def build_query(family: str) -> dict[str, str]:
    # Broad public processed inventory. No magnitude cut is introduced (minmag=0).
    # BAD/UNDEF are deliberately retained at this discovery stage to avoid silently adding a
    # quality-class eligibility rule before the second-source design is frozen.
    return {
        "eventid": "*",
        "starttime": "1900-01-01",
        "endtime": "2100-01-01",
        "minmag": "0",
        "maxdist": "3000",
        "network": "*",
        "station": "*",
        "instrument": family,
        "unprocessed": "false",
        "discarded": "false",
        "automatic": "true",
        "manual": "true",
        "standard": "true",
        "ebasco": "true",
        "processing-filter-logic": "available",
        "best": "true",
        "good": "true",
        "bad": "true",
        "undef": "true",
        "quality-reason": "all",
        "format": "json",
        "offset": "0",
        "limit": "0",
        "indent": "false",
    }


def fetch_family(family: str, timeout_s: float) -> tuple[str, bytes, list[dict[str, Any]]]:
    url = BASE_URL + "?" + urlencode(build_query(family))
    request = Request(url, headers={"User-Agent": "SeismicShield-RL/0.8 ESM exhaustive prescreen"})
    with urlopen(request, timeout=timeout_s) as response:  # noqa: S310 - fixed HTTPS ESM service
        body = response.read()
        status = int(getattr(response, "status", response.getcode()))
    if status != 200:
        raise RuntimeError(f"ESM Dataset Selection returned HTTP {status} for {family}")
    parsed = json.loads(body.decode("utf-8"))
    return url, body, _records(parsed)


def waveform_identity(row: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        str(row.get("event_id", "")).strip(),
        str(row.get("net_name", "")).strip(),
        str(row.get("station_code", "")).strip(),
        str(row.get("location_code", "")).strip(),
        str(row.get("instr_code", "")).strip().upper(),
    )


def pga_value(row: dict[str, Any]) -> float | None:
    raw = row.get("corr_hz_PGA")
    try:
        if raw is None or not str(raw).strip():
            return None
        return abs(float(raw))
    except (TypeError, ValueError):
        return None


def build_event_inventory(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # Dataset Selection can expose the same waveform through more than one family request or
    # processing availability path. Keep one deterministic row per waveform identity, preferring
    # the larger finite corr_hz_PGA only for this necessary-condition inventory.
    unique: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    for row in rows:
        ident = waveform_identity(row)
        if not ident[0] or not ident[1] or not ident[2] or not ident[4]:
            continue
        previous = unique.get(ident)
        if previous is None:
            unique[ident] = row
            continue
        old_pga = pga_value(previous)
        new_pga = pga_value(row)
        if new_pga is not None and (old_pga is None or new_pga > old_pga):
            unique[ident] = row

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in unique.values():
        grouped[str(row.get("event_id", "")).strip()].append(row)

    events: list[dict[str, Any]] = []
    for event_id, event_rows in grouped.items():
        above = [row for row in event_rows if (pga_value(row) or 0.0) >= PGA_THRESHOLD_CM_S2]
        # One ESM waveform identity can return at most two horizontal acceleration components.
        # Therefore >=2 station/waveform identities above the station-level PGA threshold is only
        # a necessary condition for reaching four final horizontal components; Event-Data audit is
        # still mandatory.
        candidate = len(above) >= 2
        event_times = sorted({str(row.get("event_time", "")).strip() for row in event_rows if row.get("event_time")})
        events.append(
            {
                "event_id": event_id,
                "event_times": event_times,
                "waveform_identities": len(event_rows),
                "rows_at_or_above_0p15g": len(above),
                "max_corr_hz_PGA_cm_s2": max((pga_value(row) or 0.0) for row in event_rows),
                "necessary_condition_candidate": candidate,
                "candidate_waveforms": [
                    {
                        "network": row.get("net_name"),
                        "station": row.get("station_code"),
                        "location": row.get("location_code"),
                        "instrument": row.get("instr_code"),
                        "processing_type": row.get("processing_type"),
                        "quality_class": row.get("class"),
                        "corr_hz_PGA_cm_s2": pga_value(row),
                    }
                    for row in sorted(
                        above,
                        key=lambda item: (
                            -(pga_value(item) or 0.0),
                            str(item.get("net_name", "")),
                            str(item.get("station_code", "")),
                            str(item.get("location_code", "")),
                            str(item.get("instr_code", "")),
                        ),
                    )
                ],
            }
        )
    return sorted(
        events,
        key=lambda item: (
            not item["necessary_condition_candidate"],
            -int(item["rows_at_or_above_0p15g"]),
            str(item["event_id"]),
        ),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout-s", type=float, default=180.0)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--summary-out", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--candidates-out", type=Path, default=DEFAULT_CANDIDATES)
    args = parser.parse_args()
    if args.timeout_s <= 0:
        parser.error("--timeout-s must be > 0")

    args.raw_dir.mkdir(parents=True, exist_ok=True)
    all_rows: list[dict[str, Any]] = []
    source_requests: list[dict[str, Any]] = []
    for family in FAMILIES:
        print(f"Fetching ESM Dataset Selection family {family} ...", flush=True)
        url, body, rows = fetch_family(family, args.timeout_s)
        raw_path = args.raw_dir / f"dataset-selection-{family[:2].lower()}.json"
        raw_path.write_bytes(body)
        digest = hashlib.sha256(body).hexdigest()
        source_requests.append(
            {
                "family": family,
                "request_url": url,
                "response_sha256": digest,
                "response_bytes": len(body),
                "rows": len(rows),
                "raw_path": str(raw_path),
            }
        )
        all_rows.extend(rows)
        print(f"  rows={len(rows)} bytes={len(body)} sha256={digest}")

    events = build_event_inventory(all_rows)
    candidates = [event for event in events if event["necessary_condition_candidate"]]
    unique_waveforms = sum(event["waveform_identities"] for event in events)
    above_rows = sum(event["rows_at_or_above_0p15g"] for event in events)

    args.candidates_out.parent.mkdir(parents=True, exist_ok=True)
    args.candidates_out.write_text(json.dumps(candidates, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary = {
        "screen_type": "ESM_DATASET_SELECTION_NECESSARY_CONDITION_PRESCREEN_ONLY",
        "final_manifest": False,
        "fetched_at_utc": _now_utc(),
        "source_requests": source_requests,
        "pga_threshold_cm_s2": PGA_THRESHOLD_CM_S2,
        "input_rows_across_family_requests": len(all_rows),
        "unique_events": len(events),
        "unique_waveform_identities": unique_waveforms,
        "waveform_identities_at_or_above_0p15g": above_rows,
        "event_candidates_with_at_least_two_above_threshold_waveforms": len(candidates),
        "candidate_output": str(args.candidates_out),
        "notes": [
            "corr_hz_PGA is used only as a necessary-condition prescreen after a direct Event-Data round-trip matched the tested ASCII header PGA within 0.01 cm/s^2.",
            "All final component checks must use authoritative Event-Data ASCII headers.",
            "BAD and UNDEF quality classes are retained in source discovery; no new quality-class exclusion is introduced here.",
            "No cross-source deduplication, source ordering, final 40-event selection, OSF registration, source tag, or confirmatory result is produced.",
        ],
    }
    args.summary_out.parent.mkdir(parents=True, exist_ok=True)
    args.summary_out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"Unique ESM events: {len(events)}")
    print(f"Unique waveform identities: {unique_waveforms}")
    print(f"Waveforms with corr_hz_PGA >= 0.15g: {above_rows}")
    print(f"Necessary-condition event candidates (>=2 such waveforms): {len(candidates)}")
    print(f"Wrote private/raw source responses under: {args.raw_dir}")
    print(f"Wrote candidate inventory: {args.candidates_out}")
    print(f"Wrote summary: {args.summary_out}")
    print("No final source ordering, manifest, OSF registration, or confirmatory result was produced.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
