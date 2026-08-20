#!/usr/bin/env python3
"""Probe the public ESM dataset-selection web service without changing the frozen design.

This is source-discovery/provenance infrastructure only. It does not create a final ground-motion
manifest and it does not run confirmatory simulations. The purpose is to verify the machine-readable
ESM response shape before implementing a second-source selector.

Official service documentation:
https://esm-db.eu/esmws/dataset-selection/1/
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE_URL = "https://esm-db.eu/esmws/dataset-selection/1/query"
DEFAULT_RAW = Path("data/private/esm/dataset-selection-probe.json")
DEFAULT_SUMMARY = Path("data/private/esm/dataset-selection-probe-summary.json")
SENSITIVE_TOKENS = ("authorization", "cookie", "csrf", "xsrf", "token", "password", "secret")


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def build_query(args: argparse.Namespace) -> dict[str, str]:
    return {
        "eventid": "*",
        "starttime": args.starttime,
        "endtime": args.endtime,
        "minmag": str(args.minmag),
        "maxdist": str(args.maxdist),
        "network": "*",
        "station": "*",
        "instrument": "*",
        "unprocessed": "false",
        "discarded": "false",
        "automatic": "true",
        "manual": "true",
        "standard": "true",
        "ebasco": "true",
        "processing-filter-logic": "available",
        "best": "true",
        "good": "true",
        "bad": "false",
        "undef": "false",
        "format": "json",
        "offset": "0",
        "limit": str(args.limit),
        "indent": "true",
    }


def fetch_json(url: str, timeout_s: float) -> tuple[int, str, bytes, Any]:
    request = Request(url, headers={"User-Agent": "SeismicShield-RL/0.8 ESM source probe"})
    with urlopen(request, timeout=timeout_s) as response:  # noqa: S310 - fixed HTTPS service
        body = response.read()
        status = int(getattr(response, "status", response.getcode()))
        content_type = response.headers.get("Content-Type", "")
    parsed = json.loads(body.decode("utf-8"))
    return status, content_type, body, parsed


def _record_list(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [row for row in value if isinstance(row, dict)]
    if isinstance(value, dict):
        for key in ("records", "results", "data", "waveforms", "items"):
            rows = value.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
    return []


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if any(token in str(key).lower() for token in SENSITIVE_TOKENS):
                out[str(key)] = "<redacted>"
            else:
                out[str(key)] = _sanitize(item)
        return out
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value


def summarize(parsed: Any, *, url: str, status: int, content_type: str, body: bytes) -> dict[str, Any]:
    records = _record_list(parsed)
    first = records[0] if records else {}
    top_keys = sorted(parsed.keys()) if isinstance(parsed, dict) else []
    first_keys = sorted(first.keys()) if first else []
    preview = _sanitize({key: first[key] for key in first_keys[:40]}) if first else {}
    return {
        "probe_type": "ESM_DATASET_SELECTION_SOURCE_DISCOVERY_ONLY",
        "final_manifest": False,
        "fetched_at_utc": _now_utc(),
        "request_url": url,
        "http_status": status,
        "content_type": content_type,
        "response_sha256": hashlib.sha256(body).hexdigest(),
        "response_bytes": len(body),
        "json_top_level_type": type(parsed).__name__,
        "top_level_keys": top_keys,
        "records_detected": len(records),
        "first_record_keys": first_keys,
        "first_record_preview": preview,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--starttime", default="1900-01-01")
    parser.add_argument("--endtime", default="2100-01-01")
    parser.add_argument("--minmag", type=float, default=4.0)
    parser.add_argument("--maxdist", type=float, default=3000.0)
    parser.add_argument("--limit", type=int, default=5, help="small schema probe only; use 0 only after response shape is validated")
    parser.add_argument("--timeout-s", type=float, default=60.0)
    parser.add_argument("--raw-out", type=Path, default=DEFAULT_RAW)
    parser.add_argument("--summary-out", type=Path, default=DEFAULT_SUMMARY)
    args = parser.parse_args()
    if args.limit < 0:
        parser.error("--limit must be >= 0")
    if args.timeout_s <= 0:
        parser.error("--timeout-s must be > 0")

    query = build_query(args)
    url = BASE_URL + "?" + urlencode(query)
    status, content_type, body, parsed = fetch_json(url, args.timeout_s)
    if status != 200:
        raise RuntimeError(f"ESM dataset-selection returned HTTP {status}")

    args.raw_out.parent.mkdir(parents=True, exist_ok=True)
    args.raw_out.write_bytes(body)
    summary = summarize(parsed, url=url, status=status, content_type=content_type, body=body)
    args.summary_out.parent.mkdir(parents=True, exist_ok=True)
    args.summary_out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"ESM dataset-selection HTTP {status}")
    print(f"Top-level JSON type: {summary['json_top_level_type']}")
    print(f"Detected records: {summary['records_detected']}")
    print(f"Top-level keys: {summary['top_level_keys'] or '-'}")
    print(f"First-record keys: {summary['first_record_keys'] or '-'}")
    print(f"Response SHA256: {summary['response_sha256']}")
    print(f"Wrote private raw response: {args.raw_out}")
    print(f"Wrote private schema summary: {args.summary_out}")
    print("No final manifest or confirmatory result was produced.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
