#!/usr/bin/env python3
"""Sanitized diagnostic probe for a TADAS waveform-detail page.

Captures DOM descriptors and HTTP(S) request/response metadata without writing Cookie,
Authorization, CSRF/XSRF, or other sensitive header values. This is infrastructure-only.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

if __package__:
    from scripts.audit_afad_tadas_candidate_events import DETAIL_URL_TEMPLATE, DEFAULT_PROFILE_DIR
    from scripts.tadas_kendo_adapter import KendoTadasPlaywrightBrowser
else:
    from audit_afad_tadas_candidate_events import DETAIL_URL_TEMPLATE, DEFAULT_PROFILE_DIR
    from tadas_kendo_adapter import KendoTadasPlaywrightBrowser

DEFAULT_OUT = Path("data/private/tadas-waveform-detail-probe.json")
SENSITIVE_HEADER_NAMES = {
    "authorization", "proxy-authorization", "cookie", "set-cookie",
    "x-csrf-token", "x-xsrf-token", "csrf-token", "xsrf-token",
}
SENSITIVE_QUERY_RE = re.compile(r"token|auth|session|key|secret|csrf|xsrf", re.I)
STATIC_TYPES = {"image", "font", "stylesheet", "media"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sanitize_url(url: str) -> str:
    parts = urlsplit(url)
    safe = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        safe.append((key, "[REDACTED]" if SENSITIVE_QUERY_RE.search(key) else value))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(safe), ""))


def sensitive_header_presence(headers: dict[str, str]) -> dict[str, bool]:
    lowered = {str(k).lower() for k in headers}
    return {name: name in lowered for name in sorted(SENSITIVE_HEADER_NAMES)}


def safe_headers(headers: dict[str, str]) -> dict[str, str]:
    return {
        str(k): str(v)
        for k, v in headers.items()
        if str(k).lower() not in SENSITIVE_HEADER_NAMES
    }


def _descriptor(locator) -> dict[str, object]:
    return locator.evaluate(
        """el => ({
          tag: el.tagName || '',
          text: (el.innerText || el.textContent || '').trim().slice(0, 500),
          id: el.id || '',
          className: typeof el.className === 'string' ? el.className : '',
          href: el.getAttribute('href') || '',
          src: el.getAttribute('src') || '',
          title: el.getAttribute('title') || '',
          aria: el.getAttribute('aria-label') || '',
          role: el.getAttribute('role') || '',
          download: el.getAttribute('download') || '',
          onclick: el.getAttribute('onclick') || '',
          name: el.getAttribute('name') || '',
          type: el.getAttribute('type') || '',
          value: (el.getAttribute('value') || '').slice(0, 300),
          visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length),
          outerHTML: (el.outerHTML || '').slice(0, 1500)
        })"""
    )


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--waveform-id", default="2136302")
    p.add_argument("--profile-dir", type=Path, default=DEFAULT_PROFILE_DIR)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--timeout-ms", type=int, default=30000)
    a = p.parse_args()
    waveform_id = str(a.waveform_id).strip()
    if not re.fullmatch(r"[0-9]+", waveform_id):
        p.error("--waveform-id must be ASCII decimal digits")

    request_rows: list[dict[str, object]] = []
    response_rows: list[dict[str, object]] = []
    detail_url = DETAIL_URL_TEMPLATE.format(waveform_id=waveform_id)

    with KendoTadasPlaywrightBrowser(
        a.profile_dir,
        Path("data/private/tadas-waveform-detail-probe-downloads"),
        headless=False,
        timeout_ms=a.timeout_ms,
        selectors={},
    ) as browser:
        page = browser.page
        assert page is not None

        def on_request(req):
            if req.resource_type in STATIC_TYPES:
                return
            if not req.url.startswith(("http://", "https://")):
                return
            headers = req.headers
            request_rows.append({
                "method": req.method,
                "url": sanitize_url(req.url),
                "resource_type": req.resource_type,
                "safe_headers": safe_headers(headers),
                "sensitive_header_presence": sensitive_header_presence(headers),
            })

        def on_response(resp):
            req = resp.request
            if req.resource_type in STATIC_TYPES:
                return
            if not resp.url.startswith(("http://", "https://")):
                return
            response_rows.append({
                "status": resp.status,
                "url": sanitize_url(resp.url),
                "resource_type": req.resource_type,
                "content_type": resp.headers.get("content-type", ""),
            })

        page.on("request", on_request)
        page.on("response", on_response)
        page.goto(detail_url, wait_until="networkidle")
        page.wait_for_timeout(1200)

        selectors = [
            "a", "button", "[role=button]", "input", "select", "option",
            "[onclick]", "[href]", "[download]", "i", "span", "svg",
        ]
        descriptors: list[dict[str, object]] = []
        seen = set()
        for selector in selectors:
            loc = page.locator(selector)
            for i in range(min(loc.count(), 500)):
                try:
                    d = _descriptor(loc.nth(i))
                except Exception:
                    continue
                key = (d.get("tag"), d.get("id"), d.get("className"), d.get("href"), d.get("onclick"), d.get("text"))
                if key in seen:
                    continue
                seen.add(key)
                haystack = " ".join(str(d.get(k, "")) for k in ("text", "id", "className", "href", "title", "aria", "onclick", "outerHTML")).lower()
                if any(tok in haystack for tok in ("raw", "download", "indir", "dyna", "ascii", "zip", "ham veri", "data")):
                    descriptors.append(d)

        artifact = {
            "schema_version": 1,
            "captured_at_utc": _now(),
            "waveform_id": waveform_id,
            "detail_url": detail_url,
            "final_page_url": sanitize_url(page.url),
            "title": page.title(),
            "frames": [sanitize_url(frame.url) for frame in page.frames],
            "matching_dom_descriptors": descriptors,
            "requests": request_rows,
            "responses": response_rows,
            "security_note": "Cookie/Authorization/CSRF/XSRF values are not written; sensitive query values are redacted.",
        }
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(artifact, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    hosts = sorted({urlsplit(str(r["url"])).netloc for r in request_rows})
    print(f"Waveform detail: {detail_url}")
    print(f"Captured non-static requests: {len(request_rows)}")
    print(f"Hosts: {', '.join(hosts) or 'none'}")
    print(f"Matching DOM descriptors: {len(descriptors)}")
    print(f"Wrote sanitized probe: {a.out}")
    print("No Cookie/Authorization/CSRF/XSRF values are written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
