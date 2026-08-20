from scripts.screen_esm_dataset_selection import (
    PGA_THRESHOLD_CM_S2,
    build_event_inventory,
    build_query,
    pga_value,
    waveform_identity,
)


def _row(event, station, pga, instrument="HN*", location="00"):
    return {
        "event_id": event,
        "event_time": "2020-01-01T00:00:00",
        "net_name": "XX",
        "station_code": station,
        "location_code": location,
        "instr_code": instrument,
        "processing_type": "MP",
        "class": "GOOD",
        "corr_hz_PGA": pga,
    }


def test_query_is_broad_and_has_no_magnitude_cut():
    q = build_query("HN*")
    assert q["minmag"] == "0"
    assert q["instrument"] == "HN*"
    assert q["unprocessed"] == "false"
    assert q["discarded"] == "false"
    assert q["best"] == q["good"] == q["bad"] == q["undef"] == "true"
    assert q["offset"] == "0"
    assert q["limit"] == "0"


def test_waveform_identity_preserves_event_network_station_location_instrument():
    row = _row("IT-1", "ABC", 200.0, "HG*", "10")
    assert waveform_identity(row) == ("IT-1", "XX", "ABC", "10", "HG*")


def test_pga_parser_is_absolute_and_fail_closed():
    assert pga_value(_row("E", "A", -200.0)) == 200.0
    assert pga_value(_row("E", "A", "bad")) is None
    assert pga_value(_row("E", "A", None)) is None


def test_event_requires_two_distinct_above_threshold_waveform_identities():
    rows = [
        _row("E1", "A", PGA_THRESHOLD_CM_S2 + 1),
        _row("E1", "B", PGA_THRESHOLD_CM_S2 + 2),
        _row("E2", "C", PGA_THRESHOLD_CM_S2 + 3),
    ]
    events = {event["event_id"]: event for event in build_event_inventory(rows)}
    assert events["E1"]["necessary_condition_candidate"] is True
    assert events["E1"]["rows_at_or_above_0p15g"] == 2
    assert events["E2"]["necessary_condition_candidate"] is False


def test_duplicate_identity_keeps_larger_pga_not_extra_candidate_count():
    rows = [
        _row("E1", "A", PGA_THRESHOLD_CM_S2 + 1),
        _row("E1", "A", PGA_THRESHOLD_CM_S2 + 50),
        _row("E1", "B", PGA_THRESHOLD_CM_S2 - 1),
    ]
    event = build_event_inventory(rows)[0]
    assert event["waveform_identities"] == 2
    assert event["rows_at_or_above_0p15g"] == 1
    assert event["necessary_condition_candidate"] is False
    assert event["max_corr_hz_PGA_cm_s2"] == PGA_THRESHOLD_CM_S2 + 50


def test_below_threshold_and_exact_threshold_behavior():
    rows = [
        _row("E1", "A", PGA_THRESHOLD_CM_S2),
        _row("E1", "B", PGA_THRESHOLD_CM_S2),
        _row("E2", "C", PGA_THRESHOLD_CM_S2 - 1e-9),
        _row("E2", "D", PGA_THRESHOLD_CM_S2),
    ]
    events = {event["event_id"]: event for event in build_event_inventory(rows)}
    assert events["E1"]["necessary_condition_candidate"] is True
    assert events["E2"]["necessary_condition_candidate"] is False
