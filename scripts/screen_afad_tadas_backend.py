#!/usr/bin/env python3
"""Screen the frozen AFAD/TADAS event queue through the authenticated waveform backend.

Provenance/data-selection infrastructure only. This preserves the existing station-summary
PGA necessary-condition prescreen; final eligibility still requires audited HNE/HNN raw
components. Confirmatory simulation remains blocked.
"""
from __future__ import annotations
import argparse, copy, csv, hashlib, json, math, time
from datetime import datetime, timedelta, timezone
from pathlib import Path

if __package__:
    from scripts import screen_afad_tadas_station_summaries as base
    from scripts.probe_tadas_backend_replay import BACKEND_URL, forwardable_headers, sensitive_header_presence
    from scripts.tadas_kendo_adapter import KendoTadasPlaywrightBrowser
else:
    import screen_afad_tadas_station_summaries as base
    from probe_tadas_backend_replay import BACKEND_URL, forwardable_headers, sensitive_header_presence
    from tadas_kendo_adapter import KendoTadasPlaywrightBrowser

# PR #17 established that the TADAS UI template's default fromMagnitude=3 is an active
# backend filter even when an exact eaEventId is supplied. Magnitude is not a frozen
# SeismicShield-RL eligibility criterion, so all scientific screening requests must neutralize
# that floor explicitly. Use fresh defaults so pre-fix ledger/candidate artifacts cannot be
# silently resumed as if they were produced under the corrected query contract.
QUERY_CONTRACT = "event-specific;fromMagnitude=null"
DEFAULT_LEDGER = Path("results/local/afad_tadas/station_summary_backend_screen_nomag.csv")
DEFAULT_UI_LEDGER = Path("results/local/afad_tadas/station_summary_screen.csv")
DEFAULT_CANDIDATE_DIR = Path("data/private/tadas-backend-candidates-nomag")
FINAL_STATUSES = {"REJECT_SUMMARY_PGA", "CANDIDATE_COMPONENT_AUDIT"}
LEDGER_COLUMNS = (
    "rank","event_hash","event_id","event_date_from_export","query_contract",
    "backend_response_sha256","backend_row_count","unique_station_count",
    "stations_at_or_above_threshold","max_summary_pga_cm_s2","threshold_cm_s2",
    "required_candidate_stations","status","reason","source_reference",
    "candidate_json_path","screened_at_utc",
)

def _ui_dt(v:str)->datetime: return datetime.strptime(v,"%d-%m-%Y %H:%M:%S")
def _iso_dt(v:str)->datetime:
    if not str(v).endswith("Z"): raise ValueError(f"backend date is not UTC-Z serialized: {v!r}")
    return datetime.fromisoformat(str(v)[:-1]+"+00:00").replace(tzinfo=None)

def infer_date_serialization_shift(ui_start:str, ui_end:str, live_payload:dict[str,object])->timedelta:
    s,e=live_payload.get("startDate"),live_payload.get("endDate")
    if not isinstance(s,str) or not isinstance(e,str): raise ValueError("live request missing startDate/endDate")
    ds,de=_iso_dt(s)-_ui_dt(ui_start),_iso_dt(e)-_ui_dt(ui_end)
    if ds!=de: raise ValueError(f"inconsistent live date shifts: {ds} vs {de}")
    if abs(ds.total_seconds())>14*3600: raise ValueError(f"implausible live date shift: {ds}")
    return ds

def _serialize(v:str,shift:timedelta)->str: return (_ui_dt(v)+shift).strftime("%Y-%m-%dT%H:%M:%S.000Z")
def build_payload_from_live_template(template:dict[str,object], row:dict[str,str], *, pad_days:int, shift:timedelta)->dict[str,object]:
    event_id=str(row["event_id"]).strip()
    if not event_id: raise ValueError("event_id must be nonblank")
    start,end=base.date_window(row["event_date_from_export"],pad_days=pad_days)
    payload=copy.deepcopy(template)
    payload["eaEventId"]=event_id
    payload["startDate"]=_serialize(start,shift)
    payload["endDate"]=_serialize(end,shift)
    # Critical scientific contract: do not inherit the TADAS UI's default M>=3 filter.
    payload["fromMagnitude"]=None
    return payload

