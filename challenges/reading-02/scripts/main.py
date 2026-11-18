#!/usr/bin/env python3
"""reading-02 科研图表解析 runner: stdlib only, offline, CWD independent, exit 0.
discover -> legal partial result.json -> figure structure -> literal tables ->
axis calibration + digitisation from Agent readings -> evidence check -> finalize.
"""
import argparse, csv, io, json, re, sys, time, traceback, zipfile, zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
  import parsekit as PK
  FLE = ""
except Exception as e:
  PK, FLE = None, str(e)
ROOT = Path(__file__).resolve().parent.parent
V = "1.0.0"
RDL = ("directly_read", "inferred", "undetermined")
NUM = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")
FK = ("figure_id", "panel", "caption", "image_px", "plot_box_px", "ticks_px",
      "spacing", "axes", "color_clusters", "legend_candidates", "elements", "digitized",
      "traceable", "warnings", "calibration_notes")


def now():
  return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def wj(p, o):
  p = Path(p); p.parent.mkdir(parents=True, exist_ok=True)
  p.write_text(json.dumps(o, ensure_ascii=False, indent=2), encoding="utf-8")


def lj(p):
  try:
    return json.loads(Path(p).read_text(encoding="utf-8", errors="replace")), ""
  except Exception as e:
    return None, "%s: %s" % (type(e).__name__, e)


def sha(p):
  h = __import__("hashlib").sha256()
  with open(p, "rb") as f:
    for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
  return h.hexdigest()


def flat(t):
  """Whitespace/punctuation tolerant form for verbatim quote matching."""
  t = re.sub(r"[\u2010-\u2015\u2212]", "-", t or "")
  t = re.sub(r"[\u2018\u2019]", "'", re.sub(r"[\u201c\u201d]", '"', t))
  return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff%.+-]", "", t).lower()


def nums(t):
  return [float(x) for x in NUM.findall(str(t))]


def num(v):
  """Parse a printed tick label: '1,000' / '1e3' / '10^3' / '-2.5'."""
  if isinstance(v, (int, float)): return float(v)
  s = str(v if v is not None else "").strip().replace(",", "").replace("\u2212", "-")
  m = re.match(r"^10\s*\^\s*([-+]?\d+)$", s)
  if m: return 10.0 ** int(m.group(1))
  m = NUM.search(s)
  try: return float(m.group(0)) if m else None
  except ValueError: return None


def declared(case):
  """Organizer must-do objects, found semantically (no fixed key names)."""
  blob, tids = json.dumps(case, ensure_ascii=False), []

  def walk(o):
    if isinstance(o, dict):
      for k, v in o.items():
        if isinstance(v, list) and "table" in k.lower() and all(isinstance(x, str) for x in v):
          tids.extend(v)
        walk(v)
    elif isinstance(o, list):
      for v in o: walk(v)

  walk(case)
  seen, imgs = set(), []
  for f in re.findall(r"[\w./\-]+\.(?:png|jpe?g|tiff?|bmp)", blob):
    if Path(f).name not in seen:
      seen.add(Path(f).name)
      imgs.append(f)
  return imgs, sorted({t for t in tids if t})


def text_of(p):
  k = PK.sniff(p) if PK else "text"
  if k == "pdf": return PK.pdf_text(p)
  if k in ("text", "csv", "json"):
    try: return Path(p).read_text(encoding="utf-8", errors="replace")[:400000]
    except OSError: return ""
  return ""


# --------------------------------------------------------- figure reading
def readings_for(cli, inp, work, out):
  for p in ([Path(cli)] if cli else []) + [work / "readings.json", inp / "readings.json",
                                           out / "readings.json", ROOT / "readings.json"]:
    if p and Path(p).is_file():
      o, e = lj(p)
      return (o if isinstance(o, dict) else {}), str(p), e
  return {}, "", "no readings.json supplied"


def rd_of(rd, sid):
  f = rd.get("figures") or {}
  return f.get(sid) or f.get(Path(sid).name) or {}


