#!/usr/bin/env python3
"""Safely probe the real TADAS "Download Raw Data (ASCII)" action.

This diagnostic intentionally clicks the Waveform tab before locating the raw-download button,
then captures only sanitized request/response metadata produced by that click. Sensitive header
values are never persisted. The goal is to learn the real backend/download surface before
changing the component-audit downloader.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

if __package__:
    from scripts.audit_afad_tadas_candidate_events import DETAIL_URL_TEMPLATE, DEFAULT_PROFILE_DIR
    from scripts.probe_tadas_waveform_detail import (
        STATIC_TYPES,
        SENSITIVE_QUERY_RE,
        safe_headers,
        sanitize_url,
        sensitive_header_presence,
    )
    from scripts.tadas_kendo_adapter import KendoTadasPlaywrightBrowser
else:
    from audit_afad_tadas_candidate_events import DETAIL_URL_TEMPLATE, DEFAULT_PROFILE_DIR
    from probe_tadas_waveform_detail import (
        STATIC_TYPES,
        SENSITIVE_QUERY_RE,
        safe_headers,
        sanitize_url,
        sensitive_header_presence,
    )
    from tadas_kendo_adapter import KendoTadasPlaywrightBrowser

DEFAULT_OUT = Path("data/private/tadas-raw-download-trigger-probe.json")
RAW_BUTTON_NAME = "Download Raw Data (ASCII)"
WAVEFORM_TAB_SELECTOR = 'a[href="#waveform-detail-tab-2"]'


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def redact_json(value):
    """Recursively redact values whose JSON keys look credential/session-like."""
    if isinstance(value, dict):
        return {
            str(key): ("[REDACTED]" if SENSITIVE_QUERY_RE.search(str(key)) else redact_json(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_json(item) for item in value]
    return value


def safe_post_data(request):
    raw = request.post_data
    if not raw:
        return None
    content_type = str(request.headers.get("content-type", "")).lower()
    if "json" not in content_type:
        return "[NON_JSON_BODY_OMITTED]"
    try:
        return redact_json(json.loads(raw))
    except Exception:
        return "[UNPARSEABLE_JSON_BODY_OMITTED]"


def _button_descriptor(locator) -> dict[str, object]:
    return locator.evaluate(
        """el => ({
          tag: el.tagName || '',
          text: (el.innerText || el.textContent || '').trim(),
          className: typeof el.className === 'string' ? el.className : '',
          visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length),
          disabled: !!el.disabled,
          outerHTML: (el.outerHTML || '').slice(0, 1500)
        })"""
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--waveform-id", default="2136302")
    parser.add_argument("--profile-dir", type=Path, default=DEFAULT_PROFILE_DIR)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--timeout-ms", type=int, default=30000)
    parser.add_argument("--observe-ms", type=int, default=8000)
    args = parser.parse_args()

    waveform_id = str(args.waveform_id).strip()
    if not re.fullmatch(r"[0-9]+", waveform_id):
        parser.error("--waveform-id must be ASCII decimal digits")
    if args.observe_ms < 0:
        parser.error("--observe-ms must be >= 0")

    detail_url = DETAIL_URL_TEMPLATE.format(waveform_id=waveform_id)
    request_rows: list[dict[str, object]] = []
    response_rows: list[dict[str, object]] = []
    download_rows: list[dict[str, object]] = []

    with KendoTadasPlaywrightBrowser(
        args.profile_dir,
        Path("data/private/tadas-raw-download-trigger-probe-downloads"),
        headless=False,
        timeout_ms=args.timeout_ms,
        selectors={},
    ) as browser:
        page = browser.page
        assert page is not None

        def on_request(req):
            if req.resource_type in STATIC_TYPES or not req.url.startswith(("http://", "https://")):
                return
            headers = req.headers
            request_rows.append({
                "method": req.method,
                "url": sanitize_url(req.url),
                "resource_type": req.resource_type,
                "safe_headers": safe_headers(headers),
                "sensitive_header_presence": sensitive_header_presence(headers),
                "post_data": safe_post_data(req),
            })

        def on_response(resp):
            req = resp.request
            if req.resource_type in STATIC_TYPES or not resp.url.startswith(("http://", "https://")):
                return
            response_rows.append({
                "status": resp.status,
                "url": sanitize_url(resp.url),
                "resource_type": req.resource_type,
                "content_type": resp.headers.get("content-type", ""),
                "content_disposition": resp.headers.get("content-disposition", ""),
            })

        def on_download(download):
            download_rows.append({
                "suggested_filename": download.suggested_filename or "",
                "url": sanitize_url(download.url or ""),
            })

        page.on("request", on_request)
        page.on("response", on_response)
        page.on("download", on_download)

        page.goto(detail_url, wait_until="networkidle")
        page.wait_for_timeout(1000)

        tab = page.locator(WAVEFORM_TAB_SELECTOR)
        if tab.count() != 1:
            raise RuntimeError(f"expected one Waveform tab, found {tab.count()}")
        tab.click()
        page.wait_for_timeout(700)

        button = page.get_by_role("button", name=RAW_BUTTON_NAME, exact=True)
        if button.count() != 1:
            raise RuntimeError(f"expected one {RAW_BUTTON_NAME!r} button, found {button.count()}")
        button.wait_for(state="visible", timeout=args.timeout_ms)
        descriptor = _button_descriptor(button)
        if descriptor.get("disabled"):
            raise RuntimeError("raw ASCII download button is disabled after opening Waveform tab")

        # Only keep traffic caused by the button click, not page bootstrap traffic.
        request_rows.clear()
        response_rows.clear()
        download_rows.clear()
        button.click()
        page.wait_for_timeout(args.observe_ms)

        artifact = {
            "schema_version": 1,
            "captured_at_utc": _now(),
            "waveform_id": waveform_id,
            "detail_url": detail_url,
            "waveform_tab_selector": WAVEFORM_TAB_SELECTOR,
            "raw_button_name": RAW_BUTTON_NAME,
            "button_descriptor_after_tab_open": descriptor,
            "triggered_requests": request_rows,
            "triggered_responses": response_rows,
            "download_events": download_rows,
            "security_note": (
                "Cookie/Authorization/CSRF/XSRF values are not written; sensitive query/JSON values are redacted."
            ),
        }
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(artifact, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    hosts = sorted({urlsplit(str(row["url"])).netloc for row in request_rows if row.get("url")})
    print(f"Waveform detail: {detail_url}")
    print(f"Waveform tab opened; raw ASCII button visible=yes")
    print(f"Triggered non-static requests: {len(request_rows)}")
    print(f"Triggered responses: {len(response_rows)}")
    print(f"Download events: {len(download_rows)}")
    print(f"Hosts: {', '.join(hosts) or 'none'}")
    print(f"Wrote sanitized trigger probe: {args.out}")
    print("No Cookie/Authorization/CSRF/XSRF values are written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
