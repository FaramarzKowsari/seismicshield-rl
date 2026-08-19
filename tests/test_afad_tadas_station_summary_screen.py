import hashlib

import pytest

from scripts.screen_afad_tadas_station_summaries import (
    MIN_PGA_CM_S2,
    MIN_STATIONS_NEEDED,
    date_window,
    screen_station_summary_csv,
)


def write_summary(path, rows, header="EventID,Date,Type,Magnitude,Network,StationCode,Repi,Pga,Pgv,Pgd"):
    lines = [header]
    lines.extend(",".join(str(value) for value in row) for row in rows)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_summary_prescreen_rejects_when_station_maxima_cannot_reach_four_horizontals(tmp_path):
    source = tmp_path / "summary.csv"
    write_summary(source, [
        ("623342", "19-03-2024  22:55", "MW", "4.0", "TK", "1001", "10", "37.53", "0", "0"),
        ("623342", "19-03-2024  22:55", "MW", "4.0", "TK", "1002", "20", "25.68", "0", "0"),
    ])
    result = screen_station_summary_csv(source, "623342")
    assert result.status == "REJECT_SUMMARY_PGA"
    assert result.stations_at_or_above_threshold == 0
    assert result.required_candidate_stations == MIN_STATIONS_NEEDED == 2
    assert result.max_summary_pga_cm_s2 == pytest.approx(37.53)
    assert result.summary_csv_sha256 == hashlib.sha256(source.read_bytes()).hexdigest()


def test_summary_prescreen_candidate_needs_two_distinct_station_summaries_above_threshold(tmp_path):
    source = tmp_path / "summary.csv"
    write_summary(source, [
        ("543428", "06-02-2023  01:17", "MW", "7.7", "TK", "8002", "10", "336.563", "0", "0"),
        ("543428", "06-02-2023  01:17", "MW", "7.7", "TK", "8003", "20", "180.0", "0", "0"),
        ("543428", "06-02-2023  01:17", "MW", "7.7", "TK", "8004", "30", "25.0", "0", "0"),
    ])
    result = screen_station_summary_csv(source, "543428")
    assert result.status == "CANDIDATE_COMPONENT_AUDIT"
    assert result.stations_at_or_above_threshold == 2
    assert "HNE/HNN raw audit is required" in result.reason
    assert MIN_PGA_CM_S2 == pytest.approx(147.09975)


def test_summary_prescreen_one_high_station_is_still_rejected(tmp_path):
    source = tmp_path / "summary.csv"
    write_summary(source, [
        ("379819", "01-01-2020  00:00", "MW", "6.0", "TK", "5001", "10", "215.42", "0", "0"),
        ("379819", "01-01-2020  00:00", "MW", "6.0", "TK", "5002", "20", "40.0", "0", "0"),
    ])
    result = screen_station_summary_csv(source, "379819")
    assert result.status == "REJECT_SUMMARY_PGA"
    assert result.stations_at_or_above_threshold == 1


def test_summary_prescreen_fails_closed_on_event_mismatch_duplicate_station_or_bad_pga(tmp_path):
    mismatch = tmp_path / "mismatch.csv"
    write_summary(mismatch, [
        ("123", "01-01-2020  00:00", "MW", "4", "TK", "1001", "10", "1", "0", "0"),
        ("124", "01-01-2020  00:00", "MW", "4", "TK", "1002", "10", "1", "0", "0"),
    ])
    with pytest.raises(ValueError, match="EventID mismatch"):
        screen_station_summary_csv(mismatch, "123")

    duplicate = tmp_path / "duplicate.csv"
    write_summary(duplicate, [
        ("123", "01-01-2020  00:00", "MW", "4", "TK", "1001", "10", "1", "0", "0"),
        ("123", "01-01-2020  00:00", "MW", "4", "TK", "1001", "10", "2", "0", "0"),
    ])
    with pytest.raises(ValueError, match="duplicate station code"):
        screen_station_summary_csv(duplicate, "123")

    bad = tmp_path / "bad.csv"
    write_summary(bad, [
        ("123", "01-01-2020  00:00", "MW", "4", "TK", "1001", "10", "NaN", "0", "0"),
    ])
    with pytest.raises(ValueError, match="invalid PGA"):
        screen_station_summary_csv(bad, "123")


def test_real_tadas_summary_header_aliases_and_date_window(tmp_path):
    source = tmp_path / "summary.csv"
    write_summary(source, [
        ("279680", "14-11-2014  23:30", "MW", "4", "TK", "4306", "21.6", "2.266004", "0", "0"),
    ])
    result = screen_station_summary_csv(source, "279680")
    assert result.unique_station_count == 1
    assert date_window("14-11-2014  23:30") == (
        "13-11-2014 00:00:00",
        "15-11-2014 23:59:59",
    )


def test_missing_required_summary_column_fails_closed(tmp_path):
    source = tmp_path / "summary.csv"
    source.write_text("EventID,StationCode\n123,1001\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing required field 'pga'"):
        screen_station_summary_csv(source, "123")