def calibrate(fig, rd):
  """Cross-check Agent tick labels against tool-detected tick pixels, then fit."""
  axes, notes, det = {}, [], fig.get("ticks_px") or {}
  for key in ("x", "y", "y2"):
    spec = (rd.get("axes") or {}).get(key)
    if not isinstance(spec, dict): continue
    lab = spec.get("tick_labels") or spec.get("labels") or []
    lab = [lab] if isinstance(lab, (str, int, float)) else lab
    px = spec.get("tick_px") or det.get(key if key != "y2" else "y") or []
    vals = [v for v in (num(x) for x in lab) if v is not None]
    if not (vals and px):
      notes.append({"axis": key, "issue": "tick labels or tick pixels missing",
                    "n_labels": len(lab), "n_tick_px": len(px)})
      continue
    if len(lab) != len(px):
      notes.append({"axis": key, "issue": "label/pixel count mismatch", "n_labels": len(lab),
                    "n_detected_ticks": len(px), "action": "pairing from the axis origin"})
    n = min(len(vals), len(px))
    cal = PK.calibrate(px[:n], vals[:n], spec.get("scale", "auto"))
    if cal:
      cal.update({"axis": key, "unit": spec.get("unit"), "label": spec.get("label"),
                  "tick_labels": lab, "tick_px": px[:n]})
      axes[key] = cal
  return axes, notes


def verify(res, ctx):
  """Deterministic self-check: contract keys, claim schema, verbatim quotes."""
  bad, per = [], []
  miss = [k for k in ctx["contract"] if k not in res]
  if miss: bad.append("contract keys missing: %s" % miss)
  for c in res.get("claims") or []:
    ev, ci = c.get("evidence") or {}, []
    cid = c.get("claim_id") or "?"
    for f in ("kind", "text", "evidence", "readability", "conditions"):
      if not c.get(f): ci.append("missing field %s" % f)
    for f in ("quote", "quote_type", "source_id", "location"):
      if not ev.get(f): ci.append("evidence missing %s" % f)
    if c.get("readability") not in RDL: ci.append("invalid readability %r" % c.get("readability"))
    q, qt, sid = ev.get("quote") or "", ev.get("quote_type"), str(ev.get("source_id"))
    body = ctx["texts"].get(sid) or ctx["texts"].get(Path(sid).name) or ""
    qm = "n/a"
    if qt == "text" and q:
      if not body:
        qm = "source_not_indexed"; ci.append("quote source not indexed: %s" % sid)
      elif q in body: qm = "exact"
      elif flat(q) and flat(q) in flat(body): qm = "normalized"
      else:
        qm = "not_found"; ci.append("verbatim quote not found in source")
    elif qt == "visual":
      px = (ctx["figures"].get(sid) or {}).get("image_px") or {}
      bb = (ev.get("location") if isinstance(ev.get("location"), dict) else {}).get("bbox_px")
      if bb and px:
        ok = 0 <= bb[0] <= bb[2] <= px.get("w", 0) and 0 <= bb[1] <= bb[3] <= px.get("h", 0)
        qm = "bbox_in_bounds" if ok else "bbox_out_of_bounds"
        if not ok: ci.append("visual bbox outside image")
      else: qm = "locator_only"
    per.append({"claim_id": cid, "issues": ci, "quote_match": qm})
    bad += ["%s: %s" % (cid, i) for i in ci]
  hard = [i for i in bad if any(k in i for k in (
      "missing field", "evidence missing", "not found in source", "outside image",
      "invalid readability", "contract keys missing"))]
  return {"checked_at": now(), "n_claims": len(res.get("claims") or []),
          "n_contract_keys": len(ctx["contract"]), "issues": bad[:60],
          "claim_checks": per, "hard_failures": len(hard)}


def finalize(ctx):
  """Unconditional legal result.json: contract keys first, extras preserved."""
  spec, payload = ctx["contract"], ctx["payload"]
  final = {}
  for k in spec: final[k] = None
  for k, v in (("case_id", ctx["case_id"]), ("status", ctx["status"]), ("result", payload),
               ("claims", ctx["claims"]), ("uncertainties", ctx["uncertainties"]),
               ("uncertainty", ctx["uncertainty"]), ("sources", ctx["sources"]),
               ("pending_human", ctx["pending_human"]), ("errors", ctx["errors"]),
               ("degradations", ctx["degradations"]), ("changes", ctx["changes"]),
               ("runtime", ctx["runtime"])):
    final[k] = final[k] if final.get(k) is not None else v
  final["output_contract_spec"] = spec
  final["skill"] = {"name": "reading-02-scientific-figure-parser", "version": V,
                    "readability_levels": list(RDL)}
  final["verification"] = verify(final, ctx)
  if final["verification"]["hard_failures"] and final["status"] in ("answered", "ok"):
    final["status"] = ctx["status"] = "partial"
    final["errors"].append("status downgraded: verification failure")
  wj(ctx["out"] / "result.json", final)
  return final


