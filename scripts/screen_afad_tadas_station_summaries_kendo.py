#!/usr/bin/env python3
"""Run AFAD/TADAS station-summary screening with the strict current-Kendo UI adapter."""

from __future__ import annotations

try:
    from scripts import screen_afad_tadas_station_summaries as base
    from scripts.tadas_kendo_adapter import KendoTadasPlaywrightBrowser
except ModuleNotFoundError:  # direct execution from scripts/
    import screen_afad_tadas_station_summaries as base
    from tadas_kendo_adapter import KendoTadasPlaywrightBrowser


base.TadasPlaywrightBrowser = KendoTadasPlaywrightBrowser


if __name__ == "__main__":
    raise SystemExit(base.main())