def summarize_backend_json(value, expected_event_id:str)->dict[str,object]:
    if not isinstance(value,list): raise ValueError(f"GetWaveforms response must be list, found {type(value).__name__}")
    expected=str(expected_event_id).strip(); stations=set(); above_rows=[]; max_pga=0.0
    for i,row in enumerate(value):
        if not isinstance(row,dict): raise ValueError(f"backend row {i} is not object")
        if str(row.get("eaEventId","")).strip()!=expected: raise ValueError(f"backend EventID mismatch at row {i}")
        station=str(row.get("stationCode","")).strip()
        if not station: raise ValueError(f"blank stationCode at row {i}")
        if station in stations: raise ValueError(f"duplicate stationCode {station!r}")
        stations.add(station)
        try: pga=float(row.get("pga"))
        except (TypeError,ValueError) as exc: raise ValueError(f"non-numeric PGA at row {i}") from exc
        if not math.isfinite(pga) or pga<0: raise ValueError(f"invalid PGA at row {i}: {pga!r}")
        max_pga=max(max_pga,pga)
        if pga>=base.MIN_PGA_CM_S2: above_rows.append(row)
    above=len(above_rows)
    if above<base.MIN_STATIONS_NEEDED:
        status="REJECT_SUMMARY_PGA"; reason=f"only {above} station summaries reach {base.MIN_PGA_CM_S2:.5f} cm/s^2; at least {base.MIN_STATIONS_NEEDED} stations are necessary for four eligible horizontal components"
    else:
        status="CANDIDATE_COMPONENT_AUDIT"; reason=f"{above} station summaries reach {base.MIN_PGA_CM_S2:.5f} cm/s^2; station-summary PGA is not component eligibility, so HNE/HNN raw audit is required"
    return {"backend_row_count":len(value),"unique_station_count":len(stations),"stations_at_or_above_threshold":above,"max_summary_pga_cm_s2":max_pga,"threshold_cm_s2":base.MIN_PGA_CM_S2,"required_candidate_stations":base.MIN_STATIONS_NEEDED,"status":status,"reason":reason,"above_threshold_rows":above_rows}

def _load(path:Path, *, finals_only=False, require_query_contract=False):
    if not path.exists(): return {}
    with path.open("r",encoding="utf-8",newline="") as h:
        rows=list(csv.DictReader(h))
    entries={}
    for r in rows:
        event_id=(r.get("event_id") or "").strip()
        if not event_id or (finals_only and r.get("status") not in FINAL_STATUSES):
            continue
        if require_query_contract and r.get("query_contract")!=QUERY_CONTRACT:
            raise ValueError(
                f"ledger {path} contains EventID {event_id} under stale/unknown query contract "
                f"{r.get('query_contract')!r}; corrected screening requires {QUERY_CONTRACT!r}"
            )
        entries[event_id]=r
    return entries

def _write(path:Path,entries):
    path.parent.mkdir(parents=True,exist_ok=True); tmp=path.with_suffix(path.suffix+".tmp")
    with tmp.open("w",encoding="utf-8",newline="") as h:
        w=csv.DictWriter(h,fieldnames=LEDGER_COLUMNS,extrasaction="ignore",lineterminator="\n"); w.writeheader(); w.writerows(sorted(entries.values(),key=lambda r:int(r["rank"])))
    tmp.replace(path)

def assert_ui_parity(summary,ui_row,*,tol:float):
    if str(summary["status"])!=ui_row.get("status"): raise RuntimeError("backend/UI status mismatch")
    for bk,uk in (("backend_row_count","summary_row_count"),("unique_station_count","unique_station_count"),("stations_at_or_above_threshold","stations_at_or_above_threshold")):
        if int(summary[bk])!=int(ui_row[uk]): raise RuntimeError(f"backend/UI {bk} mismatch: {summary[bk]} vs {ui_row[uk]}")
    if abs(float(summary["max_summary_pga_cm_s2"])-float(ui_row["max_summary_pga_cm_s2"]))>tol: raise RuntimeError("backend/UI max PGA mismatch beyond export rounding tolerance")

