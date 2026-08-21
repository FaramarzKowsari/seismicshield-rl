#!/usr/bin/env python3
"""Materialize the frozen 160-record ESM selection into private SI-normalized records.

This stage is preregistration/data-preparation infrastructure only. It consumes the already
selected 40 x 4 ESM record identities plus the exhaustive private inventory, reopens the exact
cached source ZIP/member bytes, revalidates source identity/sample-count/PGA evidence, converts
cm/s^2 to m/s^2 without filtering or resampling, and writes deterministic private CSV records plus
a manifest-staging CSV with raw and processed SHA-256 evidence.

It does NOT assign train/validation/pilot/confirmatory partitions, write the final public manifest,
submit OSF registration, create the source tag, enable the confirmatory gate, or inspect any
confirmatory simulation result.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import sys
from typing import Any
from urllib.parse import parse_qs, urlsplit
import zipfile

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.ground_motion_manifest import (  # noqa: E402
    COLUMNS,
    ESM_SOURCE,
    PGA_TOLERANCE_CM_S2,
    STANDARD_GRAVITY_M_S2,
    eligibility_errors,
    esm_horizontal_stream,
    esm_record_id,
    sha_key,
)
from scripts.probe_esm_eventdata_direct import parse_header  # noqa: E402

DEFAULT_SELECTION = Path("results/local/esm/esm_selected_records_160.csv")
DEFAULT_INVENTORY = Path("results/local/esm/esm_selected_event_record_inventory.json")
DEFAULT_PROCESSED_DIR = Path("data/private/esm/processed-selected")
DEFAULT_STAGING = Path("results/local/esm/esm_selected_records_manifest_staging.csv")
DEFAULT_AUDIT = Path("results/local/esm/esm_selected_records_materialization.audit.json")
EXPECTED_EVENTS = 40
EXPECTED_RECORDS = 160
EXPECTED_PER_EVENT = 4
EXTRA_COLUMNS = ("event_rank", "record_rank", "record_hash", "processed_path")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
DATE_RE = re.compile(r"^(\d{4})(\d{2})(\d{2})$")
TIME_RE = re.compile(r"^(\d{2})(\d{2})(\d{2})(\.\d+)?$")


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_decimal(value: Decimal) -> str:
    if not value.is_finite():
        raise ValueError("non-finite decimal value")
    if value == 0:
        return "0"
    return format(value.normalize(), "f")


def _decimal_header(header: dict[str, str], *keys: str) -> Decimal:
    for key in keys:
        text = str(header.get(key, "")).strip()
        if not text:
            continue
        try:
            value = Decimal(text)
        except InvalidOperation as exc:
            raise ValueError(f"invalid numeric header {key}") from exc
        if not value.is_finite():
            raise ValueError(f"non-finite numeric header {key}")
        return value
    raise ValueError(f"missing numeric header: {' or '.join(keys)}")


def _int_header(header: dict[str, str], key: str) -> int:
    text = str(header.get(key, "")).strip()
    if not re.fullmatch(r"[0-9]+", text):
        raise ValueError(f"invalid or missing integer header {key}")
    return int(text)


def _parse_samples_decimal(text: str) -> list[Decimal]:
    samples: list[Decimal] = []
    started = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if not started and ":" in line:
            continue
        tokens = line.replace(",", " ").split()
        if not tokens:
            continue
        try:
            values = [Decimal(token) for token in tokens]
        except InvalidOperation:
            if started:
                raise ValueError("non-numeric text encountered after ESM sample section began")
            continue
        if not all(value.is_finite() for value in values):
            raise ValueError("ESM acceleration samples must all be finite")
        started = True
        samples.extend(values)
    if not samples:
        raise ValueError("no numeric acceleration samples found in ESM ASCII member")
    return samples


def _event_timestamp(header: dict[str, str]) -> tuple[str, str]:
    date_text = str(header.get("EVENT_DATE_YYYYMMDD", "")).strip()
    time_text = str(header.get("EVENT_TIME_HHMMSS", "")).strip()
    date_match = DATE_RE.fullmatch(date_text)
    time_match = TIME_RE.fullmatch(time_text)
    if not date_match or not time_match:
        raise ValueError("missing/invalid ESM event date/time headers")
    year, month, day = map(int, date_match.groups())
    hour, minute, second = map(int, time_match.groups()[:3])
    try:
        datetime(year, month, day, hour, minute, second)
    except ValueError as exc:
        raise ValueError("invalid ESM event date/time value") from exc
    fraction = time_match.group(4) or ""
    event_date = f"{year:04d}-{month:02d}-{day:02d}"
    return event_date, f"{event_date}T{hour:02d}:{minute:02d}:{second:02d}{fraction}Z"


def _load_selection(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = [{key: (value or "").strip() for key, value in row.items()} for row in csv.DictReader(handle)]
    if len(rows) != EXPECTED_RECORDS:
        raise ValueError(f"selection must contain exactly {EXPECTED_RECORDS} rows")
    event_counts: dict[str, int] = {}
    identities: set[tuple[str, str]] = set()
    for row in rows:
        if row.get("source") != ESM_SOURCE:
            raise ValueError("selection contains a non-ESM source")
        event_id = row.get("event_id", "")
        record_id = row.get("record_id", "")
        if not event_id or not record_id:
            raise ValueError("selection contains blank event_id/record_id")
        identity = (event_id, record_id)
        if identity in identities:
            raise ValueError(f"duplicate selected identity: {identity}")
        identities.add(identity)
        event_counts[event_id] = event_counts.get(event_id, 0) + 1
        expected_hash = sha_key("record", {"source": ESM_SOURCE, "event_id": event_id, "record_id": record_id})
        if row.get("record_hash") != expected_hash:
            raise ValueError(f"noncanonical selected record hash for {event_id} / {record_id}")
        for field in ("source_member_sha256", "source_zip_sha256"):
            if not SHA256_RE.fullmatch(row.get(field, "").lower()):
                raise ValueError(f"invalid {field} in selection")
    if len(event_counts) != EXPECTED_EVENTS:
        raise ValueError(f"selection must contain exactly {EXPECTED_EVENTS} events")
    if any(count != EXPECTED_PER_EVENT for count in event_counts.values()):
        raise ValueError("selection must contain exactly four records per event")
    return rows


def _load_inventory(path: Path) -> dict[str, dict[str, Any]]:
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, list):
        raise ValueError("inventory must be a JSON list")
    mapping: dict[str, dict[str, Any]] = {}
    for row in parsed:
        if not isinstance(row, dict):
            raise ValueError("inventory contains a non-object event row")
        event_id = str(row.get("event_id", "")).strip()
        if not event_id:
            raise ValueError("inventory contains blank event_id")
        if event_id in mapping:
            raise ValueError(f"duplicate inventory event_id {event_id!r}")
        mapping[event_id] = row
    return mapping


def _record_from_inventory(event: dict[str, Any], record_id: str) -> dict[str, Any]:
    records = event.get("passing_records_hash_order_preview")
    if not isinstance(records, list):
        raise ValueError("inventory event lacks passing-record list")
    matches = [row for row in records if isinstance(row, dict) and str(row.get("record_id", "")).strip() == record_id]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one inventory record for {record_id!r}; found {len(matches)}")
    return matches[0]


def _request_metadata(event: dict[str, Any], record_id: str) -> tuple[str, str]:
    waveforms = event.get("waveforms")
    if not isinstance(waveforms, list):
        raise ValueError("inventory event lacks waveform request audit list")
    processing: set[str] = set()
    quality: set[str] = set()
    for waveform in waveforms:
        if not isinstance(waveform, dict) or waveform.get("status") != "AUDITED":
            continue
        passed = waveform.get("passing_records_in_request")
        if not isinstance(passed, list) or record_id not in {str(value) for value in passed}:
            continue
        ptype = str(waveform.get("processing_type", "")).strip().upper()
        qclass = str(waveform.get("quality_class", "")).strip().upper()
        if ptype:
            processing.add(ptype)
        if qclass:
            quality.add(qclass)
    if len(processing) != 1:
        raise ValueError(f"record {record_id!r} has ambiguous/missing source processing type: {sorted(processing)}")
    if len(quality) != 1:
        raise ValueError(f"record {record_id!r} has ambiguous/missing source quality class: {sorted(quality)}")
    ptype = next(iter(processing))
    qclass = next(iter(quality))
    if ptype not in {"CV", "MP", "AP", "MB"}:
        raise ValueError(f"unsupported ESM processing type {ptype!r}")
    if qclass not in {"BEST", "GOOD", "BAD", "UNDEF"}:
        raise ValueError(f"unsupported ESM quality class {qclass!r}")
    return ptype, qclass


def _zip_member_bytes(record: dict[str, Any], selection: dict[str, str]) -> tuple[bytes, dict[str, str]]:
    raw_path_text = str(record.get("source_zip_path", "")).strip()
    member_name = str(record.get("file_name", "")).strip()
    if not raw_path_text or not member_name:
        raise ValueError("inventory record lacks source ZIP path/member name")
    if PurePosixPath(member_name.replace("\\", "/")).name != selection["record_id"]:
        raise ValueError("inventory member basename disagrees with selected canonical record_id")
    zip_path = Path(raw_path_text.replace("\\", "/"))
    if not zip_path.exists() or not zipfile.is_zipfile(zip_path):
        raise ValueError(f"cached source ZIP is missing/invalid: {zip_path}")
    zip_bytes = zip_path.read_bytes()
    if _sha256_bytes(zip_bytes) != selection["source_zip_sha256"].lower():
        raise ValueError("cached source ZIP SHA-256 disagrees with frozen selection")
    with zipfile.ZipFile(zip_path) as archive:
        if member_name not in archive.namelist():
            raise ValueError(f"selected source member missing from cached ZIP: {member_name}")
        member_bytes = archive.read(member_name)
    if _sha256_bytes(member_bytes) != selection["source_member_sha256"].lower():
        raise ValueError("source member SHA-256 disagrees with frozen selection")
    try:
        text = member_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("ESM ASCII source member is not valid UTF-8/ASCII") from exc
    return member_bytes, parse_header(text)


def _normalized_csv_bytes(samples_cm_s2: list[Decimal], dt_s: Decimal) -> bytes:
    lines = ["time_s,accel_mps2"]
    scale = Decimal("100")
    for index, sample in enumerate(samples_cm_s2):
        time_s = dt_s * index
        accel_mps2 = sample / scale
        lines.append(f"{_canonical_decimal(time_s)},{_canonical_decimal(accel_mps2)}")
    return ("\n".join(lines) + "\n").encode("utf-8")


def _query_processing(url: str) -> str:
    parsed = urlsplit(url)
    values = parse_qs(parsed.query, keep_blank_values=True).get("processing-type", [])
    if len(values) != 1:
        raise ValueError("ESM source request URL lacks exactly one processing-type query value")
    return values[0].strip().upper()


def materialize_one(
    selection: dict[str, str],
    event: dict[str, Any],
    processed_dir: Path,
) -> dict[str, str]:
    if event.get("status") != "COMPLETE_RECORD_INVENTORY" or int(event.get("waveform_errors") or 0) != 0:
        raise ValueError(f"event {selection['event_id']} does not have a complete zero-error inventory")
    record = _record_from_inventory(event, selection["record_id"])
    if str(record.get("record_hash_preview", "")).strip() != selection["record_hash"]:
        raise ValueError("inventory record hash disagrees with frozen selection")
    if str(record.get("source_member_sha256", "")).strip().lower() != selection["source_member_sha256"].lower():
        raise ValueError("inventory member SHA-256 disagrees with frozen selection")
    if str(record.get("source_zip_sha256", "")).strip().lower() != selection["source_zip_sha256"].lower():
        raise ValueError("inventory ZIP SHA-256 disagrees with frozen selection")

    member_bytes, header = _zip_member_bytes(record, selection)
    text = member_bytes.decode("utf-8-sig")
    samples = _parse_samples_decimal(text)
    ndata = _int_header(header, "NDATA")
    if ndata < 2 or len(samples) != ndata:
        raise ValueError("ESM source member NDATA/sample-count contract failed during materialization")

    event_id = str(header.get("EVENT_ID", "")).strip()
    if event_id != selection["event_id"]:
        raise ValueError("ESM ASCII EVENT_ID disagrees with frozen selected event")
    stream = str(header.get("STREAM", "")).strip().upper()
    if not esm_horizontal_stream(stream):
        raise ValueError("selected ESM source member is not an eligible horizontal stream")
    record_id = esm_record_id(selection["record_id"])

    network = str(header.get("NETWORK", "")).strip()
    station = str(header.get("STATION_CODE", "")).strip()
    location = str(header.get("LOCATION", "")).strip()
    if not network or not station:
        raise ValueError("selected ESM source member lacks network/station identity")
    if selection.get("network_code") and selection["network_code"] != network:
        raise ValueError("selected network identity disagrees with source member")
    if selection.get("station_id") and selection["station_id"] != station:
        raise ValueError("selected station identity disagrees with source member")
    if selection.get("location_code", "") != location:
        raise ValueError("selected location identity disagrees with source member")

    units = str(header.get("UNITS", "")).strip()
    if units.lower().replace(" ", "") not in {"cm/s^2", "cm/s2"}:
        raise ValueError("selected ESM source member is not authoritative cm/s^2 acceleration")
    dt = _decimal_header(header, "SAMPLING_INTERVAL_S")
    if dt <= 0 or dt > Decimal("0.020"):
        raise ValueError("selected ESM source member has ineligible sampling interval")

    duration_text = str(header.get("DURATION_S", "")).strip()
    if duration_text:
        try:
            duration = Decimal(duration_text)
        except InvalidOperation as exc:
            raise ValueError("invalid ESM DURATION_S") from exc
        if not duration.is_finite() or duration <= 0:
            raise ValueError("invalid ESM DURATION_S")
        duration_derivation = "explicit:DURATION_S"
    else:
        duration = (ndata - 1) * dt
        duration_derivation = "(NDATA - 1) * SAMPLING_INTERVAL_S"
    if duration < Decimal("10"):
        raise ValueError("selected ESM source member has ineligible usable duration")

    header_pga = abs(_decimal_header(header, "PGA_CM/S^2", "PGA_CM_S2"))
    parsed_pga = max(abs(value) for value in samples)
    difference = abs(parsed_pga - header_pga)
    if difference > Decimal(str(PGA_TOLERANCE_CM_S2)):
        raise ValueError("selected ESM source member parsed PGA disagrees with header")
    threshold = Decimal("0.15") * Decimal(str(STANDARD_GRAVITY_M_S2)) * Decimal("100")
    if parsed_pga < threshold:
        raise ValueError("selected ESM source member has ineligible PGA")

    event_date, event_time_utc = _event_timestamp(header)
    latitude = _decimal_header(header, "EVENT_LATITUDE_DEGREE")
    longitude = _decimal_header(header, "EVENT_LONGITUDE_DEGREE")
    data_license = str(header.get("DATA_LICENSE", "")).strip()
    data_citation = str(header.get("DATA_CITATION", "")).strip()
    if not data_license or not data_citation:
        raise ValueError("selected ESM source member lacks license/citation provenance")

    processing_type, quality_class = _request_metadata(event, record_id)
    source_url = str(record.get("source_request_url", "")).strip()
    if source_url != selection.get("source_request_url", ""):
        raise ValueError("inventory source request URL disagrees with frozen selection")
    if _query_processing(source_url) != processing_type:
        raise ValueError("source request processing-type disagrees with audited request metadata")

    processed_bytes = _normalized_csv_bytes(samples, dt)
    processed_sha = _sha256_bytes(processed_bytes)
    processed_dir.mkdir(parents=True, exist_ok=True)
    event_rank = int(selection["event_rank"])
    record_rank = int(selection["record_rank"])
    processed_name = f"e{event_rank:03d}_r{record_rank:02d}_{selection['record_hash'][:16]}.csv"
    processed_path = processed_dir / processed_name
    processed_path.write_bytes(processed_bytes)

    pga_g = parsed_pga / (Decimal(str(STANDARD_GRAVITY_M_S2)) * Decimal("100"))
    row = {column: "" for column in COLUMNS}
    row.update(
        source=ESM_SOURCE,
        event_id=event_id,
        raw_header_event_id=event_id,
        record_id=record_id,
        waveform_detail_id="",
        stream=stream,
        raw_filename=record_id,
        network_code=network,
        station_id=station,
        location_code=location,
        component="horizontal acceleration",
        sampling_interval_s=_canonical_decimal(dt),
        usable_duration_s=_canonical_decimal(duration),
        original_units=units,
        normalized_units="m/s^2",
        ndata=str(ndata),
        parsed_sample_count=str(len(samples)),
        raw_duration_derivation=duration_derivation,
        pga_cm_s2=_canonical_decimal(parsed_pga),
        source_header_pga_cm_s2=_canonical_decimal(header_pga),
        pga_g=_canonical_decimal(pga_g),
        event_date=event_date,
        event_time_utc=event_time_utc,
        latitude=_canonical_decimal(latitude),
        longitude=_canonical_decimal(longitude),
        partition="",
        source_url_or_access_reference=source_url,
        preprocessing_status=f"source_processed:{processing_type};project_unit_normalized:cm/s^2->m/s^2",
        source_processing_type=processing_type,
        source_quality_class=quality_class,
        raw_sha256=selection["source_member_sha256"].lower(),
        processed_sha256=processed_sha,
        data_license=data_license,
        data_citation=data_citation,
        raw_redistribution_allowed="false",
        eligibility_status="",
        eligibility_reason="",
    )
    errors = eligibility_errors(row)
    if errors:
        raise ValueError(f"materialized row fails frozen eligibility contract: {'; '.join(errors)}")
    row.update(
        event_rank=selection["event_rank"],
        record_rank=selection["record_rank"],
        record_hash=selection["record_hash"],
        processed_path=processed_path.as_posix(),
    )
    return row


def _write_staging(rows: list[dict[str, str]], path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = (*COLUMNS, *EXTRA_COLUMNS)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return _sha256_path(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", type=Path, default=DEFAULT_SELECTION)
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--processed-dir", type=Path, default=DEFAULT_PROCESSED_DIR)
    parser.add_argument("--staging-out", type=Path, default=DEFAULT_STAGING)
    parser.add_argument("--audit-out", type=Path, default=DEFAULT_AUDIT)
    args = parser.parse_args()
    try:
        selections = _load_selection(args.selection)
        inventory = _load_inventory(args.inventory)
        missing = sorted({row["event_id"] for row in selections} - set(inventory))
        if missing:
            raise ValueError(f"inventory is missing selected events: {missing[:5]}")
        rows = [materialize_one(row, inventory[row["event_id"]], args.processed_dir) for row in selections]
        staging_sha = _write_staging(rows, args.staging_out)
        digest_lines = [f"{row['event_id']}\0{row['record_id']}\0{row['processed_sha256']}\n" for row in rows]
        processed_set_sha = hashlib.sha256("".join(digest_lines).encode("utf-8")).hexdigest()
        audit = {
            "audit_type": "ESM_SELECTED_160_PRIVATE_SI_MATERIALIZATION",
            "final_manifest": False,
            "partition_assignment_performed": False,
            "selected_events": EXPECTED_EVENTS,
            "selected_records": EXPECTED_RECORDS,
            "records_per_event": EXPECTED_PER_EVENT,
            "transformation": "source-distributed ESM acceleration cm/s^2 divided by exactly 100; no filtering/resampling",
            "selection_csv": str(args.selection),
            "selection_csv_sha256": _sha256_path(args.selection),
            "source_inventory": str(args.inventory),
            "source_inventory_sha256": _sha256_path(args.inventory),
            "staging_csv": str(args.staging_out),
            "staging_csv_sha256": staging_sha,
            "processed_record_set_sha256": processed_set_sha,
            "processed_private_dir": args.processed_dir.as_posix(),
            "generated_at_utc": _now_utc(),
            "notes": [
                "Every selected source ZIP/member hash is rechecked against the frozen 160-record selection.",
                "Every source member is reparsed and NDATA/PGA/event/station identity is revalidated before materialization.",
                "Processed waveform bytes remain private because raw/source redistribution permission is not assumed.",
                "No final manifest, partition assignment, OSF registration, source tag, gate enablement, or confirmatory result is produced.",
            ],
        }
        args.audit_out.parent.mkdir(parents=True, exist_ok=True)
        args.audit_out.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (OSError, ValueError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
        parser.error(str(exc))

    print(f"Materialized selected ESM records: {len(rows)}")
    print(f"Private normalized record directory: {args.processed_dir}")
    print(f"Staging metadata: {args.staging_out}")
    print(f"Staging SHA-256: {staging_sha}")
    print(f"Processed record-set SHA-256: {processed_set_sha}")
    print(f"Audit: {args.audit_out}")
    print("No final manifest, partition assignment, OSF registration, source tag, or confirmatory result was produced.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
