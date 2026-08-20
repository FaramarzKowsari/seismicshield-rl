#!/usr/bin/env python3
"""Run the candidate component auditor with the verified TADAS raw-download UI path.

TADAS waveform-detail pages open on the Detail tab. The real raw ASCII download control
exists on the Waveform tab and is hidden until that tab is opened. This wrapper replaces the
older heuristic downloader at runtime with the verified sequence:

1. open the exact waveform-detail URL;
2. open the Waveform tab;
3. locate the exact ``Download Raw Data (ASCII)`` button;
4. wait for the browser download event;
5. save the ZIP under the private raw-data directory and verify that it is a ZIP.

No scientific eligibility criterion, threshold, hash ordering, manifest rule, or OSF gate is
changed. Raw bytes remain private/local.
"""
from __future__ import annotations

from pathlib import Path
import zipfile

if __package__:
    from scripts import audit_afad_tadas_candidate_events as base
else:
    import audit_afad_tadas_candidate_events as base

WAVEFORM_TAB_SELECTOR = 'a[href="#waveform-detail-tab-2"]'
RAW_BUTTON_NAME = "Download Raw Data (ASCII)"


def download_raw_zip(page, waveform_id: str, target: Path, timeout_ms: int) -> tuple[str, str]:
    """Download one raw ASCII ZIP through the verified TADAS Waveform-tab control."""
    detail_url = base.DETAIL_URL_TEMPLATE.format(waveform_id=waveform_id)
    page.goto(detail_url, wait_until="domcontentloaded")
    page.wait_for_timeout(900)

    tab = page.locator(WAVEFORM_TAB_SELECTOR)
    if tab.count() != 1:
        raise RuntimeError(
            f"expected exactly one Waveform tab at {detail_url}, found {tab.count()}"
        )
    tab.click()
    page.wait_for_timeout(700)

    button = page.get_by_role("button", name=RAW_BUTTON_NAME, exact=True)
    if button.count() != 1:
        raise RuntimeError(
            f"expected exactly one {RAW_BUTTON_NAME!r} button at {detail_url}, found {button.count()}"
        )
    button.wait_for(state="visible", timeout=timeout_ms)
    if button.is_disabled():
        raise RuntimeError(f"{RAW_BUTTON_NAME!r} is disabled at {detail_url}")

    with page.expect_download(timeout=timeout_ms) as info:
        button.click()
    download = info.value
    suggested = download.suggested_filename or f"waveform-{waveform_id}.zip"

    target.parent.mkdir(parents=True, exist_ok=True)
    download.save_as(str(target))
    if not target.exists() or not zipfile.is_zipfile(target):
        target.unlink(missing_ok=True)
        raise RuntimeError(f"downloaded raw file from {detail_url} is not a ZIP archive")
    return detail_url, suggested


def main() -> int:
    # Keep all frozen candidate ordering/audit/ledger logic in the canonical auditor; only
    # substitute the now-verified download transport.
    base.download_raw_zip = download_raw_zip
    return base.main()


if __name__ == "__main__":
    raise SystemExit(main())
