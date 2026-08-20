import argparse
import hashlib
import json

from scripts.probe_esm_dataset_selection import build_query, summarize


def _args(**overrides):
    values = dict(starttime="1900-01-01", endtime="2100-01-01", minmag=4.0,
                  maxdist=3000.0, limit=5)
    values.update(overrides)
    return argparse.Namespace(**values)


def test_build_query_is_public_machine_readable_schema_probe():
    query = build_query(_args())
    assert query["eventid"] == "*"
    assert query["minmag"] == "4.0"
    assert query["unprocessed"] == "false"
    assert query["discarded"] == "false"
    assert query["bad"] == "false"
    assert query["undef"] == "false"
    assert query["processing-filter-logic"] == "available"
    assert query["format"] == "json"
    assert query["offset"] == "0"
    assert query["limit"] == "5"


def test_summarize_list_response_and_redacts_sensitive_fields():
    parsed = [{
        "event_id": "IT-TEST",
        "network": "IT",
        "station": "ABC",
        "authorization_token": "should-not-leak",
    }]
    body = json.dumps(parsed).encode()
    summary = summarize(parsed, url="https://example.test/query", status=200,
                        content_type="application/json", body=body)
    assert summary["final_manifest"] is False
    assert summary["records_detected"] == 1
    assert "event_id" in summary["first_record_keys"]
    assert summary["first_record_preview"]["authorization_token"] == "<redacted>"
    assert summary["response_sha256"] == hashlib.sha256(body).hexdigest()


def test_summarize_dict_wrapped_records():
    parsed = {"records": [{"eventid": "E1", "station": "S1"}], "count": 1}
    body = json.dumps(parsed).encode()
    summary = summarize(parsed, url="https://example.test/query", status=200,
                        content_type="application/json", body=body)
    assert summary["json_top_level_type"] == "dict"
    assert summary["top_level_keys"] == ["count", "records"]
    assert summary["records_detected"] == 1
    assert summary["first_record_preview"]["eventid"] == "E1"