def ui_parity_is_valid_for_queue_row(row:dict[str,str])->bool:
    """Old UI/CSV screening inherited M>=3, so parity is valid only for known M>=3 rows."""
    text=str(row.get("magnitude","") or "").strip()
    if not text: return False
    try: magnitude=float(text)
    except ValueError: return False
    return math.isfinite(magnitude) and magnitude>=3.0

def _bootstrap(browser,row,*,pad_days:int,timeout_ms:int):
    page=browser.page; assert page is not None
    event_id=row["event_id"]; start,end=base.date_window(row["event_date_from_export"],pad_days=pad_days)
    page.goto(base.TADAS_WAVEFORM_SEARCH_URL,wait_until="domcontentloaded"); browser._set_control("event_id",event_id); browser._set_control("start_date",start); browser._set_control("end_date",end); browser._verify_search_form(event_id,start,end)
    def mr(req): return req.url==BACKEND_URL and req.method.upper()=="POST" and f'"eaEventId":"{event_id}"' in (req.post_data or "").replace(" ","")
    with page.expect_request(mr,timeout=timeout_ms) as qi:
        with page.expect_response(lambda resp: mr(resp.request),timeout=timeout_ms) as ri: browser._action("search_button",("search","query","sorgula","ara")).click()
    req,resp=qi.value,ri.value
    if resp.status!=200: raise RuntimeError(f"bootstrap UI request returned HTTP {resp.status}")
    payload=json.loads(req.post_data or "null")
    if not isinstance(payload,dict) or str(payload.get("eaEventId",""))!=event_id: raise RuntimeError("bootstrap request payload mismatch")
    headers=req.all_headers(); presence=sensitive_header_presence(headers)
    if not presence.get("authorization"): raise RuntimeError("bootstrap request lacks Authorization header")
    return payload,forwardable_headers(headers),infer_date_serialization_shift(start,end,payload)

