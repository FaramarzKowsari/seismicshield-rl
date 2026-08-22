#!/usr/bin/env python3
"""Ephemerally hydrate the frozen ESM manifest and verify exact processed SHA-256 bytes.

This is transport/integrity infrastructure, not a scientific analysis step. It downloads the
public ESM access references recorded in the frozen manifest, extracts only the recorded ASCII
member, validates live source identity/header semantics, converts cm/s^2 to m/s^2 without
filtering/resampling, and accepts an output only when its processed SHA-256 exactly matches the
public frozen manifest. A live source-member byte hash may differ from the historical frozen raw
hash only when all frozen identity/numerical header checks pass and the exact processed hash is
reproduced; that raw-byte drift is explicitly recorded in the audit. Waveform files are written
only to the requested private directory and must never be uploaded as CI artifacts.
"""
from __future__ import annotations

import argparse
import csv
from decimal import Decimal, InvalidOperation
import hashlib
from io import BytesIO
import json
from pathlib import Path, PurePosixPath
import time
from urllib.request import Request, urlopen
import zipfile

EXPECTED_MANIFEST_SHA256 = "0f8056d5b7a3dc0af3a80539a409f2c946b8495e96ba91d540a5d1011e3fc64b"
EXPECTED_RECORDS = 136
EXPECTED_PARTITIONS = {"training": 52, "validation": 20, "pilot": 16, "confirmatory": 48}
ALLOWED_LICENSE_PREFIXES = ("CC-BY3_0-IT", "CC-BY4_0")
USER_AGENT = "SeismicShield-RL/0.8.2 frozen-manifest-hydrator"
PGA_TOLERANCE_CM_S2 = Decimal("0.01")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_decimal(value: Decimal) -> str:
    if not value.is_finite():
        raise ValueError("non-finite decimal value")
    if value == 0:
        return "0"
    return format(value.normalize(), "f")


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


def parse_samples_decimal(text: str) -> list[Decimal]:
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


def normalized_csv_bytes(samples_cm_s2: list[Decimal], dt_s: Decimal) -> bytes:
    if not dt_s.is_finite() or dt_s <= 0:
        raise ValueError("sampling interval must be finite and positive")
    lines = ["time_s,accel_mps2"]
    scale = Decimal("100")
    for index, sample in enumerate(samples_cm_s2):
        time_s = dt_s * index
        accel_mps2 = sample / scale
        lines.append(f"{canonical_decimal(time_s)},{canonical_decimal(accel_mps2)}")
    return ("\n".join(lines) + "\n").encode("utf-8")


def _decimal(value: str, label: str) -> Decimal:
    try:
        parsed = Decimal(str(value).strip())
    except InvalidOperation as exc:
        raise ValueError(f"invalid decimal {label}") from exc
    if not parsed.is_finite():
        raise ValueError(f"non-finite decimal {label}")
    return parsed


def _header_decimal(header: dict[str, str], *keys: str) -> Decimal:
    for key in keys:
        value = header.get(key, "").strip()
        if value:
            return _decimal(value, key)
    raise ValueError(f"missing live ESM header: {' or '.join(keys)}")


def _license_prefix(value: str) -> str:
    upper = value.strip().upper()
    for prefix in ALLOWED_LICENSE_PREFIXES:
        if upper.startswith(prefix):
            return prefix
    return ""


