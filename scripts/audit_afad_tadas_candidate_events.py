#!/usr/bin/env python3
"""Download and audit raw AFAD/TADAS ZIPs for station-summary candidate events.

This is provenance/data-selection infrastructure only. It consumes candidate artifacts from
``screen_afad_tadas_backend.py`` produced under the corrected query contract
``event-specific;fromMagnitude=null``. It does not run confirmatory simulations and it does
not make raw AFAD bytes public.

The script uses a separate persistent browser profile so it can run while the backend
station-summary screener is still using its own browser profile. Guest/Staff login, if needed,
is completed manually in the opened browser; credentials are never requested by this script.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import time
import zipfile

if __package__:
    from scripts.audit_afad_tadas_raw_zip import audit_zip, write_audit
    from scripts.ground_motion_manifest import AFAD_TADAS_SOURCE, sha_key
    from scripts.screen_afad_tadas_backend import QUERY_CONTRACT
    from scripts.screen_afad_tadas_station_summaries import MIN_PGA_CM_S2
    from scripts.tadas_kendo_adapter import KendoTadasPlaywrightBrowser
else:
    from audit_afad_tadas_raw_zip import audit_zip, write_audit
    from ground_motion_manifest import AFAD_TADAS_SOURCE, sha_key
    from screen_afad_tadas_backend import QUERY_CONTRACT
    from screen_afad_tadas_station_summaries import MIN_PGA_CM_S2
    from tadas_kendo_adapter import KendoTadasPlaywrightBrowser

DEFAULT_SCREEN_LEDGER = Path("results/local/afad_tadas/station_summary_backend_screen_nomag.csv")
DEFAULT_CANDIDATE_DIR = Path("data/private/tadas-backend-candidates-nomag")
DEFAULT_PROFILE_DIR = Path("data/private/tadas-component-audit-browser-profile")
DEFAULT_RAW_DIR = Path("data/private/tadas-raw-zips-nomag")
DEFAULT_AUDIT_DIR = Path("results/local/afad_tadas/component_raw_audits_nomag")
DEFAULT_EVENT_LEDGER = Path("results/local/afad_tadas/component_event_audit_nomag.csv")
DETAIL_URL_TEMPLATE = "https://tadas.afad.gov.tr/waveform-detail/{waveform_id}"
FINAL_EVENT_STATUSES = {
    "ELIGIBLE_EVENT_COMPONENT_AUDIT",
    "REJECT_COMPONENT_AUDIT",
}
EVENT_LEDGER_COLUMNS = (
    "rank",
    "event_id",
    "query_contract",
    "candidate_station_count",
    "waveform_details_audited",
    "pass_horizontal_component_count",
    "selected_record_ids",
    "selected_record_hashes",
    "status",
    "reason",
    "audited_at_utc",
)


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _digits(value: object, field: str) -> str:
    text = str(value if value is not None else "").strip()
    if not re.fullmatch(r"[0-9]+", text):
        raise ValueError(f"{field} must be an ASCII decimal digit string, found {text!r}")
    return text


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [{k: (v or "").strip() for k, v in row.items()} for row in csv.DictReader(handle)]


def _load_event_ledger(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    rows = _read_csv(path)
    entries: dict[str, dict[str, str]] = {}
    for row in rows:
        event_id = row.get("event_id", "").strip()
        if not event_id:
            continue
        if row.get("query_contract") != QUERY_CONTRACT:
            raise ValueError(
                f"event-audit ledger {path} contains stale/unknown query contract for EventID "
                f"{event_id}: {row.get('query_contract')!r}"
            )
        entries[event_id] = row
    return entries


def _write_event_ledger(path: Path, entries: dict[str, dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=EVENT_LEDGER_COLUMNS, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(sorted(entries.values(), key=lambda row: int(row["rank"])))
    tmp.replace(path)


def candidate_rows_from_artifact(path: Path, event_id: str) -> list[dict[str, object]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"candidate artifact {path} is not an object")
    if data.get("query_contract") != QUERY_CONTRACT:
        raise ValueError(
            f"candidate artifact {path} has stale/unknown query contract {data.get('query_contract')!r}"
        )
    if str(data.get("event_id", "")).strip() != event_id:
        raise ValueError(f"candidate artifact EventID mismatch for {path}")
    rows = data.get("rows_at_or_above_threshold")
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"candidate artifact {path} has no rows_at_or_above_threshold")

    normalized: list[dict[str, object]] = []
    seen_waveforms: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"candidate artifact row {index} is not an object")
        if str(row.get("eaEventId", "")).strip() != event_id:
            raise ValueError(f"candidate artifact row {index} EventID mismatch")
        waveform_id = _digits(row.get("waveformId"), "waveformId")
        if waveform_id in seen_waveforms:
            raise ValueError(f"candidate artifact repeats waveformId {waveform_id}")
        seen_waveforms.add(waveform_id)
        station_code = str(row.get("stationCode", "")).strip()
        if not station_code:
            raise ValueError(f"candidate artifact row {index} has blank stationCode")
        try:
            pga = float(row.get("pga"))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"candidate artifact row {index} has non-numeric pga") from exc
        if pga < MIN_PGA_CM_S2:
            raise ValueError(
                f"candidate artifact row {index} PGA {pga} is below frozen station-summary threshold"
            )
        normalized.append({
            "waveform_id": waveform_id,
            "station_code": station_code,
            "station_summary_pga_cm_s2": pga,
            "detail_url": DETAIL_URL_TEMPLATE.format(waveform_id=waveform_id),
        })
    return normalized


def snapshot_candidates(screen_ledger: Path, candidate_dir: Path) -> list[dict[str, object]]:
    rows = _read_csv(screen_ledger)
    candidates: list[dict[str, object]] = []
    for row in rows:
        if row.get("status") != "CANDIDATE_COMPONENT_AUDIT":
            continue
        if row.get("query_contract") != QUERY_CONTRACT:
            raise ValueError(
                f"screen ledger EventID {row.get('event_id')} has stale/unknown query contract "
                f"{row.get('query_contract')!r}"
            )
        event_id = _digits(row.get("event_id"), "event_id")
        rank = int(row["rank"])
        candidate_path_text = row.get("candidate_json_path", "").strip()
        candidate_path = Path(candidate_path_text) if candidate_path_text else (
            candidate_dir / f"rank-{rank:05d}-event-{event_id}.json"
        )
        if not candidate_path.exists():
            raise FileNotFoundError(f"candidate artifact is missing: {candidate_path}")
        station_rows = candidate_rows_from_artifact(candidate_path, event_id)
        candidates.append({
            "rank": rank,
            "event_id": event_id,
            "candidate_path": candidate_path,
            "station_rows": station_rows,
        })
    candidates.sort(key=lambda item: int(item["rank"]))
    return candidates


def _clickable_descriptor(locator) -> str:
    try:
        data = locator.evaluate(
            """el => ({
                text: (el.innerText || el.textContent || '').trim(),
                href: el.getAttribute('href') || '',
                title: el.getAttribute('title') || '',
                aria: el.getAttribute('aria-label') || '',
                download: el.getAttribute('download') || '',
                onclick: el.getAttribute('onclick') || ''
            })"""
        )
    except Exception:
        return ""
    return " ".join(str(data.get(key, "")) for key in ("text", "href", "title", "aria", "download", "onclick")).strip()


def _download_priority(descriptor: str) -> int | None:
    text = descriptor.lower()
    if any(token in text for token in ("raw data", "ham veri", "raw-data", "raw_data")):
        return 0
    if "dyna" in text or "ascii" in text:
        return 1
    if "raw" in text:
        return 2
    if "download" in text or "indir" in text:
        return 3
    return None


def discover_download_controls(page) -> list[tuple[int, int, str]]:
    locator = page.locator("a:visible, button:visible, [role=button]:visible")
    ranked: list[tuple[int, int, str]] = []
    for index in range(locator.count()):
        descriptor = _clickable_descriptor(locator.nth(index))
        priority = _download_priority(descriptor)
        if priority is not None:
            ranked.append((priority, index, descriptor[:500]))
    ranked.sort(key=lambda item: (item[0], item[1]))
    return ranked


def download_raw_zip(page, waveform_id: str, target: Path, timeout_ms: int) -> tuple[str, str]:
    """Best-effort headed download using the real waveform-detail page; fail closed on ambiguity."""
    detail_url = DETAIL_URL_TEMPLATE.format(waveform_id=waveform_id)
    page.goto(detail_url, wait_until="domcontentloaded")
    page.wait_for_timeout(800)
    controls = discover_download_controls(page)
    if not controls:
        raise RuntimeError(f"no Raw Data/download control discovered at {detail_url}")

    last_errors: list[str] = []
    all_clickables = page.locator("a:visible, button:visible, [role=button]:visible")
    for _, index, descriptor in controls[:8]:
        control = all_clickables.nth(index)
        try:
            with page.expect_download(timeout=min(timeout_ms, 8000)) as info:
                control.click()
            download = info.value
            suggested = download.suggested_filename or f"waveform-{waveform_id}.zip"
            target.parent.mkdir(parents=True, exist_ok=True)
            download.save_as(str(target))
            if not target.exists() or not zipfile.is_zipfile(target):
                target.unlink(missing_ok=True)
                raise RuntimeError(f"downloaded file from {detail_url} is not a ZIP archive")
            return detail_url, suggested
        except Exception as exc:
            last_errors.append(f"{descriptor[:120]!r}: {exc}")
            # A failed click can navigate or mutate the page; restore the detail page before retrying.
            page.goto(detail_url, wait_until="domcontentloaded")
            page.wait_for_timeout(500)
            all_clickables = page.locator("a:visible, button:visible, [role=button]:visible")
    raise RuntimeError(
        f"unable to trigger raw ZIP download at {detail_url}; tried {min(len(controls),8)} controls; "
        + " | ".join(last_errors[-3:])
    )


def _eligible_horizontal_components(audit: dict[str, object]) -> list[dict[str, object]]:
    components = audit.get("components")
    if not isinstance(components, list):
        raise ValueError("raw audit components are missing")
    return [
        component for component in components
        if isinstance(component, dict)
        and component.get("stream") in {"HNE", "HNN"}
        and component.get("eligibility_status") == "PASS"
    ]


def choose_frozen_records(event_id: str, components: list[dict[str, object]]) -> list[dict[str, object]]:
    decorated = []
    seen: set[str] = set()
    for component in components:
        record_id = str(component.get("record_id", "")).strip()
        if not record_id:
            raise ValueError("PASS horizontal component has blank record_id")
        if record_id in seen:
            raise ValueError(f"duplicate PASS record_id {record_id}")
        seen.add(record_id)
        key = sha_key("record", {
            "source": AFAD_TADAS_SOURCE,
            "event_id": event_id,
            "record_id": record_id,
        })
        decorated.append((key, component))
    decorated.sort(key=lambda pair: pair[0])
    return [component | {"record_hash": key} for key, component in decorated[:4]]


def audit_one_event(browser, candidate: dict[str, object], raw_dir: Path, audit_dir: Path,
                    timeout_ms: int, delay_s: float) -> dict[str, object]:
    page = browser.page
    assert page is not None
    rank = int(candidate["rank"])
    event_id = str(candidate["event_id"])
    station_rows = candidate["station_rows"]
    assert isinstance(station_rows, list)

    pass_components: list[dict[str, object]] = []
    errors: list[str] = []
    audited_waveforms = 0
    for station in station_rows:
        assert isinstance(station, dict)
        waveform_id = str(station["waveform_id"])
        zip_path = raw_dir / f"rank-{rank:05d}-event-{event_id}" / f"waveform-{waveform_id}.zip"
        source_reference = DETAIL_URL_TEMPLATE.format(waveform_id=waveform_id)
        audit_path = audit_dir / f"rank-{rank:05d}-event-{event_id}" / f"waveform-{waveform_id}.json"
        print(
            f"    waveform {waveform_id} station {station['station_code']} "
            f"summaryPGA={float(station['station_summary_pga_cm_s2']):.6g} ..."
        )
        try:
            if not zip_path.exists():
                download_raw_zip(page, waveform_id, zip_path, timeout_ms)
            if not zipfile.is_zipfile(zip_path):
                raise RuntimeError(f"cached raw file is not a ZIP archive: {zip_path}")
            audit = audit_zip(zip_path, event_id, waveform_id, source_reference)
            write_audit(audit, audit_path)
            horizontals = _eligible_horizontal_components(audit)
            pass_components.extend(horizontals)
            audited_waveforms += 1
            print(
                f"      audited: PASS horizontals={len(horizontals)}; "
                f"streams={[c.get('stream') for c in horizontals]}"
            )
        except Exception as exc:
            errors.append(f"waveform {waveform_id}: {exc}")
            print(f"      ERROR: {exc}")
        if delay_s:
            time.sleep(delay_s)

    if errors:
        status = "ERROR_INCOMPLETE_COMPONENT_AUDIT"
        reason = "; ".join(errors)
        selected: list[dict[str, object]] = []
    else:
        selected = choose_frozen_records(event_id, pass_components)
        if len(pass_components) >= 4:
            status = "ELIGIBLE_EVENT_COMPONENT_AUDIT"
            reason = (
                f"{len(pass_components)} horizontal raw components pass all frozen raw checks; "
                "first four by frozen salted record hash selected"
            )
        else:
            status = "REJECT_COMPONENT_AUDIT"
            reason = (
                f"only {len(pass_components)} horizontal raw components pass all frozen raw checks; "
                "four are required"
            )

    return {
        "rank": rank,
        "event_id": event_id,
        "query_contract": QUERY_CONTRACT,
        "candidate_station_count": len(station_rows),
        "waveform_details_audited": audited_waveforms,
        "pass_horizontal_component_count": len(pass_components),
        "selected_record_ids": ";".join(str(c["record_id"]) for c in selected),
        "selected_record_hashes": ";".join(str(c["record_hash"]) for c in selected),
        "status": status,
        "reason": reason,
        "audited_at_utc": _now_utc(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screen-ledger", type=Path, default=DEFAULT_SCREEN_LEDGER)
    parser.add_argument("--candidate-dir", type=Path, default=DEFAULT_CANDIDATE_DIR)
    parser.add_argument("--profile-dir", type=Path, default=DEFAULT_PROFILE_DIR)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--audit-dir", type=Path, default=DEFAULT_AUDIT_DIR)
    parser.add_argument("--event-ledger", type=Path, default=DEFAULT_EVENT_LEDGER)
    parser.add_argument("--max-events", type=int, default=0, help="0 means all snapshot candidates")
    parser.add_argument("--timeout-ms", type=int, default=30000)
    parser.add_argument("--delay-s", type=float, default=0.25)
    parser.add_argument("--prepare-only", action="store_true", help="print snapshot candidates without browser/downloads")
    args = parser.parse_args()

    if not args.screen_ledger.exists():
        parser.error(f"screen ledger not found: {args.screen_ledger}")
    if args.max_events < 0:
        parser.error("--max-events must be >= 0")
    if args.delay_s < 0:
        parser.error("--delay-s must be >= 0")

    candidates = snapshot_candidates(args.screen_ledger, args.candidate_dir)
    print(f"Snapshot candidates under corrected query contract: {len(candidates)}")
    for candidate in candidates:
        print(
            f"  rank {candidate['rank']} EventID {candidate['event_id']}: "
            f"station waveform details={len(candidate['station_rows'])}"
        )
    if args.prepare_only:
        return 0

    event_entries = _load_event_ledger(args.event_ledger)
    pending = [
        candidate for candidate in candidates
        if event_entries.get(str(candidate["event_id"]), {}).get("status") not in FINAL_EVENT_STATUSES
    ]
    if args.max_events:
        pending = pending[: args.max_events]
    if not pending:
        print("No pending snapshot candidate events to audit.")
        return 0

    # Separate profile intentionally avoids locking/conflicting with the concurrently-running
    # station-summary screener profile.
    with KendoTadasPlaywrightBrowser(
        args.profile_dir,
        Path("data/private/tadas-component-audit-bootstrap-downloads"),
        headless=False,
        timeout_ms=args.timeout_ms,
        selectors={},
    ) as browser:
        for candidate in pending:
            print(f"[component audit] rank {candidate['rank']} EventID {candidate['event_id']} ...")
            entry = audit_one_event(
                browser, candidate, args.raw_dir, args.audit_dir, args.timeout_ms, args.delay_s
            )
            event_entries[str(candidate["event_id"])] = entry
            _write_event_ledger(args.event_ledger, event_entries)
            print(
                f"  {entry['status']}: pass horizontals={entry['pass_horizontal_component_count']}; "
                f"selected={entry['selected_record_ids'] or '-'}"
            )

    eligible = sum(row.get("status") == "ELIGIBLE_EVENT_COMPONENT_AUDIT" for row in event_entries.values())
    rejected = sum(row.get("status") == "REJECT_COMPONENT_AUDIT" for row in event_entries.values())
    errors = sum(row.get("status") == "ERROR_INCOMPLETE_COMPONENT_AUDIT" for row in event_entries.values())
    print(f"Event component-audit ledger: {args.event_ledger}")
    print(f"Eligible events accumulated: {eligible}")
    print(f"Rejected events accumulated: {rejected}")
    print(f"Incomplete/error events: {errors}")
    print("Raw AFAD ZIPs remain under data/private and are not publication artifacts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