def main()->int:
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("queue",type=Path); p.add_argument("--ledger",type=Path,default=DEFAULT_LEDGER); p.add_argument("--ui-parity-ledger",type=Path,default=DEFAULT_UI_LEDGER); p.add_argument("--candidate-dir",type=Path,default=DEFAULT_CANDIDATE_DIR); p.add_argument("--profile-dir",type=Path,default=base.DEFAULT_PROFILE_DIR); p.add_argument("--bootstrap-rank",type=int,default=248); p.add_argument("--start-rank",type=int,default=1); p.add_argument("--end-rank",type=int,default=0); p.add_argument("--stop-after-candidates",type=int,default=80); p.add_argument("--pad-days",type=int,default=1); p.add_argument("--delay-s",type=float,default=0.20); p.add_argument("--timeout-ms",type=int,default=30000); p.add_argument("--max-consecutive-errors",type=int,default=3); p.add_argument("--max-pga-parity-tol",type=float,default=0.001); a=p.parse_args()
    rows=base.read_queue(a.queue)
    if not 1<=a.bootstrap_rank<=len(rows): p.error("--bootstrap-rank outside queue")
    entries=_load(a.ledger,require_query_contract=True); ui=_load(a.ui_parity_ledger,finals_only=True); candidates=sum(r.get("status")=="CANDIDATE_COMPONENT_AUDIT" for r in entries.values()); parity=0; parity_skipped=0; errors=0
    with KendoTadasPlaywrightBrowser(a.profile_dir,Path("data/private/tadas-backend-bootstrap-downloads"),headless=False,timeout_ms=a.timeout_ms,selectors={}) as browser:
        assert browser.context is not None
        template,headers,shift=_bootstrap(browser,rows[a.bootstrap_rank-1],pad_days=a.pad_days,timeout_ms=a.timeout_ms)
        print(f"Backend bootstrap established; Authorization present=yes; observed date serialization shift={shift}")
        print("Scientific query contract: exact EventID with fromMagnitude=null (no magnitude floor).")
        print("Sensitive header values remain in memory only.")
        for row in rows:
            rank=int(row["rank"])
            if rank<a.start_rank or (a.end_rank and rank>a.end_rank): continue
            if entries.get(row["event_id"],{}).get("status") in FINAL_STATUSES: continue
            if a.stop_after_candidates and candidates>=a.stop_after_candidates: break
            print(f"[rank {rank}] EventID {row['event_id']} ...")
            try:
                payload=build_payload_from_live_template(template,row,pad_days=a.pad_days,shift=shift); resp=browser.context.request.post(BACKEND_URL,data=json.dumps(payload,separators=(",",":")),headers=headers,timeout=a.timeout_ms); body=resp.body()
                if resp.status!=200: raise RuntimeError(f"GetWaveforms returned HTTP {resp.status}")
                if "json" not in resp.headers.get("content-type","").lower(): raise RuntimeError("GetWaveforms returned non-JSON")
                summary=summarize_backend_json(json.loads(body.decode("utf-8-sig")),row["event_id"])
                if row["event_id"] in ui:
                    if ui_parity_is_valid_for_queue_row(row):
                        assert_ui_parity(summary,ui[row["event_id"]],tol=a.max_pga_parity_tol); parity+=1
                    else:
                        parity_skipped+=1
                candidate_path=""
                if summary["status"]=="CANDIDATE_COMPONENT_AUDIT":
                    a.candidate_dir.mkdir(parents=True,exist_ok=True); cp=a.candidate_dir/f"rank-{rank:05d}-event-{row['event_id']}.json"; cp.write_text(json.dumps({"rank":rank,"event_id":row["event_id"],"query_contract":QUERY_CONTRACT,"threshold_cm_s2":base.MIN_PGA_CM_S2,"backend_response_sha256":hashlib.sha256(body).hexdigest(),"rows_at_or_above_threshold":summary["above_threshold_rows"]},indent=2,ensure_ascii=False),encoding="utf-8"); candidate_path=str(cp)
                entries[row["event_id"]]={"rank":rank,"event_hash":row["event_hash"],"event_id":row["event_id"],"event_date_from_export":row["event_date_from_export"],"query_contract":QUERY_CONTRACT,"backend_response_sha256":hashlib.sha256(body).hexdigest(),"backend_row_count":summary["backend_row_count"],"unique_station_count":summary["unique_station_count"],"stations_at_or_above_threshold":summary["stations_at_or_above_threshold"],"max_summary_pga_cm_s2":summary["max_summary_pga_cm_s2"],"threshold_cm_s2":summary["threshold_cm_s2"],"required_candidate_stations":summary["required_candidate_stations"],"status":summary["status"],"reason":summary["reason"],"source_reference":BACKEND_URL,"candidate_json_path":candidate_path,"screened_at_utc":datetime.now(timezone.utc).isoformat().replace("+00:00","Z")}; _write(a.ledger,entries)
                if summary["status"]=="CANDIDATE_COMPONENT_AUDIT": candidates+=1
                errors=0; print(f"  {summary['status']}: max summary PGA={summary['max_summary_pga_cm_s2']:.6g} cm/s^2, stations above threshold={summary['stations_at_or_above_threshold']}")
            except Exception as exc:
                errors+=1; entries[row["event_id"]]={"rank":rank,"event_hash":row["event_hash"],"event_id":row["event_id"],"event_date_from_export":row["event_date_from_export"],"query_contract":QUERY_CONTRACT,"backend_response_sha256":"","backend_row_count":"","unique_station_count":"","stations_at_or_above_threshold":"","max_summary_pga_cm_s2":"","threshold_cm_s2":base.MIN_PGA_CM_S2,"required_candidate_stations":base.MIN_STATIONS_NEEDED,"status":"ERROR","reason":str(exc),"source_reference":BACKEND_URL,"candidate_json_path":"","screened_at_utc":datetime.now(timezone.utc).isoformat().replace("+00:00","Z")}; _write(a.ledger,entries); print(f"  ERROR: {exc}")
                if errors>=a.max_consecutive_errors: p.error(f"aborting after {errors} consecutive backend errors")
            if a.delay_s: time.sleep(a.delay_s)
    print(f"Ledger: {a.ledger}"); print(f"Component-audit candidates accumulated: {candidates}"); print(f"Existing UI/CSV rows parity-checked (known M>=3 only): {parity}"); print(f"Existing UI/CSV rows parity-skipped due invalid old M>=3 contract: {parity_skipped}"); return 0

if __name__=="__main__": raise SystemExit(main())