def run(ctx):
  inp, out = ctx["input"], ctx["out"]
  ch, dg = ctx["changes"].append, ctx["degradations"].append
  un, ph = ctx["uncertainties"].append, ctx["pending_human"].append
  case, err = lj(inp / "case.json")
  if case is None:
    for p in sorted(inp.rglob("case*.json")):
      case, err = lj(p)
      if case is not None:
        ch({"step": "discover", "note": "case read from %s" % p.name}); break
  case = case if isinstance(case, dict) else {}
  if not case:
    ctx["errors"].append("case.json unreadable: %s" % err)
    ctx["status"] = "insufficient_evidence" if "FileNotFound" in err else "input_error"
    ctx["uncertainty"]["fatal"] = "no case: %s" % err
  ctx["case"] = case
  ctx["contract"] = case.get("output_contract") if isinstance(case.get("output_contract"), dict) else {}
  ctx["case_id"] = case.get("case_id") or "unknown-case"
  files = PK.files_of(inp)
  ctx["sources"] = [{"source_id": str(p.relative_to(inp)),
                     "kind": (PK.sniff(p) if PK else "text"), "bytes": p.stat().st_size,
                     "sha256": sha(p), "path": str(p)} for p in files]
  for p in files:
    if p.suffix.lower() in (".md", ".txt", ".json", ".csv", ".pdf") and p.name != "case.json":
      t = text_of(p)
      if t: ctx["texts"][str(p.relative_to(inp))] = t
  if (inp / "task.md").is_file():
    ctx["texts"]["task.md"] = (inp / "task.md").read_text(errors="replace")
  ctx["runtime"]["input_files"] = len(files)
  wj(out / "result.json", {"case_id": ctx["case_id"], "status": "partial", "result": None,
                           "claims": [], "uncertainties": [], "sources": ctx["sources"],
                           "note": "legal first-pass partial",
                           "runtime": ctx["runtime"]})
  ch({"step": "partial", "note": "legal partial result.json written"})
  req_imgs, req_tids = declared(case)
  readings, rpath, rerr = readings_for(ctx["cli_readings"], inp, ctx["work"], out)
  if rerr:
    dg("readings unavailable: %s" % rerr)
    ctx["uncertainty"]["visual_readings"] = ("No readings.json: axis labels, units, legend text "
                                            "and captions not attached; only pixel-structural "
                                            "facts are reported.")
  else:
    ch({"step": "readings", "note": "merged %s" % rpath})
  figs, cov, missing = {}, [], []
  imgs = [p for p in files if (PK.sniff(p) if PK else "") in ("png", "bmp", "jpeg", "tiff")]
  for p in imgs[:8]:
    sid = str(p.relative_to(inp))
    if not PK or PK.sniff(p) != "png":
      figs[sid] = {"file": sid, "traceable": False, "image_px": {},
                   "warnings": ["no decoder for %s" % (PK.sniff(p) if PK else "?")]}
      dg("%s: raster decode unsupported, visual reading only" % sid)
      ph({"item": sid, "why": "not decodable offline",
          "action": "enter axis/legend/points via readings.json"})
      continue
    f, rd = PK.analyze_image(p), rd_of(readings, sid)
    f["source_id"] = sid
    for k in ("figure_id", "panel", "caption"): f[k] = rd.get(k)
    f["elements"] = rd.get("elements") or {}
    axes, notes = calibrate(f, rd) if rd else ({}, [])
    f["axes"], f["calibration_notes"] = axes, notes
    for n in notes: un({"kind": "calibration", "figure": sid, "detail": n})
    figs[sid] = f
    cov.append({"source_id": sid, "analyzed": True,
                "declared": any(Path(r).name == p.name for r in req_imgs)})
  for r in req_imgs:
    if not any(Path(r).name == Path(c["source_id"]).name for c in cov):
      missing.append(r)
      ctx["uncertainty"].setdefault("missing_materials", []).append(r)
  ctx["figures"] = figs
  tables = []
  for p in files:
    kind, sid = (PK.sniff(p) if PK else ""), str(p.relative_to(inp))
    try:
      if kind == "csv":
        t = PK.csv_table(p); t.update({"table_id": Path(p).stem, "source_id": sid})
        tables.append(t)
      elif kind == "json":
        for t in PK.json_tables(lj(p)[0] or {}):
          t["source_id"] = sid; tables.append(t)
      elif kind in ("xlsx", "docx"):
        dg("%s: Office container kept as text source; cells not parsed" % sid)
    except Exception as e:
      dg("%s: table extraction failed (%s)" % (sid, e))
  if tables:
    wj(out / "tables.json", tables)
    for i, t in enumerate(tables):
      try:
        (out / "tables").mkdir(parents=True, exist_ok=True)
        nm = re.sub(r"[^\w.-]+", "_", str(t.get("table_id") or "t%d" % i))[:60]
        with open(out / "tables" / (nm + ".csv"), "w", newline="", encoding="utf-8") as fh:
          csv.writer(fh).writerows(t.get("grid") or [])
      except Exception as e: dg("table csv write failed: %s" % e)
  blob = flat(" ".join(ctx["texts"].values())) + flat(json.dumps(case, ensure_ascii=False)) + \
      flat(json.dumps(tables, ensure_ascii=False))
  cov_t, miss_t = [], []
  for tid in req_tids:
    hit = flat(tid) in blob
    cov_t.append({"table_id": tid, "resolved": hit})
    if not hit:
      miss_t.append(tid)
      ph({"item": tid, "why": "declared table id absent",
          "action": "locate the literal table or confirm absence"})
  rows = []
  for sid, f in figs.items():
    rd, ax = rd_of(readings, sid), f.get("axes") or {}
    if not rd.get("series") or not f.get("traceable") or not ax.get("y"): continue
    try: img, meta = PK.load_image(inp / sid)
    except Exception as e:
      dg("%s: re-decode failed (%s)" % (sid, e)); continue
    box = tuple(int(round(v / meta["analysis_scale"])) for v in f["plot_box_px"])
    for s in rd.get("series") or []:
      if not (s.get("digitize") and s.get("rgb")): continue
      got = PK.digitize_img(img, box, s["rgb"], ax.get("x"), ax["y"],
                            meta["analysis_scale"], tol=int(s.get("tol", 60)))
      for r in got:
        r.update({"figure": f.get("figure_id") or sid, "panel": f.get("panel"),
                  "series": s.get("name") or str(s.get("rgb")),
                  "x_unit": (ax.get("x") or {}).get("unit"), "y_unit": ax["y"].get("unit")})
        rows.append(r)
      f.setdefault("digitized", []).append({"series": s.get("name"), "rgb": s.get("rgb"),
                                            "n_points": len(got), "source_id": sid})
  if rows:
    keys = ["figure", "panel", "series", "x", "y", "y_lo", "y_hi", "x_unit", "y_unit",
            "err_x_data", "err_y_data", "x_px", "y_px", "approx"]
    with open(out / "digitized_series.csv", "w", newline="", encoding="utf-8") as fh:
      wr = csv.DictWriter(fh, fieldnames=keys, extrasaction="ignore")
      wr.writeheader()
      for r in rows: wr.writerow(r)
  wj(out / "figure_structure.json", figs)
  claims = []
  for i, c in enumerate(readings.get("claims") or [], 1):
    ev = c.get("evidence") or {}
    claims.append({
        "claim_id": c.get("claim_id") or "c%02d" % i, "kind": c.get("kind") or "value",
        "text": c.get("text"),
        "evidence": {"quote": ev.get("quote") or "",
                     "quote_type": ev.get("quote_type") or
                     ("visual" if ev.get("bbox_px") or ev.get("figure") else "text"),
                     "source_id": ev.get("source_id"), "location": ev.get("location") or {},
                     "read_basis": ev.get("read_basis") or ""},
        "readability": c.get("readability") or "undetermined",
        "conditions": c.get("conditions") or "as shown in the supplied material"})
  ctx["claims"] = claims
  for u in readings.get("uncertainties") or []: un(u if isinstance(u, dict) else {"note": str(u)})
  for x in readings.get("pending_human") or []: ph(x if isinstance(x, dict) else {"item": str(x)})
  counts = {"required_images": len(req_imgs), "images_analyzed": len(cov),
            "images_missing": len(missing), "tables_extracted": len(tables),
            "required_tables": len(req_tids),
            "required_tables_resolved": sum(1 for c in cov_t if c["resolved"]),
            "claims": len(claims), "digitized_points": len(rows)}
  ok_img = len(cov) >= len(req_imgs) if req_imgs else bool(cov)
  ctx["payload"] = {
      "task": case.get("task_instruction") or "", "domain": case.get("domain"),
      "figures": {sid: {k: f.get(k) for k in FK} for sid, f in figs.items()},
      "tables": [{"table_id": t.get("table_id"), "source_id": t.get("source_id"),
                  "columns": t.get("columns"), "n_rows": t.get("n_rows")} for t in tables],
      "digitized_series_file": "digitized_series.csv" if rows else None,
      "coverage": {"images": cov, "tables": cov_t, "missing_images": missing,
                   "missing_tables": miss_t}, "counts": counts}
  ctx["status"] = ctx["status"] if ctx["status"] == "input_error" else \
      ("answered" if (claims and ok_img and not missing and not rerr)
                   else "partial" if (figs or tables or claims) else "insufficient_evidence")
  if ctx["status"] == "partial":
    ctx["uncertainty"]["scope"] = ("analysed objects only; unlisted figures or "
                                   "tables are declared gaps")
  ctx["uncertainty"]["counts"] = counts


