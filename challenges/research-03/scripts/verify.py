#!/usr/bin/env python3
"""SLR stage 2/2 (stdlib): screen, appraise, synthesise, assemble, report, verify quotes.
Reads work/state.json; writes result.json, review.md, 3 CSVs. Always exits 0."""
import argparse, csv, json, re, sys, time
from pathlib import Path
from datetime import datetime, timezone
SD = Path(__file__).resolve().parent
sys.path.insert(0, str(SD))
import slr_review as S
T0 = time.time(); NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
M, CV, DIMS = S.M, S.CV, ("D1", "D2", "D3", "D4", "D5", "D6")
GW = {"high": 4, "moderate": 3, "low": 2, "very_low": 1}
DF = dict(x.split("=", 1) for x in (
  "D1=aim|objective|目的\nD2=\\bn\\s*=\\s*\\d+|sample|participants|样本\nD3=method|protocol|model|方法\n"
  "D4=\\d+(?:\\.\\d+)?\\s*%|p\\s*[<>=]\\s*0?\\.\\d+|\\bCI\\b|显著\nD5=limitation|bias|局限\nD6=generaliz|外推\n"
  "POS=improv|increas|higher|effective|提升|提高|改善\nNEG=decreas|lower|worse|reduc|降低|下降|恶化\n"
  "NUL=no (?:significant|difference)|not significant|无显著|无差异\n"
  "EDIT=editorial|commentary|erratum|社论|评论|勘误\n"
  "REVW=systematic review|meta-?analysis|系统评价|系统综述|荟萃分析").splitlines())
try:  # retunable via references/appraisal-rubrics.md; a broken pattern only unscores that dimension
  for _l in re.search(r"<!--slr:markers\s*\n(.*?)-->", (S.REF / "appraisal-rubrics.md").read_text(encoding="utf-8"), re.S).group(1).splitlines():
    _p = _l.split("=", 1)
    if len(_p) == 2 and _p[1].strip(): DF[_p[0].strip()] = _p[1].strip()
except Exception: pass

def RX(k):
  try: return re.compile(DF[k], re.I)
  except Exception: return re.compile(r"$^")

def sents(t):
  out = []
  for ln in re.finditer(r"[^\n]+", t):
    for m in re.finditer(r"[^。！？!?\.]+[。！？!?\.]*", ln.group(0)):
      a, b = ln.start() + m.start(), ln.start() + m.end()
      if 25 <= len(t[a:b].strip()) <= 600: out.append((a, b, t[a:b].strip()))
  return out

def DIR(x):
  if RX("NUL").search(x): return "null"
  p, n = len(RX("POS").findall(x)), len(RX("NEG").findall(x))
  return "pos" if p > n else ("neg" if n else "unclear")

