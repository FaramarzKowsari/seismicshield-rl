from __future__ import annotations

import pytest

from scripts import probe_esm_flatfile_eventdata_v2 as mod

SAMPLE = {
    "event_id": "IT-2005-0043",
    "event_time": "2005-04-23T19:11:41",
    "net_name": "1V",
    "station_code": "ACC7",
    "location_code": "00",
    "instr_code": "HN*",
    "processing_type": "mp",
    "class": "GOOD",
}


def test_normalize_flatfile_channel_strips_dataset_selection_wildcard():
    assert mod.normalize_flatfile_channel("HN*") == "HN"
    assert mod.normalize_flatfile_channel("HGZ") == "HG"
    with pytest.raises(ValueError):
        mod.normalize_flatfile_channel("XX*")


def test_flatfile_crosswalk_uses_time_not_legacy_event_id():
    url = mod.build_flatfile_url(SAMPLE, pad_seconds=60)
    assert "eventid=" not in url
    assert "starttime=2005-04-23T19%3A10%3A41" in url
    assert "endtime=2005-04-23T19%3A12%3A41" in url
    assert "network=1V" in url
    assert "station=ACC7" in url
    assert "channel=HN" in url


def test_authoritative_event_id_requires_one_unique_value():
    rows = [{"ESM_event_id": "EMSC-20050423_0000001"}, {"ESM_event_id": "EMSC-20050423_0000001"}]
    assert mod.authoritative_esm_event_id(rows) == "EMSC-20050423_0000001"
    with pytest.raises(ValueError, match="ambiguous"):
        mod.authoritative_esm_event_id([{"ESM_event_id": "A"}, {"ESM_event_id": "B"}])


def test_eventdata_uses_authoritative_esm_id_and_preserves_wildcard_channel():
    url = mod.build_eventdata_url(SAMPLE, "EMSC-20050423_0000001")
    assert "eventid=EMSC-20050423_0000001" in url
    assert "channel=HN%2A" in url
    assert "format=ascii" in url
    assert "data-type=ACC" in url