def _validate_live_header(
    row: dict[str, str], header: dict[str, str], samples: list[Decimal]
) -> Decimal:
    record_id = row["record_id"]
    expected_text = {
        "EVENT_ID": row.get("raw_header_event_id") or row["event_id"],
        "STREAM": row["stream"],
        "NETWORK": row["network_code"],
        "STATION_CODE": row["station_id"],
        "LOCATION": row.get("location_code", ""),
    }
    for key, expected in expected_text.items():
        observed = header.get(key, "").strip()
        if observed != expected:
            raise ValueError(
                f"live ESM {key} mismatch for {record_id}: expected {expected!r}, found {observed!r}"
            )

    units = header.get("UNITS", "").strip().lower().replace(" ", "")
    if units not in {"cm/s^2", "cm/s2"}:
        raise ValueError(f"live ESM units mismatch for {record_id}: {header.get('UNITS', '')!r}")

    try:
        ndata = int(header.get("NDATA", "").strip())
    except ValueError as exc:
        raise ValueError(f"invalid live ESM NDATA for {record_id}") from exc
    expected_count = int(row["parsed_sample_count"])
    if ndata != expected_count or int(row["ndata"]) != expected_count or len(samples) != expected_count:
        raise ValueError(
            f"sample-count mismatch for {record_id}: live_NDATA={ndata}, parsed={len(samples)}, "
            f"manifest={expected_count}"
        )

    live_dt = _header_decimal(header, "SAMPLING_INTERVAL_S")
    frozen_dt = _decimal(row["sampling_interval_s"], "manifest sampling_interval_s")
    if live_dt != frozen_dt:
        raise ValueError(
            f"sampling-interval mismatch for {record_id}: expected {frozen_dt}, found {live_dt}"
        )

    duration_text = header.get("DURATION_S", "").strip()
    live_duration = _decimal(duration_text, "DURATION_S") if duration_text else (ndata - 1) * live_dt
    frozen_duration = _decimal(row["usable_duration_s"], "manifest usable_duration_s")
    if live_duration != frozen_duration:
        raise ValueError(
            f"usable-duration mismatch for {record_id}: expected {frozen_duration}, found {live_duration}"
        )

    parsed_pga = max(abs(value) for value in samples)
    frozen_parsed_pga = _decimal(row["pga_cm_s2"], "manifest pga_cm_s2")
    if parsed_pga != frozen_parsed_pga:
        raise ValueError(
            f"parsed PGA mismatch for {record_id}: expected {frozen_parsed_pga}, found {parsed_pga}"
        )
    live_header_pga = abs(_header_decimal(header, "PGA_CM/S^2", "PGA_CM_S2"))
    frozen_header_pga = _decimal(
        row["source_header_pga_cm_s2"], "manifest source_header_pga_cm_s2"
    )
    if abs(live_header_pga - frozen_header_pga) > PGA_TOLERANCE_CM_S2:
        raise ValueError(
            f"header PGA mismatch for {record_id}: expected {frozen_header_pga}, found {live_header_pga}"
        )

    frozen_license_prefix = _license_prefix(row["data_license"])
    live_license_prefix = _license_prefix(header.get("DATA_LICENSE", ""))
    if not frozen_license_prefix or live_license_prefix != frozen_license_prefix:
        raise ValueError(
            f"live ESM license mismatch for {record_id}: expected {frozen_license_prefix or 'accepted CC'}, "
            f"found {header.get('DATA_LICENSE', '')!r}"
        )
    return live_dt


def _manifest_rows(path: Path) -> list[dict[str, str]]:
    if sha256_path(path) != EXPECTED_MANIFEST_SHA256:
        raise ValueError("ground-motion manifest SHA-256 does not match the immutable v0.8.2 gate")
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = [
            {key: (value or "").strip() for key, value in row.items()}
            for row in csv.DictReader(handle)
        ]
    if len(rows) != EXPECTED_RECORDS:
        raise ValueError(f"expected {EXPECTED_RECORDS} frozen records, found {len(rows)}")
    counts = {key: 0 for key in EXPECTED_PARTITIONS}
    identities: set[str] = set()
    for row in rows:
        record_id = row.get("record_id", "")
        if not record_id or record_id in identities:
            raise ValueError(f"blank or duplicate record_id in manifest: {record_id!r}")
        identities.add(record_id)
        partition = row.get("partition", "")
        if partition not in counts:
            raise ValueError(f"unexpected partition {partition!r}")
        counts[partition] += 1
        if row.get("source") != "ESM":
            raise ValueError("frozen v0.8.2 hydration accepts ESM rows only")
        if row.get("original_units") != "cm/s^2" or row.get("normalized_units") != "m/s^2":
            raise ValueError(f"unexpected units for {record_id}")
        if not _license_prefix(row.get("data_license", "")):
            raise ValueError(f"record {record_id} lacks an accepted explicit CC license")
        for field in ("raw_sha256", "processed_sha256"):
            value = row.get(field, "").lower()
            if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
                raise ValueError(f"invalid {field} for {record_id}")
        url = row.get("source_url_or_access_reference", "")
        if not url.startswith("https://esm-db.eu/"):
            raise ValueError(f"unexpected ESM access reference for {record_id}")
    if counts != EXPECTED_PARTITIONS:
        raise ValueError(f"frozen partition counts mismatch: {counts}")
    return rows


def download(url: str, *, timeout_s: int = 90, attempts: int = 4) -> bytes:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            request = Request(
                url,
                headers={"User-Agent": USER_AGENT, "Accept": "application/zip,text/plain,*/*"},
            )
            with urlopen(request, timeout=timeout_s) as response:  # noqa: S310 - validated ESM host
                payload = response.read()
            if not payload:
                raise RuntimeError("ESM returned an empty payload")
            return payload
        except Exception as exc:  # network retry boundary
            last_error = exc
            if attempt == attempts:
                break
            time.sleep(min(8, 2 ** (attempt - 1)))
    raise RuntimeError(
        f"failed to download frozen ESM access reference after {attempts} attempts: {last_error}"
    )


