# AFAD/TADAS current Kendo UI compatibility

The current authenticated Waveform Quick Search UI exposes two visible date inputs as
Kendo inputs without stable semantic names. The Event Id control is stable as
`name="txtEaEventId"`, and the grid CSV export button is identified by a child icon with
class `k-i-file-csv`.

Use the strict entry point:

```bash
python scripts/screen_afad_tadas_station_summaries_kendo.py \
  results/local/afad_tadas/event_candidate_queue.csv
```

The adapter fails closed unless exactly two visible non-formatted Kendo date inputs are
present and exactly one visible CSV-icon button is present. It commits Kendo/Angular form
state with input/change/blur behavior and verifies Event Id, start date, and end date both
before and after Search. If TADAS resets a date or any selector contract changes, the event
is recorded as `ERROR`; no station-summary rejection is allowed from a search whose form
values were not preserved.

This is browser compatibility and provenance infrastructure only. It does not change the
frozen event hash order, PGA threshold, component-level eligibility rules, OSF gate, or
raw-waveform redistribution policy.
