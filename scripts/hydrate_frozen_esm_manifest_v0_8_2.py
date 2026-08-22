#!/usr/bin/env python3
"""Ephemerally hydrate the frozen ESM manifest and verify exact processed SHA-256 bytes.

This is transport/integrity infrastructure, not a scientific analysis step. It downloads the
public ESM access references recorded in the frozen manifest, extracts only the recorded ASCII
member, converts cm/s^2 to m/s^2 without filtering/resampling, and accepts an output only when
its SHA-256 exactly matches the public manifest. Waveform files are written only to the requested
private directory and must never be uploaded as CI artifacts.
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


def _manifest_rows(path: Path) -> list[dict[str, str]]:
    if sha256_path(path) != EXPECTED_MANIFEST_SHA256:
        raise ValueError("ground-motion manifest SHA-256 does not match the immutable v0.8.2 gate")
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = [{key: (value or "").strip() for key, value in row.items()} for row in csv.DictReader(handle)]
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
        license_text = row.get("data_license", "").upper()
        if not any(license_text.startswith(prefix) for prefix in ALLOWED_LICENSE_PREFIXES):
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
            request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/zip,text/plain,*/*"})
            with urlopen(request, timeout=timeout_s) as response:  # noqa: S310 - frozen HTTPS ESM host is validated above
                payload = response.read()
            if not payload:
                raise RuntimeError("ESM returned an empty payload")
            return payload
        except Exception as exc:  # network retry boundary
            last_error = exc
            if attempt == attempts:
                break
            time.sleep(min(8, 2 ** (attempt - 1)))
    raise RuntimeError(f"failed to download frozen ESM access reference after {attempts} attempts: {last_error}")


def extract_member(payload: bytes, raw_filename: str) -> bytes:
    if zipfile.is_zipfile(BytesIO(payload)):
        with zipfile.ZipFile(BytesIO(payload)) as archive:
            exact = [name for name in archive.namelist() if name == raw_filename]
            if len(exact) == 1:
                return archive.read(exact[0])
            basename = PurePosixPath(raw_filename.replace("\\", "/")).name
            matches = [
                name for name in archive.namelist()
                if PurePosixPath(name.replace("\\", "/")).name == basename
            ]
            if len(matches) != 1:
                raise ValueError(
                    f"expected exactly one ESM ZIP member for {raw_filename!r}, found {len(matches)}"
                )
            return archive.read(matches[0])
    return payload


def materialize_row(row: dict[str, str], payload: bytes, output_dir: Path) -> tuple[Path, bool]:
    record_id = row["record_id"]
    member_bytes = extract_member(payload, row["raw_filename"])
    if sha256_bytes(member_bytes) != row["raw_sha256"].lower():
        raise ValueError(f"raw SHA-256 mismatch for {record_id}")
    try:
        text = member_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(f"ESM ASCII member is not UTF-8/ASCII for {record_id}") from exc
    samples = parse_samples_decimal(text)
    expected_count = int(row["parsed_sample_count"])
    if len(samples) != expected_count or int(row["ndata"]) != expected_count:
        raise ValueError(
            f"sample-count mismatch for {record_id}: parsed={len(samples)}, manifest={expected_count}"
        )
    dt_s = Decimal(row["sampling_interval_s"])
    normalized = normalized_csv_bytes(samples, dt_s)
    processed_sha = sha256_bytes(normalized)
    if processed_sha != row["processed_sha256"].lower():
        raise ValueError(f"processed SHA-256 mismatch for {record_id}")
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"{processed_sha}.csv"
    existed = output.exists()
    if existed and sha256_path(output) != processed_sha:
        raise ValueError(f"existing private file has wrong SHA-256: {output}")
    if not existed:
        output.write_bytes(normalized)
    return output, existed


def hydrate(manifest: Path, output_dir: Path, partitions: set[str]) -> dict:
    rows = _manifest_rows(manifest)
    selected = [row for row in rows if row["partition"] in partitions]
    cache: dict[str, bytes] = {}
    reused = 0
    partition_counts = {key: 0 for key in sorted(partitions)}
    for index, row in enumerate(selected, start=1):
        url = row["source_url_or_access_reference"]
        payload = cache.get(url)
        if payload is None:
            payload = download(url)
            cache[url] = payload
        _, existed = materialize_row(row, payload, output_dir)
        reused += int(existed)
        partition_counts[row["partition"]] += 1
        print(f"[{index}/{len(selected)}] verified {row['partition']} {row['record_id']}")
    return {
        "status": "PASS",
        "manifest_sha256": EXPECTED_MANIFEST_SHA256,
        "records_verified": len(selected),
        "partition_counts": partition_counts,
        "unique_access_requests": len(cache),
        "existing_verified_files_reused": reused,
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
        args.audit_out.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"Frozen ESM hydration: PASS ({evidence['records_verified']} records)")
        print(f"Audit: {args.audit_out}")
        return 0
    except Exception as exc:
        failure = {"status": "BLOCKED", "error": str(exc)}
        args.audit_out.parent.mkdir(parents=True, exist_ok=True)
        args.audit_out.write_text(json.dumps(failure, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"Frozen ESM hydration: BLOCKED\n- {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