def extract_member(payload: bytes, raw_filename: str) -> bytes:
    if zipfile.is_zipfile(BytesIO(payload)):
        with zipfile.ZipFile(BytesIO(payload)) as archive:
            exact = [name for name in archive.namelist() if name == raw_filename]
            if len(exact) == 1:
                return archive.read(exact[0])
            basename = PurePosixPath(raw_filename.replace("\\", "/")).name
            matches = [
                name
                for name in archive.namelist()
                if PurePosixPath(name.replace("\\", "/")).name == basename
            ]
            if len(matches) != 1:
                raise ValueError(
                    f"expected exactly one ESM ZIP member for {raw_filename!r}, found {len(matches)}"
                )
            return archive.read(matches[0])
    return payload


def materialize_row(
    row: dict[str, str], payload: bytes, output_dir: Path
) -> tuple[Path, bool, dict[str, str] | None]:
    record_id = row["record_id"]
    member_bytes = extract_member(payload, row["raw_filename"])
    observed_raw_sha = sha256_bytes(member_bytes)
    expected_raw_sha = row["raw_sha256"].lower()
    try:
        text = member_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(f"ESM ASCII member is not UTF-8/ASCII for {record_id}") from exc
    header = parse_header(text)
    samples = parse_samples_decimal(text)
    live_dt = _validate_live_header(row, header, samples)
    normalized = normalized_csv_bytes(samples, live_dt)
    processed_sha = sha256_bytes(normalized)
    expected_processed_sha = row["processed_sha256"].lower()
    if processed_sha != expected_processed_sha:
        raise ValueError(
            f"processed SHA-256 mismatch for {record_id}: expected {expected_processed_sha}, "
            f"found {processed_sha}; raw expected {expected_raw_sha}, found {observed_raw_sha}"
        )

    drift = None
    if observed_raw_sha != expected_raw_sha:
        drift = {
            "record_id": record_id,
            "expected_raw_sha256": expected_raw_sha,
            "observed_live_raw_sha256": observed_raw_sha,
            "processed_sha256_reproduced_exactly": expected_processed_sha,
        }

    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"{processed_sha}.csv"
    existed = output.exists()
    if existed and sha256_path(output) != processed_sha:
        raise ValueError(f"existing private file has wrong SHA-256: {output}")
    if not existed:
        output.write_bytes(normalized)
    return output, existed, drift


def hydrate(manifest: Path, output_dir: Path, partitions: set[str]) -> dict:
    rows = _manifest_rows(manifest)
    selected = [row for row in rows if row["partition"] in partitions]
    cache: dict[str, bytes] = {}
    reused = 0
    partition_counts = {key: 0 for key in sorted(partitions)}
    raw_drift: list[dict[str, str]] = []
    for index, row in enumerate(selected, start=1):
        url = row["source_url_or_access_reference"]
        payload = cache.get(url)
        if payload is None:
            payload = download(url)
            cache[url] = payload
        _, existed, drift = materialize_row(row, payload, output_dir)
        reused += int(existed)
        if drift is not None:
            raw_drift.append(drift)
        partition_counts[row["partition"]] += 1
        suffix = " (raw-source bytes drifted; processed hash exact)" if drift else ""
        print(f"[{index}/{len(selected)}] verified {row['partition']} {row['record_id']}{suffix}")
    return {
        "status": "PASS",
        "manifest_sha256": EXPECTED_MANIFEST_SHA256,
        "records_verified": len(selected),
        "partition_counts": partition_counts,
        "unique_access_requests": len(cache),
        "existing_verified_files_reused": reused,
        "raw_source_byte_drift_count": len(raw_drift),
        "raw_source_byte_drift": raw_drift,
        "raw_drift_acceptance_rule": (
            "accepted only after frozen identity/header checks and exact processed_sha256 reproduction"
        ),
        "private_output_directory": str(output_dir),
        "waveform_artifacts_permitted_for_upload": False,
        "confirmatory_response_simulations_run": False,
        "confirmatory_response_metrics_emitted": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--audit-out", type=Path, required=True)
    parser.add_argument(
        "--partitions",
        nargs="+",
        choices=sorted(EXPECTED_PARTITIONS),
        default=list(EXPECTED_PARTITIONS),
    )
    args = parser.parse_args()
    try:
        evidence = hydrate(args.manifest, args.output_dir, set(args.partitions))
        args.audit_out.parent.mkdir(parents=True, exist_ok=True)
        args.audit_out.write_text(
            json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"Frozen ESM hydration: PASS ({evidence['records_verified']} records)")
        print(f"Raw-source byte drift records: {evidence['raw_source_byte_drift_count']}")
        print(f"Audit: {args.audit_out}")
        return 0
    except Exception as exc:
        failure = {"status": "BLOCKED", "error": str(exc)}
        args.audit_out.parent.mkdir(parents=True, exist_ok=True)
        args.audit_out.write_text(
            json.dumps(failure, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"Frozen ESM hydration: BLOCKED\n- {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
