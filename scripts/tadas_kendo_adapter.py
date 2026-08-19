"""Strict adapter for the current AFAD/TADAS Kendo Quick Search UI.

This module contains browser-UI compatibility logic only. It does not change the
frozen scientific selection contract and does not turn station-summary screening into
final component eligibility.
"""

from __future__ import annotations

from pathlib import Path

if __package__:
    from scripts import screen_afad_tadas_station_summaries as base
else:  # imported as a top-level module by the direct script entrypoint
    import screen_afad_tadas_station_summaries as base


DATE_INPUT_SELECTOR = "input.k-input:not(.k-formatted-value):visible"
EVENT_ID_SELECTOR = "input[name='txtEaEventId']:visible"
CSV_BUTTON_SELECTOR = "button:has(.k-i-file-csv):visible"


def assert_preserved_value(kind: str, observed: str, expected: str) -> None:
    """Fail closed if TADAS/Kendo did not preserve a submitted search value."""
    if str(observed).strip() != str(expected).strip():
        raise RuntimeError(
            f"TADAS search form did not preserve {kind}: "
            f"expected {expected!r}, observed {observed!r}"
        )


def keyboard_commit_kendo_date(locator, value: str, *, delay_ms: int = 12) -> None:
    """Commit a Kendo DateInput through real keyboard events.

    The live TADAS widget rejected DOM-style ``fill`` plus synthetic change events and
    restored its prior date. Kendo DateInput is keyboard/segment driven, so this helper
    follows the user interaction path: select all, clear, type sequentially, accept, blur.
    """
    locator.click()
    locator.press("Control+A")
    locator.press("Backspace")
    locator.press_sequentially(value, delay=delay_ms)
    locator.press("Enter")
    locator.press("Tab")


class KendoTadasPlaywrightBrowser(base.TadasPlaywrightBrowser):
    """Use stable DOM structure observed in the current TADAS Kendo search form."""

    def _input(self, kind: str):
        assert self.page is not None
        override = self.selectors.get(kind)
        if override:
            locator = self.page.locator(override)
            if locator.count() != 1:
                raise RuntimeError(
                    f"selector override for {kind!r} must match exactly one element: "
                    f"{override!r}; matched {locator.count()}"
                )
            return locator.first

        if kind == "event_id":
            locator = self.page.locator(EVENT_ID_SELECTOR)
            if locator.count() != 1:
                raise RuntimeError(
                    f"current TADAS event-id selector matched {locator.count()} elements"
                )
            return locator.first

        if kind in {"start_date", "end_date"}:
            date_inputs = self.page.locator(DATE_INPUT_SELECTOR)
            if date_inputs.count() != 2:
                raise RuntimeError(
                    "current TADAS date-input contract expected exactly two visible "
                    f"non-formatted Kendo inputs; found {date_inputs.count()}"
                )
            return date_inputs.nth(0 if kind == "start_date" else 1)

        return super()._input(kind)

    def _action(self, kind: str, terms: tuple[str, ...]):
        assert self.page is not None
        override = self.selectors.get(kind)
        if override:
            locator = self.page.locator(override)
            if locator.count() != 1:
                raise RuntimeError(
                    f"selector override for {kind!r} must match exactly one element: "
                    f"{override!r}; matched {locator.count()}"
                )
            return locator.first

        if kind == "csv_button":
            locator = self.page.locator(CSV_BUTTON_SELECTOR)
            if locator.count() != 1:
                raise RuntimeError(
                    "current TADAS CSV export contract expected exactly one visible "
                    f"k-i-file-csv button; found {locator.count()}"
                )
            return locator.first

        return super()._action(kind, terms)

    def _set_control(self, kind: str, value: str) -> None:
        assert self.page is not None
        locator = self._input(kind)

        if kind in {"start_date", "end_date"}:
            keyboard_commit_kendo_date(locator, value)
        else:
            locator.click()
            locator.fill(value)
            locator.dispatch_event("input")
            locator.dispatch_event("change")
            locator.press("Tab")

        self.page.wait_for_timeout(150)
        assert_preserved_value(kind, locator.input_value(), value)

    def _verify_search_form(self, event_id: str, start: str, end: str) -> None:
        assert_preserved_value("event_id", self._input("event_id").input_value(), event_id)
        assert_preserved_value("start_date", self._input("start_date").input_value(), start)
        assert_preserved_value("end_date", self._input("end_date").input_value(), end)

    def download_station_summary(
        self, queue_row: dict[str, str], destination: Path, *, pad_days: int
    ) -> None:
        assert self.page is not None
        event_id = queue_row["event_id"]
        start, end = base.date_window(queue_row["event_date_from_export"], pad_days=pad_days)

        self.page.goto(base.TADAS_WAVEFORM_SEARCH_URL, wait_until="domcontentloaded")
        self._set_control("event_id", event_id)
        self._set_control("start_date", start)
        self._set_control("end_date", end)
        self._verify_search_form(event_id, start, end)

        self._action("search_button", ("search", "query", "sorgula", "ara")).click()
        try:
            self.page.wait_for_load_state("networkidle", timeout=min(self.timeout_ms, 15000))
        except Exception:
            self.page.wait_for_timeout(1500)

        # Critical anti-false-rejection guard: never export/screen if TADAS changed any
        # submitted search value after Search.
        self._verify_search_form(event_id, start, end)

        csv_button = self._action("csv_button", ("csv",))
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self.page.expect_download(timeout=self.timeout_ms) as download_info:
                csv_button.click()
            download = download_info.value
            download.save_as(str(destination))
        except Exception as exc:
            raise RuntimeError(f"CSV download failed for EventID {event_id}: {exc}") from exc
