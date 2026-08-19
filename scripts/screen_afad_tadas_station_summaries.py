#!/usr/bin/env python3
"""Screen AFAD/TADAS station-summary exports in frozen event order.

This is provenance/data-selection infrastructure only. Station-summary PGA is used as a
necessary-condition prescreen; final eligibility remains component-level and must be
established from audited HNE/HNN raw records.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import time
from typing import Iterable

if __package__:
    from scripts.ground_motion_manifest import STANDARD_GRAVITY_M_S2
else:
    from ground_motion_manifest import STANDARD_GRAVITY_M_S2

TADAS_WAVEFORM_SEARCH_URL = "https://tadas.afad.gov.tr/list-waveform"
DEFAULT_OUT_DIR = Path("results/local/afad_tadas")
DEFAULT_PROFILE_DIR = Path("data/private/tadas-browser-profile")
MIN_PGA_CM_S2 = 0.15 * STANDARD_GRAVITY_M_S2 * 100.0
RECORDS_PER_EVENT = 4
MAX_HORIZONTAL_COMPONENTS_PER_STATION = 2
MIN_STATIONS_NEEDED = math.ceil(RECORDS_PER_EVENT / MAX_HORIZONTAL_COMPONENTS_PER_STATION)
FINAL_SCREEN_STATUSES = {"REJECT_SUMMARY_PGA", "CANDIDATE_COMPONENT_AUDIT"}
LEDGER_COLUMNS = (
    "rank", "event_hash", "event_id", "event_date_from_export",
    "summary_csv_sha256", "summary_row_count", "unique_station_count",
    "stations_at_or_above_threshold", "max_summary_pga_cm_s2",
    "threshold_cm_s2", "required_candidate_stations", "status", "reason",
    "source_reference", "summary_csv_path", "screened_at_utc",
)

SUMMARY_ALIASES = {
    "event_id": ("eventid", "event_id"),
    "station_code": ("stationcode", "station_code", "stationid", "station_id"),
    "pga": ("pga", "pgacms2", "pga_cm_s2", "pga_cm_s_2"),
}


def _header_key(value: str) -> str:
    return "".join(char.lower() for char in value.strip() if char.isalnum() or char == "_")


def _field_map(fieldnames: Iterable[str] | None) -> dict[str, str]:
    normalized = {_header_key(name): name for name in (fieldnames or ())}
    mapping: dict[str, str] = {}
    for field, aliases in SUMMARY_ALIASES.items():
        hit = next((normalized[alias] for alias in aliases if alias in normalized), None)
        if hit is None:
            raise ValueError(f"TADAS station-summary CSV is missing required field {field!r}")
        mapping[field] = hit
    return mapping


def _dict_reader(text: str) -> csv.DictReader:
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    return csv.DictReader(text.splitlines(), dialect=dialect)


@dataclass(frozen=True)
class SummaryScreen:
    summary_csv_sha256: str
    summary_row_count: int
    unique_station_count: int
    stations_at_or_above_threshold: int
    max_summary_pga_cm_s2: float
    threshold_cm_s2: float
    required_candidate_stations: int
    status: str
    reason: str


def screen_station_summary_csv(path: Path, expected_event_id: str) -> SummaryScreen:
    """Fail closed while using station-summary PGA only as a necessary-condition prescreen."""
    raw = path.read_bytes()
    text = raw.decode("utf-8-sig")
    reader = _dict_reader(text)
    fields = _field_map(reader.fieldnames)

    stations: set[str] = set()
    above = 0
    max_pga = 0.0
    rows = 0
    expected = str(expected_event_id).strip()
    if not expected:
        raise ValueError("expected_event_id must be nonblank")

    for line_number, row in enumerate(reader, 2):
        rows += 1
        event_id = (row.get(fields["event_id"]) or "").strip()
        if event_id != expected:
            raise ValueError(
                f"station-summary EventID mismatch at CSV line {line_number}: "
                f"expected {expected!r}, found {event_id!r}"
            )
        station = (row.get(fields["station_code"]) or "").strip()
        if not station:
            raise ValueError(f"blank station code at CSV line {line_number}")
        if station in stations:
            raise ValueError(f"duplicate station code {station!r} in station-summary CSV")
        stations.add(station)

        raw_pga = (row.get(fields["pga"]) or "").strip()
        try:
            pga = float(raw_pga)
        except ValueError as exc:
            raise ValueError(f"non-numeric PGA {raw_pga!r} at CSV line {line_number}") from exc
        if not math.isfinite(pga) or pga < 0:
            raise ValueError(f"invalid PGA {raw_pga!r} at CSV line {line_number}")
        max_pga = max(max_pga, pga)
        if pga >= MIN_PGA_CM_S2:
            above += 1

    if above < MIN_STATIONS_NEEDED:
        status = "REJECT_SUMMARY_PGA"
        reason = (
            f"only {above} station summaries reach {MIN_PGA_CM_S2:.5f} cm/s^2; "
            f"at least {MIN_STATIONS_NEEDED} stations are necessary for four eligible "
            "horizontal components"
        )
    else:
        status = "CANDIDATE_COMPONENT_AUDIT"
        reason = (
            f"{above} station summaries reach {MIN_PGA_CM_S2:.5f} cm/s^2; "
            "station-summary PGA is not component eligibility, so HNE/HNN raw audit is required"
        )

    return SummaryScreen(
        summary_csv_sha256=hashlib.sha256(raw).hexdigest(),
        summary_row_count=rows,
        unique_station_count=len(stations),
        stations_at_or_above_threshold=above,
        max_summary_pga_cm_s2=max_pga,
        threshold_cm_s2=MIN_PGA_CM_S2,
        required_candidate_stations=MIN_STATIONS_NEEDED,
        status=status,
        reason=reason,
    )


def parse_export_event_datetime(value: str) -> datetime:
    compact = " ".join(str(value).split())
    for fmt in ("%d-%m-%Y %H:%M", "%d-%m-%Y %H:%M:%S"):
        try:
            return datetime.strptime(compact, fmt)
        except ValueError:
            pass
    raise ValueError(f"unsupported TADAS EventDate format: {value!r}")


def date_window(value: str, pad_days: int = 1) -> tuple[str, str]:
    if pad_days < 0:
        raise ValueError("pad_days must be >= 0")
    event_dt = parse_export_event_datetime(value)
    start = event_dt.date() - timedelta(days=pad_days)
    end = event_dt.date() + timedelta(days=pad_days)
    return (
        f"{start.strftime('%d-%m-%Y')} 00:00:00",
        f"{end.strftime('%d-%m-%Y')} 23:59:59",
    )


def read_queue(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = [{key: (value or "").strip() for key, value in row.items()}
                for row in csv.DictReader(handle)]
    required = {"rank", "event_hash", "source", "event_id", "event_date_from_export"}
    if not rows:
        raise ValueError("event candidate queue is empty")
    missing = required - set(rows[0])
    if missing:
        raise ValueError(f"event candidate queue is missing columns: {', '.join(sorted(missing))}")
    for row in rows:
        if row["source"] != "AFAD_TADAS":
            raise ValueError(f"unexpected queue source {row['source']!r}")
    ranks = [int(row["rank"]) for row in rows]
    if ranks != list(range(1, len(rows) + 1)):
        raise ValueError("event candidate queue ranks are not contiguous from 1")
    return rows


def load_ledger(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        return {
            (row.get("event_id") or "").strip(): row
            for row in csv.DictReader(handle)
            if (row.get("event_id") or "").strip()
        }


def write_ledger(path: Path, entries: dict[str, dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    rows = sorted(entries.values(), key=lambda row: int(row["rank"]))
    with temp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=LEDGER_COLUMNS, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    temp.replace(path)


def _screen_entry(queue_row: dict[str, str], summary_path: Path) -> dict[str, object]:
    screen = screen_station_summary_csv(summary_path, queue_row["event_id"])
    return {
        "rank": int(queue_row["rank"]),
        "event_hash": queue_row["event_hash"],
        "event_id": queue_row["event_id"],
        "event_date_from_export": queue_row["event_date_from_export"],
        **asdict(screen),
        "source_reference": TADAS_WAVEFORM_SEARCH_URL,
        "summary_csv_path": str(summary_path),
        "screened_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


def _error_entry(queue_row: dict[str, str], reason: str) -> dict[str, object]:
    return {
        "rank": int(queue_row["rank"]),
        "event_hash": queue_row["event_hash"],
        "event_id": queue_row["event_id"],
        "event_date_from_export": queue_row["event_date_from_export"],
        "summary_csv_sha256": "",
        "summary_row_count": "",
        "unique_station_count": "",
        "stations_at_or_above_threshold": "",
        "max_summary_pga_cm_s2": "",
        "threshold_cm_s2": MIN_PGA_CM_S2,
        "required_candidate_stations": MIN_STATIONS_NEEDED,
        "status": "ERROR",
        "reason": reason,
        "source_reference": TADAS_WAVEFORM_SEARCH_URL,
        "summary_csv_path": "",
        "screened_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


def _load_selector_overrides(path: Path | None) -> dict[str, str]:
    if path is None:
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in data.items()):
        raise ValueError("selector override JSON must be an object of string keys and string selectors")
    return data


class TadasPlaywrightBrowser:
    """Headed, authenticated browser helper; never stores or asks for credentials."""

    INPUT_TERMS = {
        "event_id": ("event id", "eventid", "event", "deprem id", "olay id"),
        "start_date": ("start date", "start", "başlangıç", "baslangic", "from date"),
        "end_date": ("end date", "end", "bitiş", "bitis", "to date", "until"),
    }

    def __init__(
        self,
        profile_dir: Path,
        download_dir: Path,
        *,
        headless: bool,
        timeout_ms: int,
        selectors: dict[str, str],
    ) -> None:
        self.profile_dir = profile_dir
        self.download_dir = download_dir
        self.headless = headless
        self.timeout_ms = timeout_ms
        self.selectors = selectors
        self._pw = None
        self.context = None
        self.page = None

    def __enter__(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                'Playwright is not installed. Run: pip install -e ".[tadas]" '
                "and then: playwright install chromium"
            ) from exc

        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self._pw = sync_playwright().start()
        self.context = self._pw.chromium.launch_persistent_context(
            user_data_dir=str(self.profile_dir),
            headless=self.headless,
            accept_downloads=True,
        )
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        self.page.set_default_timeout(self.timeout_ms)
        self._ensure_authenticated()
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.context is not None:
            self.context.close()
        if self._pw is not None:
            self._pw.stop()

    def _ensure_authenticated(self) -> None:
        assert self.page is not None
        self.page.goto(TADAS_WAVEFORM_SEARCH_URL, wait_until="domcontentloaded")
        self.page.wait_for_timeout(1000)
        # Login buttons may remain in the site chrome even when the waveform form is usable,
        # so form availability—not button text—is the authentication/session signal.
        needs_login = "/login" in self.page.url.lower() or self.page.locator("input:visible").count() < 3
        if not needs_login:
            return
        if self.headless:
            raise RuntimeError(
                "TADAS waveform search is not available in the saved session and browser is "
                "headless. Run once in headed mode and complete login manually; credentials "
                "are never requested or stored by this script."
            )
        print("\nTADAS waveform search is not yet available.")
        print("Complete Guest/Staff login manually in the opened browser.")
        print("Do not paste credentials into this terminal.")
        input("After the waveform search page is available, press Enter here to continue: ")
        self.page.goto(TADAS_WAVEFORM_SEARCH_URL, wait_until="domcontentloaded")
        self.page.wait_for_timeout(1000)
        if self.page.locator("input:visible").count() < 3:
            raise RuntimeError("TADAS waveform search form is still unavailable after manual login")

    @staticmethod
    def _descriptor(locator) -> str:
        try:
            data = locator.evaluate(
                """el => ({
                    id: el.id || '',
                    name: el.getAttribute('name') || '',
                    placeholder: el.getAttribute('placeholder') || '',
                    aria: el.getAttribute('aria-label') || '',
                    title: el.getAttribute('title') || '',
                    label: el.labels ? Array.from(el.labels).map(x => x.innerText || '').join(' ') : '',
                    parent: el.parentElement ? (el.parentElement.innerText || '').slice(0, 240) : ''
                })"""
            )
        except Exception:
            return ""
        return " ".join(str(data.get(key, "")) for key in ("id", "name", "placeholder", "aria", "title", "label", "parent")).lower()

    def _input(self, kind: str):
        assert self.page is not None
        override = self.selectors.get(kind)
        if override:
            locator = self.page.locator(override).first
            if locator.count() == 0:
                raise RuntimeError(f"selector override for {kind!r} matched no element: {override!r}")
            return locator

        terms = self.INPUT_TERMS[kind]
        inputs = self.page.locator("input:visible")
        scored = []
        for index in range(inputs.count()):
            locator = inputs.nth(index)
            descriptor = self._descriptor(locator)
            score = sum(4 if term in descriptor else 0 for term in terms)
            # Date fields often share a date/time placeholder; parent label breaks the tie.
            if kind in {"start_date", "end_date"} and re.search(r"\d{2}[-/.]\d{2}[-/.]\d{4}|date|tarih", descriptor):
                score += 1
            if kind == "event_id" and "id" in descriptor:
                score += 1
            if score:
                scored.append((score, index, descriptor))
        if not scored:
            raise RuntimeError(
                f"could not identify {kind} input. Provide a CSS selector in --selectors-json."
            )
        scored.sort(key=lambda item: (-item[0], item[1]))
        if len(scored) > 1 and scored[0][0] == scored[1][0]:
            raise RuntimeError(
                f"ambiguous {kind} input. Provide a CSS selector in --selectors-json."
            )
        return inputs.nth(scored[0][1])

    def _action(self, kind: str, terms: tuple[str, ...]):
        assert self.page is not None
        override = self.selectors.get(kind)
        if override:
            locator = self.page.locator(override).first
            if locator.count() == 0:
                raise RuntimeError(f"selector override for {kind!r} matched no element: {override!r}")
            return locator

        candidates = self.page.locator(
            "button:visible, [role='button']:visible, a:visible, input[type='submit']:visible"
        )
        scored = []
        for index in range(candidates.count()):
            locator = candidates.nth(index)
            try:
                text = " ".join(
                    filter(None, (
                        locator.inner_text().strip(),
                        locator.get_attribute("aria-label") or "",
                        locator.get_attribute("title") or "",
                        locator.get_attribute("value") or "",
                    ))
                ).lower()
            except Exception:
                continue
            score = max((10 if text.strip() == term else 4 if term in text else 0) for term in terms)
            if score:
                scored.append((score, index, text))
        if not scored:
            raise RuntimeError(
                f"could not identify {kind} control. Provide a CSS selector in --selectors-json."
            )
        scored.sort(key=lambda item: (-item[0], item[1]))
        return candidates.nth(scored[0][1])

    def download_station_summary(
        self, queue_row: dict[str, str], destination: Path, *, pad_days: int
    ) -> None:
        assert self.page is not None
        event_id = queue_row["event_id"]
        start, end = date_window(queue_row["event_date_from_export"], pad_days=pad_days)

        self.page.goto(TADAS_WAVEFORM_SEARCH_URL, wait_until="domcontentloaded")
        self._input("event_id").fill(event_id)
        self._input("start_date").fill(start)
        self._input("end_date").fill(end)
        self._action("search_button", ("search", "query", "sorgula", "ara")).click()
        try:
            self.page.wait_for_load_state("networkidle", timeout=min(self.timeout_ms, 15000))
        except Exception:
            self.page.wait_for_timeout(1500)

        try:
            csv_button = self._action("csv_button", ("csv",))
        except RuntimeError:
            try:
                self._action("export_button", ("export", "dışa aktar", "disa aktar")).click()
                self.page.wait_for_timeout(500)
                csv_button = self._action("csv_button", ("csv",))
            except RuntimeError as exc:
                raise RuntimeError("CSV export control was not found after search") from exc

        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self.page.expect_download(timeout=self.timeout_ms) as download_info:
                csv_button.click()
            download = download_info.value
            download.save_as(str(destination))
        except Exception as exc:
            raise RuntimeError(f"CSV download failed for EventID {event_id}: {exc}") from exc


def run_browser_screening(args: argparse.Namespace) -> int:
    queue = read_queue(args.queue)
    selectors = _load_selector_overrides(args.selectors_json)
    out_dir: Path = args.out_dir
    summary_dir = out_dir / "station_summaries"
    ledger_path = out_dir / "station_summary_screen.csv"
    screenshot_dir = out_dir / "browser_errors"
    existing = load_ledger(ledger_path)
    entries: dict[str, dict[str, object]] = {
        event_id: dict(row) for event_id, row in existing.items()
    }

    final_candidate_count = sum(
        1 for row in entries.values() if row.get("status") == "CANDIDATE_COMPONENT_AUDIT"
    )
    consecutive_errors = 0

    with TadasPlaywrightBrowser(
        args.profile_dir, summary_dir,
        headless=args.headless,
        timeout_ms=args.timeout_ms,
        selectors=selectors,
    ) as browser:
        for row in queue:
            rank = int(row["rank"])
            if rank < args.start_rank:
                continue
            if args.end_rank and rank > args.end_rank:
                break
            prior = existing.get(row["event_id"])
            if prior and prior.get("status") in FINAL_SCREEN_STATUSES:
                continue
            if prior and prior.get("status") == "ERROR" and args.skip_errors:
                continue
            if args.stop_after_candidates and final_candidate_count >= args.stop_after_candidates:
                break

            destination = summary_dir / f"{rank:05d}_{row['event_id']}.csv"
            print(f"[rank {rank}] EventID {row['event_id']} ...", flush=True)
            try:
                browser.download_station_summary(row, destination, pad_days=args.pad_days)
                entry = _screen_entry(row, destination)
                consecutive_errors = 0
                if entry["status"] == "CANDIDATE_COMPONENT_AUDIT":
                    final_candidate_count += 1
                print(
                    f"  {entry['status']}: max summary PGA="
                    f"{float(entry['max_summary_pga_cm_s2']):.6g} cm/s^2, "
                    f"stations above threshold={entry['stations_at_or_above_threshold']}"
                )
            except Exception as exc:
                consecutive_errors += 1
                entry = _error_entry(row, str(exc))
                screenshot_dir.mkdir(parents=True, exist_ok=True)
                try:
                    assert browser.page is not None
                    browser.page.screenshot(
                        path=str(screenshot_dir / f"{rank:05d}_{row['event_id']}.png"),
                        full_page=True,
                    )
                except Exception:
                    pass
                print(f"  ERROR: {exc}")
            entries[row["event_id"]] = entry
            write_ledger(ledger_path, entries)

            if consecutive_errors >= args.max_consecutive_errors:
                raise RuntimeError(
                    f"aborting after {consecutive_errors} consecutive browser/download errors"
                )
            if args.delay_s > 0:
                time.sleep(args.delay_s)

    print(f"Ledger: {ledger_path}")
    print(f"Component-audit candidates accumulated: {final_candidate_count}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("queue", type=Path, help="deterministic event_candidate_queue.csv")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--profile-dir", type=Path, default=DEFAULT_PROFILE_DIR)
    parser.add_argument("--selectors-json", type=Path)
    parser.add_argument("--start-rank", type=int, default=1)
    parser.add_argument("--end-rank", type=int, default=0, help="0 means no rank limit")
    parser.add_argument("--stop-after-candidates", type=int, default=80, help="0 means no candidate limit")
    parser.add_argument("--pad-days", type=int, default=1)
    parser.add_argument("--delay-s", type=float, default=4.0)
    parser.add_argument("--timeout-ms", type=int, default=30000)
    parser.add_argument("--max-consecutive-errors", type=int, default=3)
    parser.add_argument("--skip-errors", action="store_true")
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()

    if args.start_rank < 1:
        parser.error("--start-rank must be >= 1")
    if args.end_rank < 0:
        parser.error("--end-rank must be >= 0")
    if args.stop_after_candidates < 0:
        parser.error("--stop-after-candidates must be >= 0")
    if args.pad_days < 0:
        parser.error("--pad-days must be >= 0")
    if args.delay_s < 0:
        parser.error("--delay-s must be >= 0")
    if args.max_consecutive_errors < 1:
        parser.error("--max-consecutive-errors must be >= 1")

    try:
        return run_browser_screening(args)
    except (OSError, ValueError, RuntimeError) as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
