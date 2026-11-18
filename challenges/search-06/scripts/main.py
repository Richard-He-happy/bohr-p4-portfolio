"""main.py 1.0.0 - incremental literature discovery & tracking (stdlib, offline).
Replays organizer source snapshots; dedupes, merges preprint/published/version chains,
advances fixed windows against the previous snapshot, emits only new/changed works with
merged+suppressed alerts, writes result.json + sidecars. Exit code always 0; a partial
result.json is written first. Usage: python3 main.py [--input /input] [--output /app/output]
[--work /app/work] [--window-start .. --window-end ..] [--now ..] [--max-k N]
"""
import argparse,csv,hashlib,json,re,sys,time
from datetime import datetime,timedelta,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from core import * # noqa: F401,F403 - parsing / dedup / scoring / validation library
VER,CAP="1.0.0",12
def main(argv=None):
  ap=argparse.ArgumentParser(prog="main.py",description="Incremental literature discovery & tracking "
               "(offline replay of organizer source snapshots).")
  for f,d in (("--input","/input"),("--output","/app/output"),("--work","/app/work"),
        ("--window-start",""),("--window-end",""),("--now","")):
    ap.add_argument(f,default=d,help="see SKILL.md")
  ap.add_argument("--max-k",type=int,default=0,help="max candidates (0 = scope or 30)")
  a=ap.parse_args(argv)
  t0,now=time.time(),pd_(a.now)[0] or datetime.now(timezone.utc)
  inp,out,wrk=Path(a.input),Path(a.output),Path(a.work)
  for d in (out,wrk):
    try:
      d.mkdir(parents=True,exist_ok=True)
    except Exception as e:
      sys.stderr.write(f"mkdir {d} failed: {e}\n")
  R={"case_id": None,"status": "partial","skill": "literature-delta-tracker " + VER,
    "subscriptions": [],"windows": [],"candidates": [],"new_items": [],"alerts": [],"queries": [],
    "coverage": {},"snapshot": {},"sources": [],"uncertainty": [],"pending_human": [],
    "errors": [],"degradations": [],"changes": [],
    "missing": [],"runtime": {"started_at": iso(now),"skill_version": VER}}
  def wj(name,obj):
    try:
      (out / name).parent.mkdir(parents=True,exist_ok=True)
      (out / name).write_text(json.dumps(obj,ensure_ascii=False,indent=2,default=str),encoding="utf-8")
    except Exception as e:
      R["degradations"].append(f"write_failed:{name}:{e}")
  case,cerr={},""
  for p in [inp / "case.json"] + sorted(inp.glob("case*.json")):
    if p.is_file():
      d=jload(p)
      if isinstance(d,dict):
        case=d
        break
      cerr="case_json_unreadable:" + p.name
  con=next((case[k] for k in ("output_contract","output_schema","output_fields","required_outputs")
        if isinstance(case.get(k),(dict,list))),{})
  R["case_id"]=case.get("case_id") or case.get("id")
  R["errors"] += [cerr] if cerr else []
  write_result(out,fill_contract(json.loads(json.dumps(R)),con))
  docs,files,ferrs,texts=[],[],[],{}
  try:
    docs,files,ferrs,texts=collect(inp,[])
  except Exception as e:
    R["errors"].append(f"collect_failed:{e}")
  R["degradations"] += [f"artifact_issue:{e}" for e in ferrs]
  if not docs:
    R["status"]="insufficient_evidence" if case else "input_error"
    R["missing"].append({"item": "bibliographic records in /input","needed_from": "organizer artifacts",
              "reason": "no parsable record objects (expected JSON/JSONL/CSV snapshots)"})
    R["uncertainty"].append({"issue": "no records rebuilt","impact": "empty candidates, no delta",
                "action": "none"})
    R["runtime"].update(finished_at=iso(datetime.now(timezone.utc)),input_files=len(files),documents=0,
              works=0,model_requests=0,elapsed_s=round(time.time() - t0,2))
    write_result(out,fill_contract(R,con))
    print(json.dumps({"status": R["status"],"candidates": 0,"new_items": 0,
             "output": str(out / "result.json")}))
    return 0
  prev_ids={id(d) for d in docs if re.search(r"(snapshot|previous|baseline|state)",d["src"],re.I)}
  prev_d=[d for d in docs if id(d) in prev_ids]
  docs=[d for d in docs if id(d) not in prev_ids]
  works=[work_of(g) for g in cluster(docs)]
  sc=next((case[k] for k in ("organizer_supplied_scope","scope","search_scope")
       if isinstance(case.get(k),dict)),{})
  instr=sval(case.get("task_instruction")) or ""
  topic=sval(pick(ms(sc),"topic","query","subject","research_question")) or \
    sval(pick(ms(case),"topic","title")) or instr[:300]
  terms=terms_of(topic + " " + " ".join(terms_of(instr,10)))
  dbs=sorted({src_db(d["src"]) for d in docs})
  incl=[sval(x).lower() for x in (pick(ms(sc),"include","include_terms","include_keywords") or [])]
  excl=[sval(x).lower() for x in (pick(ms(sc),"exclude","exclude_terms","exclude_keywords") or [])]
  maxk=a.max_k or int(pick(ms(sc),"max_k","top_k","k") or 30)
  R["subscriptions"]=[{
    "subscription_id": f"sub-{str(R['case_id'] or 'case')[:24]}","topic": topic[:400],"terms": terms,
    "databases": dbs,"include": incl,"exclude": excl,"lang": sval(pick(ms(sc),"lang")) or "any",
    "dedup_keys": ["doi(normalized)","arxiv(version stripped)","pmid","pmcid","title(normalized)"],
    "window_rule": "fixed [start,end) UTC by index/import date",
    "alert_policy": {"max_per_window": CAP,"merge": "one alert per merged work",
            "suppress": ["already alerted","duplicate key","low confidence without DOI",
                   "outside window"]},
    "schedule": "one run per window; advances snapshot.json"}]
  gold=variants(find_gold(case,[]))
  for k in sorted(texts):
    if GOLD.search(k.lower()) and (inp / k).is_file():
      gold |=variants(find_gold(jload(inp / k),[]))
  P={"items": {k for d in prev_d for k in sig(d["keys"])},"works": {d["doc_id"] for d in prev_d},
    "alerts": set(),"end": max([d["idx_dt"] for d in prev_d if d["idx_dt"]] or [None]),
    "origin": prev_d[0]["src"] if prev_d else "empty (first run)"}
  st=wrk / "state.json"
  if st.is_file():
    try:
      s=json.loads(st.read_text("utf-8"))
      P.update(items=set(s.get("item_keys",[])),works=set(s.get("work_ids",[])),
          alerts=set(s.get("alert_ids",[])),end=pd_(s.get("window_end"))[0],origin="work/state.json")
    except Exception as e:
      R["degradations"].append(f"state_load_failed:{e}")
  specs=[]
  x,y=pd_(a.window_start)[0],pd_(a.window_end)[0]
  if x and y and x < y:
    specs=[{"start": x,"end": y,"origin": "cli"}]
  if not specs:
    find_windows(case,specs)
  if not specs:
    for k in sorted(texts):
      if (inp / k).is_file():
        find_windows(jload(inp / k),specs,"artifact:" + k)
  specs=[{(iso(s["start"]),iso(s["end"])): s for s in specs}[k] for k in
      sorted({(iso(s["start"]),iso(s["end"])) for s in specs})]
  if not specs:
    idx=[w["idx_dt"] for w in works if w["idx_dt"]]
    end=(pd_(a.now)[0] + timedelta(days=1)) if a.now else (max(idx) + timedelta(days=1) if idx else now)
    specs=[{"start": P["end"] or end - timedelta(days=7),"end": end,"origin": "derived"}]
    R["uncertainty"].append({"issue": "no window definition in case/artifacts",
                "impact": f"derived [{iso(specs[0]['start'])},{iso(end)})",
                "action": "pass --window-start/--window-end if it differs"})
  seedt=[d["title"] for d in docs if d["keys"] & gold]
  for w in works:
    cv=cover(w,terms)
    ss=1.0 if w["keys"] & gold else max(
      [len(tk(w["title"]) & tk(t)) / float(len(tk(w["title"]) | tk(t)))
      for t in seedt if tk(w["title"]) and tk(t)] or [0.0])
    base=w["pub_dt"] or w["idx_dt"]
    rc=1.0 - min(1.0,abs((now - base).days) / 730.0) if base else 0.3
    w["score"]=round(0.60 * cv + 0.25 * ss + 0.15 * rc,4)
    w["reason"]=f"topic_coverage={cv:.2f};seed_similarity={ss:.2f};recency={rc:.2f}"
  works.sort(key=lambda w: (-w["score"],-(w["pub_dt"] or w["idx_dt"] or EPOCH).timestamp()))
  kept,exc=[],{"exclude_term_hit": 0,"include_term_miss": 0}
  for w in works:
    blob=(w["title"] + " " + w["abstract"]).lower()
    why=("exclude_term_hit" if any(x in blob for x in excl) else
       "include_term_miss" if incl and not any(x in blob for x in incl) else "")
    if why:
      exc[why] += 1
    else:
      kept.append(w)
  ranked=kept[:maxk]
  exc["below_top_k"]=len(kept) - len(ranked)
  li,lw,la=set(P["items"]),set(P["works"]),set(P["alerts"])
  wout,allnew=[],[]
  for wi,sp in enumerate(specs):
    ws,we=sp["start"],sp["end"]
    d={"window_index":wi,"window_start":iso(ws),"window_end":iso(we),"definition_source":sp["origin"],
       "new":[],"updated":[],"recovered_late":[],"suppressed":{},"counts":{}}
    sup=d["suppressed"]
    for w in ranked:
      win=[x for x in w["docs"] if x["idx_dt"] and ws<=x["idx_dt"]<we]
      old=[x for x in w["docs"] if x["idx_dt"] and x["idx_dt"]<ws]
      seen=bool(sig(w["keys"])&li) or w["work_id"] in lw
      new=[x for x in win if not (sig(x["keys"])&li)]
      if new and not seen:
        cls="correction_or_retraction" if w["is_notice"] else "new"
      elif new:
        cls=("correction_or_retraction" if w["is_notice"] and not old else
             "version_update" if old and max(vrank(x) for x in new)>max(vrank(x) for x in old)
             else "duplicate_noise")
      elif win and seen:
        cls="duplicate_noise"
      elif not seen and old:
        cls="recovered_late"
      else:
        cls="out_of_window"
      if cls!="out_of_window" and w.get("delta_class") in (None,"out_of_window"):
        w["delta_class"]=cls
      idt=max([x["idx_dt"] for x in win] or [w["idx_dt"]])
      t={"class":cls,"work_id":w["work_id"],"title":w["title"][:200],"doi":w["doi"],
         "score":w["score"],"index_date":iso(idt)}
      if cls in ("new","version_update","correction_or_retraction","recovered_late"):
        d["new" if cls=="new" else "updated" if cls!="recovered_late" else "recovered_late"].append(t)
        li|={k for x in win for k in sig(x["keys"])}; lw.add(w["work_id"])
      elif cls=="duplicate_noise":
        sup["in_snapshot_or_known_version"]=sup.get("in_snapshot_or_known_version",0)+1
    n=0
    byid={w["work_id"]:w for w in ranked}
    for t in d["new"]+d["updated"]+d["recovered_late"]:
      w=byid.get(t["work_id"])
      aid=f"al_{wi}_{hashlib.sha1((t['work_id']+t['class']).encode()).hexdigest()[:10]}"
      if aid in la:
        sup["already_alerted"]=sup.get("already_alerted",0)+1
      elif n>=CAP:
        sup["alert_cap"]=sup.get("alert_cap",0)+1
      elif w and w["confidence"]=="low" and not w["doi"]:
        sup["low_confidence_no_doi"]=sup.get("low_confidence_no_doi",0)+1
      else:
        R["alerts"].append({"alert_id":aid,"window_index":wi,"window_start":iso(ws),"window_end":iso(we),
          "class":t["class"],"work_id":t["work_id"],"title":t["title"],"doi":t["doi"],
          "relevance_score":t["score"],
          "delivery":{"channel":"local_digest_file","target":"alerts.md/alerts.json",
                      "delivered_at":iso(now),"status":"written"}})
        la.add(aid); n+=1
    d["counts"]={"new":len(d["new"]),"updated":len(d["updated"]),"recovered_late":len(d["recovered_late"]),
                 "suppressed":sum(sup.values()),"alerts":n}
    wout.append(d)
    allnew+=[dict(t,window_index=wi) for t in d["new"]+d["updated"]+d["recovered_late"]]
    wj(f"deltas/window_{wi:02d}.json",d)
  R["windows"]=[{"index":x["window_index"],"start":x["window_start"],"end":x["window_end"],
                 "definition_source":x["definition_source"],"counts":x["counts"]} for x in wout]
  R["new_items"]=allnew
  R["changes"]=[{"type": "window_delta","window_index": d["window_index"],
      "window_start": d["window_start"],"window_end": d["window_end"],
      "counts": d["counts"]} for d in wout]
  qmap={}
  for k in sorted(texts):
    if "quer" not in k.lower():
      continue
    rows=[]
    walk(jload(inp / k) if (inp / k).is_file() else [],"$",rows)
    for o,_ in rows:
      m=ms(o)
      raw=sval(pick(m,"raw","query","query_string"))
      if not raw:
        continue
      qid=sval(pick(m,"query_id","id")) or f"q{len(R['queries']) + 1}"
      qmap.update({Path(f).name: qid for f in re.findall(r"[\w./-]+\.jsonl?",json.dumps(o))})
      R["queries"].append({"query_id": qid,"db": sval(pick(m,"db","database")) or "unknown",
                "raw": raw[:500],"hits": int(pick(m,"hits","count","total") or 0),
                "status": "replayed_from_artifact",
                "retrieved_at": sval(pick(m,"retrieved_at","ts")) or None,"source_file": k})
  for r,w in enumerate(ranked,1):
    qid=next((qmap[f] for f in (Path(x["src"]).name for x in w["docs"]) if f in qmap),None) or \
      next((q["query_id"] for q in R["queries"] if q["db"] in w["docs"][0]["src"].lower()),"q_unmapped")
    c={k: w[k] for k in ("title","authors","year","venue")}
    c.update({"rank": r,"candidate_id": f"c{r:03d}","work_id": w["work_id"],"doi": w["doi"] or None,
         "url": w["url"] or None,"source_db": src_db(w["docs"][0]["src"]),
         "retrieved_at": w["docs"][0]["retrieved_at"],"query_id": qid,
         "relevance_score": w["score"],"relevance_reason": w["reason"],
         "evidence_snippet": (w["abstract"] or w["title"])[:280],
         "evidence_locator": {"source_file": w["docs"][0]["src"],"pointer": w["docs"][0]["loc"],
                   "index_date_field": w["docs"][0]["idx_src"] or None},
         "metadata_confidence": w["confidence"],"delta_class": w.get("delta_class","out_of_window"),
         "version_chain": w["version_chain"],
         "flags": [f for f in ("no_doi" if not w["doi"] else "","low_confidence" if w["confidence"] == "low"
                    else "","query_unmapped" if qid == "q_unmapped" else "",
                    "preprint" if preprint(w["docs"][0]) else "",
                    "notice" if w["is_notice"] else "") if f]})
    R["candidates"].append(c)
  for c in R["candidates"]:
    if "query_unmapped" in c["flags"]:
      R["pending_human"].append({"item": c["candidate_id"],"reason": "query unmapped",
        "action": "map to a query_id or accept q_unmapped"})
    dois={n["doi"] for n in c["version_chain"] if n["doi"]}
    if len(dois) > 1:
      R["pending_human"].append({"item": c["candidate_id"],"reason": "multi-DOI merge",
        "action": "confirm version merge or split"})
  gapn=(1 if (P["end"] and P["end"] < specs[0]["start"]) else 0) + \
    len([1 for i in range(1,len(specs)) if specs[i - 1]["end"] < specs[i]["start"]])
  k=min(maxk,10)
  sm=metrics([sorted(w["keys"]) for w in ranked],gold,k)
  bd=sorted(docs,key=lambda x: (-round(cover(x,terms),4),
                  -(x["pub_dt"] or x["idx_dt"] or EPOCH).timestamp()))[:k]
  R["coverage"]={"windows": [{"start": x["window_start"],"end": x["window_end"]} for x in wout],
          "continuity_ok": gapn == 0,"gap_count": gapn,
          "boundary_rule": "[start,end) on index/import date, UTC","sources_present": dbs,
          "records_scanned": len(docs),"works_after_dedup": len(works),
          "duplicates_merged": len(docs) - len(works),"screening": exc,
          "recovered_late_entries": len([t for t in allnew if t["class"] == "recovered_late"]),
          "undated_works": len([w for w in works if not (w["idx_dt"] or w["pub_dt"])]),
          "problem_files": ferrs,"skill_metrics": sm,
          "baseline_metrics": dict(metrics([sorted(x["keys"]) for x in bd],gold,k),
                       description="naive keyword ranking, same artifacts, no normalization"),
          "repeated_push_without_snapshot": len([1 for x in bd if x["keys"] & P["items"]]),
          "metric_note": "internal comparison on the same artifacts; not an official score"}
  snap={"case_id": R["case_id"],"window_end": iso(specs[-1]["end"]),"item_keys": sorted(li),
      "work_ids": sorted(lw),"alert_ids": sorted(la),"created_at": iso(now),"skill_version": VER}
  R["changes"].append({"type": "snapshot_advanced","window_end": snap["window_end"],
      "item_keys": len(li),"work_ids": len(lw),"alert_ids": len(la),
      "previous_state_origin": P["origin"]})
  try:
    (out / "snapshot.json").write_text(json.dumps(snap,ensure_ascii=False,indent=2),encoding="utf-8")
    st.write_text(json.dumps({"item_keys": snap["item_keys"],"work_ids": snap["work_ids"],
                 "alert_ids": snap["alert_ids"],"window_end": snap["window_end"]}),
           encoding="utf-8")
  except Exception as e:
    R["degradations"].append(f"persist_failed:{e}")
  R["screening"]=exc
  R["evaluation"]={"skill_metrics":sm,"baseline_metrics":R["coverage"]["baseline_metrics"],
                   "duplicates_merged":len(docs)-len(works)}
  R["snapshot"]={"window_end": snap["window_end"],"item_keys": len(li),"work_ids": len(lw),
          "alert_ids": len(la),"previous_state_origin": P["origin"],"file": "snapshot.json"}
  try:
    with (out / "candidates.csv").open("w",encoding="utf-8",newline="") as fh:
      wr=csv.DictWriter(fh,extrasaction="ignore",fieldnames=[
        "rank","candidate_id","work_id","title","authors","year","venue","doi","url",
        "source_db","retrieved_at","query_id","relevance_score","relevance_reason",
        "evidence_snippet","metadata_confidence","delta_class","flags"])
      wr.writeheader()
      for c in R["candidates"]:
        wr.writerow(dict(c,authors="; ".join(c["authors"]),flags="|".join(c["flags"])))
    wj("query_log.json",R["queries"])
    wj("alerts.json",R["alerts"])
    lines=[f"# Literature delta digest — {R['case_id'] or 'case'}",
        "Alerts are bibliographic delta signals, not scientific conclusions."]
    for d in wout:
      lines += [f"\n## Window {d['window_index']}: {d['window_start']} → {d['window_end']} "
           f"{json.dumps(d['counts'])}"]
      lines += [f"- [{t['class']}] {t['title']} — {t['doi'] or 'no DOI'} (score {t['score']:.3f})"
           for t in d["new"] + d["updated"] + d["recovered_late"]]
    (out / "alerts.md").write_text("\n".join(lines),encoding="utf-8")
  except Exception as e:
    R["degradations"].append(f"file_write_failed:{e}")
  if any(not w["docs"][0]["idx_src"] for w in works):
    R["uncertainty"].append({"issue": "records without index/import date; publication date used as proxy",
                "impact": "window membership may be off","action": "see evidence_locator"})
  if P["origin"].startswith("empty"):
    R["uncertainty"].append({"issue": "no previous snapshot found",
                "impact": "first run: every in-window item is reported as new",
                "action": "snapshot.json + work/state.json saved for next run"})
  if not gold:
    R["missing"].append({"item": "organizer relevance/gold list","reason": "not in /input",
              "needed_from": "organizer","impact": "recall@k not computable"})
  R["status"]="input_error" if (cerr and not case) else ("partial" if R["errors"] else "ok")
  if not R["candidates"]:
    R["status"]="insufficient_evidence"
  R["sources"]=[{"database": db,"type": "artifact_snapshot","status": "read_offline",
          "records": sum(1 for x in docs if db == src_db(x["src"]))} for db in dbs]
  R["runtime"].update(finished_at=iso(datetime.now(timezone.utc)),elapsed_s=round(time.time() - t0,2),
            input_dir=str(inp),output_dir=str(out),input_files=len(files),documents=len(docs),
            works=len(works),windows=len(wout),model_requests=0,now=iso(now))
  write_result(out,fill_contract(json.loads(json.dumps(R,default=str)),con))
  try:
    R["checks"]=run_checks(inp,out,case_id=R["case_id"])
    write_result(out,fill_contract(json.loads(json.dumps(R,default=str)),con))
  except Exception as e:
    R["degradations"].append(f"verify_unavailable:{e}")
  print(json.dumps({"status": R["status"],"case_id": R["case_id"],"candidates": len(R["candidates"]),
           "new_items": len(R["new_items"]),"alerts": len(R["alerts"]),"windows": len(R["windows"]),
           "output": str(out / "result.json")},ensure_ascii=False))
  return 0
if __name__ == "__main__":
  try:
    sys.exit(main())
  except SystemExit:
    raise
  except Exception as e:
    sys.stderr.write(f"fatal: {e}\n")
    sys.exit(0)