def build_parser():
  p = argparse.ArgumentParser(
      description="reading-02 科研图表解析: case -> result.json + digitised CSV + checked claims",
      epilog="Example: python3 main.py --input ./input --output ./output --readings readings.json")
  p.add_argument("--input", help="case dir (case.json, task.md, artifacts/)")
  p.add_argument("--output", help="output dir for result.json and artefacts")
  p.add_argument("--readings", help="Agent visual readings JSON")
  p.add_argument("--version", action="version", version=V)
  return p


def pick(cli, cands, create=False):
  for c in ([cli] if cli else []) + cands:
    if not c: continue
    if Path(c).is_dir(): return Path(c)
    if create and c == cli:
      try:
        Path(c).mkdir(parents=True, exist_ok=True); return Path(c)
      except OSError: pass
  if create:
    for c in cands:
      try:
        Path(c).mkdir(parents=True, exist_ok=True); return Path(c)
      except OSError: continue
  return Path(cands[-1])


def main(argv=None):
  a = build_parser().parse_args(argv)
  t0 = time.time()
  inp = pick(a.input, ["/input", str(ROOT / "input")])
  out = pick(a.output, ["/app/output", str(ROOT.parent / "output")], create=True)
  work = out / "work"
  try: work.mkdir(parents=True, exist_ok=True)
  except OSError: work = out
  ctx = {"cli_readings": a.readings, "input": inp, "out": out, "work": work, "contract": {},
         "case": {}, "case_id": "unknown-case", "claims": [], "uncertainties": [],
         "pending_human": [], "sources": [], "errors": [], "degradations": [], "changes": [],
         "figures": {}, "texts": {}, "payload": {}, "status": "partial", "uncertainty": {},
         "runtime": {"skill": "reading-02-scientific-figure-parser", "version": V,
                     "started_utc": now(), "python": sys.version.split()[0],
                     "input_dir": str(inp), "output_dir": str(out),
                     "parsekit": "ok" if PK else FLE[:120]}}
  if not PK: ctx["degradations"].append("figurelab import failed: %s" % FLE)
  try:
    run(ctx)
  except Exception:
    ctx["errors"].append("fatal: " + traceback.format_exc(limit=3).replace("\n", " | ")[:900])
    ctx["status"] = "partial" if ctx.get("payload") else "insufficient_evidence"
    ctx["uncertainty"]["fatal"] = "run aborted; see errors"
  finally:
    try:
      ctx["runtime"].update({"duration_s": round(time.time() - t0, 2), "finished_utc": now()})
      finalize(ctx)
    except Exception:
      try:
        wj(ctx["out"] / "result.json", {
            "case_id": ctx.get("case_id", "unknown-case"), "status": "input_error",
            "result": None, "claims": [], "uncertainties": ctx.get("uncertainties", []),
            "errors": ctx.get("errors", []) + ["finalize failed"],
            "runtime": ctx.get("runtime", {})})
      except Exception: pass
  print(json.dumps({"status": ctx.get("status"), "output": str(ctx["out"]),
                    "errors": len(ctx["errors"]), "degradations": len(ctx["degradations"]),
                    "claims": len(ctx.get("claims") or [])}, ensure_ascii=False))
  return 0


if __name__ == "__main__":
  try: sys.exit(main())
  except SystemExit: raise
  except Exception: sys.exit(0)
