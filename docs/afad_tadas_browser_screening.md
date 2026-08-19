# Automated AFAD/TADAS station-summary screening

This workflow removes the repetitive manual EventID/date/CSV loop while preserving the
frozen scientific contract.

## Scope

`scripts/screen_afad_tadas_station_summaries.py` is **data-selection/provenance
infrastructure only**. It does not run OpenSeesPy, reinforcement learning, optimization,
or confirmatory analyses.

The station-summary CSV is used only as a necessary-condition prescreen:

- frozen component PGA threshold: `0.15 g = 147.09975 cm/s²`;
- at most two eligible horizontal components (`HNE`, `HNN`) can come from one station;
- therefore an event needs at least two distinct station-summary rows at or above the
  threshold before it can possibly provide four eligible horizontal records;
- a station-summary PGA above threshold does **not** prove either horizontal component
  passes. Such events are marked `CANDIDATE_COMPONENT_AUDIT`, not eligible.

Final eligibility remains the raw component-level audit contract.

## One-time setup

```bash
pip install -e ".[tadas]"
playwright install chromium
```

Build the frozen queue from the original Event Search export if it does not already exist:

```bash
python scripts/build_afad_tadas_event_queue.py /path/to/tadas_event_search.csv
```

The expected queue is:

```text
results/local/afad_tadas/event_candidate_queue.csv
```

## Run the browser-assisted prescreen

```bash
python scripts/screen_afad_tadas_station_summaries.py \
  results/local/afad_tadas/event_candidate_queue.csv
```

The default browser is headed. The script opens the official TADAS waveform-search page.
If the saved session is not usable, complete Guest/Staff login manually in that browser
and then press Enter in the terminal. The script never asks for or stores a password.

By default it:

- resumes from the existing local ledger;
- searches events in frozen hash rank order;
- derives a date window of ±1 calendar day from the Event Search export;
- downloads the station-summary CSV through the visible TADAS UI;
- hashes and validates each CSV;
- rejects events that cannot possibly supply four threshold-passing horizontal records;
- stops after accumulating 80 component-audit candidates;
- waits 4 seconds between events;
- aborts after 3 consecutive browser/download errors.

Local outputs remain under ignored paths:

```text
results/local/afad_tadas/station_summaries/
results/local/afad_tadas/station_summary_screen.csv
results/local/afad_tadas/browser_errors/
data/private/tadas-browser-profile/
```

## Resume or narrow a run

```bash
python scripts/screen_afad_tadas_station_summaries.py \
  results/local/afad_tadas/event_candidate_queue.csv \
  --start-rank 100 \
  --end-rank 500 \
  --stop-after-candidates 80
```

Use `--stop-after-candidates 0` for no candidate-count stop.

Use `--skip-errors` to leave prior `ERROR` rows untouched. Without that flag, errored
events are retried on the next run.

## Selector overrides

The browser helper first uses visible labels/attributes and button text. If the TADAS UI
changes and a control becomes ambiguous, create a local JSON file such as:

```json
{
  "event_id": "CSS selector here",
  "start_date": "CSS selector here",
  "end_date": "CSS selector here",
  "search_button": "CSS selector here",
  "csv_button": "CSS selector here"
}
```

Then run with:

```bash
python scripts/screen_afad_tadas_station_summaries.py \
  results/local/afad_tadas/event_candidate_queue.csv \
  --selectors-json /path/to/local-selectors.json
```

Do not commit credentials, cookies, browser profiles, downloaded real data, or private
selector/session material.

## Browser safety and access discipline

The automation uses the normal visible TADAS interface. It does not bypass CAPTCHA,
authentication, rate limits, or access controls. If TADAS changes its access policy or
blocks automated interaction, stop the run and use the permitted access method instead.

The script's persistent browser profile is local-only. Raw waveform redistribution
remains disabled unless explicitly authorized by a frozen license rule.