def decide(r, T, strict):
  q = r["title"] + " " + r["abstract"]; tx = S.nz(q); n = sum(x in tx for x in T)
  if len(r["title"]) < 8: return "uncertain", "EC0", M("r_notitle"), ""
  m = RX("EDIT").search(q)
  if m and len(tx) < 400: return "exclude", "EC3", M("r_edit"), q[max(0, m.start() - 20):m.end() + 20]
  if not n: return "exclude", "EC1", M("r_off", t=", ".join(T[:4])), r["title"][:160]
  if n < (len(T) if strict else max(1, len(T) // 2)):
    return "uncertain", "IC1", M("r_partial", a=n, b=len(T)), r["title"][:160]
  m2 = RX("REVW").search(q)
  if m2 and not RX("D2").search(q): return "exclude", "EC4", M("r_revno"), q[max(0, m2.start() - 30):m2.end() + 30]
  if not RX("D4").search(q) and not RX("D2").search(q):
    return "uncertain", "IC3", M("r_nores"), (r["abstract"] or r["title"])[:160]
  return "include", "IC1", M("r_ok"), r["title"][:160]

ECOLS = "claim_id theme_id claim_kind record_id appraisal_grade direction source_file extract_file char_start char_end quote locator doi title".split()
SCOLS = "record_id round clause_id verdict verdict_lenient reason_code reason_text evidence_quote criteria_version screener ts title year".split()
ACOLS = "record_id D1 D2 D3 D4 D5 D6 score grade abstract_only".split()

def row(*c): return "| " + " | ".join(str(x) for x in c) + " |"

def pass2(recs, st):
  T = st["core_terms"]; logs = []; G = {}
  def L(r, d, dl, scr, rt):
    logs.append(dict(zip(SCOLS, (r["record_id"], rt, d[1], d[0], dl, d[1], d[2], d[3], CV, scr, NOW,
      r["title"][:160], r["year"]))))
  for r in recs:
    a, b = decide(r, T, True), decide(r, T, False)
    L(r, a, b[0], "A_strict|B_lenient", "R1_title_abstract")
    r["r1"] = "include" if a[0] == b[0] == "include" else ("exclude" if (a[0] == b[0] == "exclude" or
      (a[0] == "exclude" and a[1] in ("EC1", "EC3") and b[0] == "uncertain")) else "uncertain")
    full = r.get("has_full") or r["src"].lower().endswith(".pdf") or len(r["text"]) - len(r["abstract"]) > 400
    if r["r1"] != "exclude":
      r["ft"] = "full" if full else "abstract_only"
      d = ("include", "IC1", M("r_ftok"), r["title"][:160]) if full else ("include_limited", "EC7", M("r_ftsoft"), r["title"][:160])
      L(r, d, d[0], "A_strict", "R2_full_text")
  R1 = [l for l in logs if l["round"] == "R1_title_abstract"]
  A = {l["record_id"]: l["verdict"] == "include" for l in R1}
  B = {l["record_id"]: l["verdict_lenient"] == "include" for l in R1}
  ids = sorted(A); n = max(1, len(ids)); po = sum(A[i] == B[i] for i in ids) / n
  pa = (sum(A.values()) + sum(B.values())) / (2.0 * n); pe = pa * pa + (1 - pa) ** 2
  inc = [r for r in recs if r.get("r1") != "exclude"]
  c1 = {k: sum(r.get("r1") == k for r in recs) for k in ("include", "uncertain", "exclude")}
  sc = dict(logs=logs, included=inc, manual_queue=[r["record_id"] for r in recs if r.get("r1") == "uncertain"],
    rounds=[dict(round="R0_supplied_corpus", n_in=len(recs)), dict(round="R1_title_abstract", n_in=len(recs), **c1),
      dict(round="R2_full_text", n_in=len(inc), include=sum(r.get("ft") == "full" for r in inc),
        include_limited=sum(r.get("ft") == "abstract_only" for r in inc))],
    dual_pass=dict(passes=["A_strict", "B_lenient"], agreement=round(po, 3), note=M("r_dual"),
      cohen_kappa=round((po - pe) / (1 - pe), 3) if pe < 1 else None,
      disagreements=[dict(record_id=i, A_strict=A[i], B_lenient=B[i], final="uncertain->human_queue") for i in ids if A[i] != B[i]]))
  items = []
  for r in inc:
    dims, s2, qs = [], 0, []
    for d in DIMS:
      q = next((x for _a, _b, x in sents(r["text"]) if RX(d).search(x)), None)
      if q: dims.append(d + ":yes"); s2 += 2; qs.append(dict(dim=d, quote=q))
      else: dims.append(d + ":unclear")
    if r.get("ft") == "abstract_only": s2 = min(s2, 6)
    g = "high" if s2 >= 10 else ("moderate" if s2 >= 7 else ("low" if s2 >= 4 else "very_low"))
    if r.get("ft") == "abstract_only" and g in ("high", "moderate"): g = "low"
    G[r["record_id"]] = g
    items.append(dict(record_id=r["record_id"], dimensions=dims, score=s2, grade=g, evidence=qs[:1],
      abstract_only=r.get("ft") == "abstract_only", effect_on_claims=M("a_eff_" + g)))
  app = dict(instrument=dict(name="SLR-6D", version="1.0", note=M("a_note"), dimensions=list(DIMS),
      grading="2=yes 0=unclear; 0-12; >=10 high, 7-9 moderate, 4-6 low, <4 very_low"), items=items,
    summary={k: sum(i["grade"] == k for i in items) for k in ("high", "moderate", "low", "very_low")})
  claims, evrows, confl, themes = [], [], [], []
  for k in (st["core_terms"][:4] or ["topic"]):
    mem = [r for r in inc if k in S.nz(r["title"] + " " + r["abstract"])]
    if not mem: continue
    tid = "T%d" % (len(themes) + 1)
    th = dict(theme_id=tid, label=k, records=[r["record_id"] for r in mem], claim_ids=[])
    themes.append(th); pool = []
    for r in mem:
      for s1, e1, x in sents(r["text"]):
        if (RX("D4").search(x) or any(RX(z).search(x) for z in ("POS", "NEG", "NUL"))) and k in S.nz(x):
          pool.append((GW.get(G.get(r["record_id"]), 1), r, s1, e1, x)); break
    if not pool: themes.pop(); continue
    pool.sort(key=lambda z: -z[0]); sup = pool[:2]; dirs = [DIR(z[4]) for z in sup]
    cid = "C%d" % (len(claims) + 1); nd = len({d for d in dirs if d != "unclear"}) or 1
    kind = ("insufficient_evidence" if nd > 1 else ("directly_supported" if len(sup) >= 2 and any(
      G.get(z[1]["record_id"]) in ("high", "moderate") for z in sup) else ("inferred" if len(sup) == 1 and
      G.get(sup[0][1]["record_id"]) in ("high", "moderate") else "insufficient_evidence")))
    ev = []
    for _s, r, s1, e1, x in sup:
      loc = "%s#chars=%d-%d" % (r["src"], s1, e1)
      ev.append(dict(record_id=r["record_id"], source=r["src"], extract=r["xf"], span=[s1, e1], locator=loc,
        quote=r["text"][s1:e1], direction=DIR(x), appraisal_grade=G.get(r["record_id"])))
      evrows.append(dict(zip(ECOLS, (cid, tid, kind, r["record_id"], G.get(r["record_id"]), DIR(x), r["src"],
        r["xf"], s1, e1, r["text"][s1:e1], loc, r["doi"], r["title"][:160]))))
    claims.append(dict(claim_id=cid, theme_id=tid, kind=kind, evidence=ev, boundary=M("y_bound"),
      statement=M("y_claim", th=k, n=len(sup), d=", ".join(M("y_" + d) for d in sorted(set(dirs)))),
      strength_rationale=M("y_rule", n=len(sup), g=", ".join(str(G.get(z[1]["record_id"])) for z in sup), d=nd)))
    th["claim_ids"].append(cid)
    if nd > 1:
      confl.append(dict(theme_id=tid, records=[z[1]["record_id"] for z in sup], directions=dirs,
        nature="direction_contrast", resolution=M("y_confres"),
        quotes=[dict(record_id=z[1]["record_id"], quote=z[4][:300]) for z in sup]))
  gaps = []
  for t in themes:
    if len(t["claim_ids"]) == 1:
      gaps.append(dict(gap_id="G%d" % (len(gaps) + 1), type="evidence_density", basis=t["records"],
        description=M("y_gap1", th=t["label"])))
  if claims and not any(c["kind"] == "directly_supported" for c in claims):
    gaps.append(dict(gap_id="G%d" % (len(gaps) + 1), type="method", basis=[c["claim_id"] for c in claims],
      description=M("y_gap2")))
  low = [i["record_id"] for i in items if i["grade"] in ("low", "very_low")]
  if low: gaps.append(dict(gap_id="G%d" % (len(gaps) + 1), type="reporting", basis=low, description=M("y_gap3", n=len(low))))
  if not st["structured"].get("comparison"):
    gaps.append(dict(gap_id="G%d" % (len(gaps) + 1), type="question", basis=["comparison=null"], description=M("y_gap5")))
  return sc, app, dict(themes=themes, claims=claims, conflicts=confl, gaps=gaps), evrows

ALIAS = {"casid": "case_id", "review": "review", "path": "review", "quality": "appraisal",
  "conclusions": "claims", "findings": "claims", "references": "sources", "eligibility": "criteria",
  "abstract": "summary", "files": "artifacts", "included_studies": "included",
  "included_records": "included", "evidence_matrix": "evidence", "evidence_table": "evidence"}
PH = {"", "string", "str", "text", "path", "file", "array", "list", "object", "number", "int", "float",
  "bool", "null", "none", "n/a", "tbd", "todo", "[]", "{}", "-"}

def cfill(node, prov, path=(), unm=None):
  """Keep every contract key verbatim; replace placeholder leaves from the provenance map, else null."""
  unm = [] if unm is None else unm
  if isinstance(node, dict): return {k: cfill(v, prov, path + (str(k),), unm) for k, v in node.items()}
  if isinstance(node, list): return [cfill(v, prov, path, unm) for v in node]
  k = re.sub(r"[^a-z0-9]", "", "".join(str(x) for x in path).lower())
  for c in (k, re.sub(r"(json|csv|md|ids|id|s)$", "", k), str(path[-1]).lower() if path else ""):
    c = ALIAS.get(c, c)
    if prov.get(c) not in (None, "", [], {}): return prov[c]
    c2 = ALIAS.get(re.sub(r"(json|csv|md|ids|id|s)$", "", c), c)
    if prov.get(c2) not in (None, "", [], {}): return prov[c2]
  if isinstance(node, str) and node.strip().lower() in PH: return None
  if node is not None: unm.append(".".join(str(x) for x in path))
  return node

def nleaf(o, nulls=False):
  if isinstance(o, dict): return sum(nleaf(v, nulls) for v in o.values())
  if isinstance(o, list): return sum(nleaf(v, nulls) for v in o)
  return (1 if o is None else 0) if nulls else 1

def wcsv(p, rows, cols):
  with Path(p).open("w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore"); w.writeheader()
    for r in rows: w.writerow({c: r.get(c, "") for c in cols})

def render(R, sc, app, syn):
  q, s, v = R["research_question"], R["search"], R["verification"]
  L = ["# " + q["raw"], "", "> " + M("q_scope", n=R["coverage"]["records_total"]), "",
       "## 1 Question decomposition", ""]
  L += ["- **%s**: %s" % kv for kv in q["structured"].items()]
  L += ["- core_terms: " + ", ".join(q["core_terms"]), "- derivation: %s, confidence=%s, needs_human=%s" %
        (q["derivation"]["method"], q["derivation"]["confidence"], q["derivation"]["needs_human"]), "",
        "## 2 Search protocol", ""]
  L += ["- `%s` status=%s date=%s n=%s" % (d["name"], d["status"], d.get("date"), d.get("n_records")) for d in s["databases"]]
  L += ["- block `%s` (%s): %s" % (b["block_id"], b["element"], " OR ".join(b["expanded"][:10])) for b in s["blocks"]]
  L += ["", "```", s["queries"]["pubmed_style"], "```", "",
        "- execution: mode=%s corpus=%s matched_by_block=%s matched_all=%s" % (s["execution"]["mode"],
        s["execution"]["corpus_size"], json.dumps(s["execution"]["matched_by_block"]), s["execution"]["matched_all_blocks"])]
  L += ["- limitation: " + x for x in s["limitations"]]
  L += ["", "## 3 Eligibility criteria (version %s, frozen %s)" % (R["criteria"]["version"], R["criteria"]["frozen_at"]), "",
        row("id", "type", "priority", "rule", "text"), row(*["---"] * 5)]
  L += [row(c["id"], c["type"], c["priority"], c["rule"], c["text"]) for c in R["criteria"]["clauses"]]
  L += ["", "- conflict policy: " + R["criteria"]["conflict_policy"], "", "## 4 Screening records", ""]
  L += ["- %s: %s" % (r["round"], ", ".join("%s=%s" % (k, x) for k, x in r.items() if k != "round")) for r in sc["rounds"]]
  L += ["", "- dual pass agreement=%s kappa=%s; %s" % (sc["dual_pass"]["agreement"], sc["dual_pass"]["cohen_kappa"], M("r_dual")),
        "- manual queue: " + (", ".join(sc["manual_queue"]) or "none"), "", "## 5 Quality appraisal (SLR-6D)", "",
        row("record", *DIMS, "score", "grade"), row(*["---"] * 9)]
  for i in app["items"]:
    g = dict(x.split(":") for x in i["dimensions"])
    L.append(row(*([i["record_id"]] + [g.get(x, "?") for x in DIMS] + [i["score"], i["grade"]])))
  L += ["", "- instrument: " + M("a_note"), "", "## 6 Synthesis by theme", ""]
  L += ["- theme `%s` (%s): %s" % (t["theme_id"], t["label"], ", ".join(t["records"])) for t in syn["themes"]]
  for c in syn["claims"]:
    L += ["", "### %s / %s / %s" % (c["claim_id"], c["theme_id"], c["kind"]), "", c["statement"], "",
          "- strength: " + c["strength_rationale"], "- boundary: " + c["boundary"]]
    for x in c["evidence"]:
      L += ["- `%s` (%s, grade=%s, %s) @ `%s`:" % (x["record_id"], x["source"], x["appraisal_grade"],
            x["direction"], x["locator"]), "  > " + x["quote"].replace("\n", " ")]
  L += ["", "## 7 Conflicting evidence", ""]
  if not syn["conflicts"]: L.append("none recorded under the frozen rules.")
  for k in syn["conflicts"]:
    L += ["- `%s` nature=%s records=%s directions=%s" % (k["theme_id"], k["nature"], ", ".join(k["records"]),
          "/".join(k["directions"])), "  - resolution: " + k["resolution"]]
  L += ["", "## 8 Research gaps", ""]
  L += ["- `%s` %s: %s" % (g["gap_id"], g["type"], g["description"]) for g in syn["gaps"]]
  L += ["", "## 9 Citation traceability", "", row("ref", "title", "authors", "year", "journal", "doi", "locator"),
        row(*["---"] * 7)]
  L += [row("`%s`" % x["source_id"], (x["title"] or "")[:120], (x["authors"] or "")[:80], x["year"], x["journal"],
        x["doi"], "`%s`" % x["locator"]) for x in R["sources"]]
  L += ["", "## 10 Uncertainty and status", "", "- status: %s; quotes verified %s/%s; artifacts present %s/%s" %
        (R["status"], v["quotes_verified"], v["quotes_checked"], len(v["artifacts_present"]), len(R["artifacts"]))]
  L += ["- cannot determine: " + u for u in R["uncertainty"]["cannot_determine"]]
  L += ["- bias `%s`: %s" % (b["id"], b["risk"]) for b in R["uncertainty"]["bias_risks"]]
  L += ["- pending human: %s (%s)" % (p.get("action"), p.get("why")) for p in R["pending_human"]]
  L += ["- degradation: " + json.dumps(d, ensure_ascii=False)[:280] for d in R["degradations"]]
  L += ["- error: " + json.dumps(d, ensure_ascii=False)[:280] for d in R["errors"]]
  L += ["", "_Skill %s %s; generated %s; conclusions are limited to the supplied materials._" %
        (R["skill"]["name"], R["skill"]["version"], NOW)]
  return "\n".join(L) + "\n"

def main():
  ap = argparse.ArgumentParser(prog="verify.py",
    description="SLR stage 2/2: screen, appraise, synthesise, assemble, render, verify quotes. Exit code always 0.",
    epilog="Run slr_review.py first: it writes work/state.json and a partial result.json.")
  ap.add_argument("--work", default="", help="work dir holding state.json")
  ap.add_argument("--output", default="", help="output dir for result.json and artifacts")
  n = ap.parse_args()
  base = Path("/app") if Path("/app").is_dir() else SD.parent
  wk = Path(n.work) if n.work else base / "work"
  out = Path(n.output) if n.output else base / "output"
  out.mkdir(parents=True, exist_ok=True)
  try: Z = json.loads((wk / "state.json").read_text(encoding="utf-8"))
  except Exception:
    print("state.json unreadable: run slr_review.py first", file=sys.stderr); return 0
  R, recs, st = Z["R"], Z["recs"], Z["st"]; S.LANG = Z.get("lang", "en")
  mats = Z.get("mats") or []; errs, degs, pend = R["errors"], R["degradations"], R["pending_human"]
  try:
    sc, app, syn, ev = pass2(recs, st)
    inc = sc["included"]; ids = [r["record_id"] for r in inc]
    bad = []
    for x in ev:
      try:
        t = (wk / x["extract_file"]).read_text(encoding="utf-8")
        if t[int(x["char_start"]):int(x["char_end"])] != x["quote"]:
          bad.append(dict(claim_id=x["claim_id"], record_id=x["record_id"], issue="span_mismatch"))
      except Exception as ex:
        bad.append(dict(claim_id=x["claim_id"], record_id=x["record_id"], issue=type(ex).__name__))
    R["screening"] = {k: x for k, x in sc.items() if k != "logs"}
    R["appraisal"], R["synthesis"] = app, syn
    R["sources"] = [dict(source_id=r["record_id"], title=r["title"], authors=r["authors"], year=r["year"],
      journal=r["journal"], doi=r["doi"], file=r["src"], sha256_12=S.h12(r["text"]), language=r["lang"],
      fulltext=("full" if r.get("has_full") else ("abstract_only" if r.get("r1") != "exclude" else "not_included")),
      locator="%s#chars=%d-%d" % (r["src"], r["aspan"][0], r["aspan"][1]),
      verified_fields=[f for f in ("title", "year", "doi", "journal") if r.get(f)]) for r in recs]
    ns = sum(c["kind"] == "directly_supported" for c in syn["claims"])
    R["coverage"] = dict(records_total=len(recs), records_included=len(inc), records_excluded=len(recs) - len(inc),
      criteria_clauses=len(R["criteria"]["clauses"]), themes=len(syn["themes"]), claims=len(syn["claims"]),
      claims_directly_supported=ns, claims_insufficient=sum(c["kind"] == "insufficient_evidence" for c in syn["claims"]),
      conflicts=len(syn["conflicts"]), gaps=len(syn["gaps"]), manual_queue=len(sc["manual_queue"]),
      materials=len(mats), quotes_total=sum(len(c["evidence"]) for c in syn["claims"]),
      abstract_only_records=sum(r.get("ft") == "abstract_only" for r in inc))
    R["status"] = "insufficient_evidence" if not recs else ("partial" if not syn["claims"] else "ok")
    R["summary"] = M("y_sum", n=len(recs), i=len(inc), c=len(syn["claims"]), d=ns, k=len(syn["conflicts"]), g=len(syn["gaps"]))
    R["uncertainty"] = dict(conflicts=syn["conflicts"], gaps=syn["gaps"],
      cannot_determine=[g["description"] for g in syn["gaps"]],
      evidence_scope=M("u_scope", n=len(recs), i=len(inc), m=len(mats)),
      bias_risks=[dict(id="B1", risk=M("u_b1"), affected=[i["record_id"] for i in app["items"] if i["grade"] in ("low", "very_low")]),
        dict(id="B2", risk=M("u_b2"), affected=sc["manual_queue"]),
        dict(id="B3", risk=M("u_b3"), affected=[r["record_id"] for r in inc if r.get("ft") == "abstract_only"][:20])])
    if recs and not syn["claims"]:
      pend.append(dict(action="review_no_claim", why="no quotable outcome sentence in included records"))
    wcsv(out / "screening_log.csv", sc["logs"], SCOLS); wcsv(out / "evidence_map.csv", ev, ECOLS)
    wcsv(out / "appraisal.csv", [dict(record_id=i["record_id"], **dict(x.split(":") for x in i["dimensions"]),
      score=i["score"], grade=i["grade"], abstract_only=i["abstract_only"]) for i in app["items"]], ACOLS)
    R["artifacts"] = dict(result_json="result.json", review_md="review.md", evidence_map_csv="evidence_map.csv",
      screening_log_csv="screening_log.csv", appraisal_csv="appraisal.csv")
    def verify_files():
      arts = [k for k, x in R["artifacts"].items() if (out / x).exists()]
      R["verification"] = dict(quotes_checked=len(ev), quotes_verified=len(ev) - len(bad), failures=bad[:10],
        artifacts_present=arts, method="re-extract the substring at char span from work/extracted and compare with the stored quote",
        verified_at=NOW, result=("pass" if not bad and len(arts) == len(R["artifacts"]) else "warn"))
    verify_files()
    (out / "review.md").write_text(render(R, sc, app, syn), encoding="utf-8")
    verify_files()
    (out / "review.md").write_text(render(R, sc, app, syn), encoding="utf-8")
    prov = dict(R, review="review.md", evidence_map="evidence_map.csv", screening_log="screening_log.csv",
      appraisal_csv="appraisal.csv", evidence=ev, clauses=R["criteria"]["clauses"], included=ids,
      claims=syn["claims"], conflicts=syn["conflicts"], gaps=syn["gaps"], themes=syn["themes"])
    unm = []
    if isinstance(R.get("output_contract"), dict) and R["output_contract"]:
      R["output_contract"] = cfill(R["output_contract"], prov, (), unm)
    cc = R.get("output_contract") or {}
    R["contract_check"] = dict(fields_requested=nleaf(cc), fields_null=nleaf(cc, True), unmapped=unm[:20],
      rule="every input contract key is kept verbatim; a leaf is filled from an artifact or set to explicit null")
    R["runtime"] = dict((R.get("runtime") or {}), finished_utc=NOW, python=sys.version.split()[0], network=False,
      model_requests=None, mode="corpus_only", stage2_seconds=round(time.time() - T0, 1))
    R["stage"] = "finalize"
    S.jw(out / "result.json", R)
    print("quotes %d/%d | artifacts %d/%d | contract nulls %d unmapped %d | status=%s" % (len(ev) - len(bad), len(ev),
      len(R["verification"]["artifacts_present"]), len(R["artifacts"]), R["contract_check"]["fields_null"], len(unm), R["status"]))
  except Exception as ex:
    errs.append(dict(stage="stage2", error=type(ex).__name__, detail=str(ex)[:400]))
    R["pending_human"], R["errors"], R["degradations"] = pend, errs, degs
    if R.get("status") not in ("ok", "insufficient_evidence"): R["status"] = "partial"
    try: S.jw(out / "result.json", R)
    except Exception: pass
    print("stage2 error %s: %s" % (type(ex).__name__, str(ex)[:200]), file=sys.stderr)
  return 0

if __name__ == "__main__":
  sys.exit(main())
