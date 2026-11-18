#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Literature knowledge graph builder: papers -> evidenced nodes and edges.
  python3 build_graph.py --input /input --output /app/output
Parses case.json and the paper material (JATS XML, JSON paragraph index, text),
extracts entities and cue-scoped relations bound to verbatim quotes and organizer
paragraph ids, aligns aliases, writes graph_raw.json and a partial result.json,
then calls verify.py.
"""
import argparse, hashlib, json, os, re, subprocess, sys, time
from pathlib import Path
T0 = time.time()
HD = Path(__file__).resolve().parent


def rl():
    try: return json.loads((HD.parent / "references" / "graph_rules.json").read_text(encoding="utf-8"))
    except Exception: return {}


RM = rl()
W2T = {w: t for t, ws in (RM.get("lexicon") or {"metric": ["accuracy", "error"]}).items() for w in ws}
CR = [(re.compile(a, re.I), b) for a, b in (RM.get("cues") or [[r"\b(?:using|used)\b", "uses"], [r"\bcontradict\w*", "contradicts"]])]
STOP = set(RM.get("stop") or "the a an of and in to for with we is are was were this that study paper data result results method methods approach table figure".split())
BLOCK = set(RM.get("block") or "abstract introduction methods results discussion conclusion references table figure".split())
PK = ("paragraph_id", "paragraphid", "pid", "para_id", "p_id", "id", "jats_id", "para", "key", "block_id")
TK = ("text", "body", "content", "paragraph", "sentence", "chunk", "raw_text", "plain")
PRIO = lambda n: 0 if "primary" in n else 1 if "secondary" in n else 3 if "manifest" in n else 5 if "material" in n else 4
MAXN, MAXE = 45, 120


def el(): return round(time.time() - T0, 2)
def h8(s): return hashlib.sha1(s.encode()).hexdigest()[:8]
def rd(p):
    for e in ("utf-8", "utf-8-sig", "latin-1"):
        try: return p.read_text(encoding=e)
        except Exception: pass
    return ""


def wr(p, s): p.parent.mkdir(parents=True, exist_ok=True); p.write_text(s, encoding="utf-8")
def dp(p, o): wr(p, json.dumps(o, ensure_ascii=False, indent=2))
def ev(q, s, l): return {"quote": q, "source_id": s, "location": l, "evidence_class": "directly_read"}
def lc(p, s, sp): return {"kind": "jats_paragraph_id", "paragraph_id": p, "section": s, "char_span": sp}
def st(s): return re.sub(r"\s+", " ", re.sub(r"&[a-z]+;", " ", re.sub(r"<[^>]+>", " ", s))).strip()


def nm(s):
    s = (s or "").lower()
    for a, b in (("\u2013", "-"), ("\u2014", "-"), ("\u2011", "-"), ("\u00a0", " "), ("\u2019", "'"), ("\u201c", ""), ("\u201d", "")): s = s.replace(a, b)
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9%./+\- ]+", " ", s)).strip(" .-/")


def ss(t):
    o, pv = [], 0
    for m in re.finditer(r"[.!?](?=\s+[A-Z\u4e00-\u9fff(\[])", t): o.append((pv, m.end())); pv = m.end()
    if pv < len(t): o.append((pv, len(t)))
    r = []
    for s, e in o:
        while s < e and t[s].isspace(): s += 1
        while e > s and t[e - 1].isspace(): e -= 1
        if e - s > 8: r.append((s, e))
    return r


def so(t, p): return next(((s, e) for s, e in ss(t) if s <= p < e), (0, min(len(t), p + 200)))


def ty(s):
    for w in nm(s).split():
        if w in W2T: return W2T[w]
    return "concept"


def hv(o, c, f, acc, d=0):
    if d > 10: return
    if isinstance(o, dict):
        c = dict(c)
        for k, v in o.items():
            lk = str(k).lower()
            if lk in ("doi", "source_id", "paper_id", "article_id") and isinstance(v, str) and v.strip(): c["sid"] = v.strip()
            elif lk in ("title", "paper_title", "article_title") and isinstance(v, str) and v.strip(): c["ti"] = v.strip()
        tx = next((v for k, v in o.items() if str(k).lower() in TK and isinstance(v, str) and len(v.strip()) >= 30), None)
        if tx is not None:
            acc.append({"pid": next((str(v).strip() for k, v in o.items() if str(k).lower() in PK and isinstance(v, (str, int)) and str(v).strip()), None),
                        "t": tx, "sec": c.get("sec", ""), "sid": c.get("sid"), "ti": c.get("ti"), "f": f}); return
        for v in list(o.values()):
            if isinstance(v, (dict, list)): hv(v, c, f, acc, d + 1)
    elif isinstance(o, list):
        for v in o:
            if isinstance(v, str) and len(v.strip()) >= 30: acc.append({"pid": None, "t": v, "sec": c.get("sec", ""), "sid": c.get("sid"), "ti": c.get("ti"), "f": f})
            elif isinstance(v, (dict, list)): hv(v, c, f, acc, d + 1)


def pa(p, rel, err, deg):
    n, acc, meta, cur = p.name.lower(), [], {}, ""
    try:
        if n.endswith(".json"): hv(json.loads(rd(p)), {}, rel, acc); return acc, {}
        if n.endswith(".pdf"):
            deg.append({"what": "pdf not text-extracted (stdlib only): " + rel, "effect": "excluded; see pending_human", "code": "PDF_UNPARSED"})
            return [], {"pdf_gap": rel}
        if n.endswith((".xml", ".nxml", ".jats", ".html")):
            t = re.sub(r"<!(?:DOCTYPE|ENTITY)[^>]*>", "", re.sub(r'\sxmlns(:\w+)?="[^"]*"', "", rd(p)))
            for pat, k in ((r'<article-id[^>]*doi[^>]*>(.*?)</article-id>', "doi"), (r"<article-title[^>]*>(.*?)</article-title>", "ti")):
                m = re.search(pat, t, re.S)
                if m: meta[k] = st(m.group(1))
            for m in re.finditer(r"<title[^>]*>(.*?)</title>|<p\b([^>]*)>(.*?)</p>", t, re.S):
                if m.group(1) is not None: cur = st(m.group(1)); continue
                b = st(m.group(3))
                if len(b) >= 30:
                    i = re.search(r'\bid\s*=\s*"([^"]+)"', m.group(2) or "")
                    acc.append({"pid": i.group(1) if i else None, "t": b, "sec": cur, "sid": meta.get("doi"), "ti": meta.get("ti"), "f": rel})
            return acc, meta
        return [{"pid": "blk%04d" % i, "t": re.sub(r"\s+", " ", b.strip()), "sec": "", "sid": None, "ti": None, "f": rel} for i, b in enumerate(re.split(r"\n\s*\n", rd(p))) if len(b.strip()) >= 30], {}
    except Exception as e:
        err.append({"stage": "parse", "file": rel, "error": repr(e)[:150]}); return [], {}


def manifest_meta(p):
    """Read corpus-manifest.json for per-source authors/title/license (not paper body)."""
    try:
        data = json.loads(rd(p))
    except Exception:
        return {}
    out = {}

    def walk(o):
        if isinstance(o, dict):
            sid = next((str(v).strip() for k, v in o.items() if str(k).lower() in ("doi", "source_id", "article_id", "paper_id") and isinstance(v, str) and v.strip()), None)
            if sid:
                au = o.get("authors") or o.get("author") or o.get("creators") or []
                if isinstance(au, str):
                    au = [a.strip() for a in re.split(r"[;,]", au) if a.strip()]
                elif isinstance(au, list):
                    au = [str(a).strip() for a in au if isinstance(a, str) and str(a).strip()]
                else:
                    au = []
                ti = next((str(v).strip() for k, v in o.items() if str(k).lower() in ("title", "paper_title", "article_title") and isinstance(v, str) and v.strip()), None)
                lic = o.get("license") or o.get("licence") or o.get("rights")
                if isinstance(lic, dict):
                    lic = lic.get("name") or lic.get("id") or lic.get("url") or str(lic)
                lic = str(lic).strip() if lic is not None else None
                if au or ti or lic:
                    rec = out.setdefault(sid, {})
                    if au: rec.setdefault("authors", au)
                    if ti: rec.setdefault("title", ti)
                    if lic: rec.setdefault("license", lic)
            for v in o.values():
                if isinstance(v, (dict, list)): walk(v)
        elif isinstance(o, list):
            for v in o:
                if isinstance(v, (dict, list)): walk(v)
    walk(data)
    return out


def main():
    ap = argparse.ArgumentParser(prog="build_graph.py", formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Build an evidence-bound literature knowledge graph; export graph_raw.json (nodes, edges, sources, paragraph index).",
        epilog="Example: python3 build_graph.py --input /input --output /app/output\nOutputs: result.json + graph_raw.json; verify.py adds claims, queries, CSV, quote check.")
    ap.add_argument("--input", default=os.environ.get("INPUT_DIR", "/input"), help="input dir")
    ap.add_argument("--output", default=os.environ.get("OUTPUT_DIR", "/app/output"), help="output dir")
    ap.add_argument("--quiet", action="store_true", help="silent")
    a = ap.parse_args()
    say = (lambda *x: None) if a.quiet else (lambda *x: print("[%6.1fs]" % el(), *x, flush=True))
    inp, out = Path(a.input), Path(a.output)
    try: out.mkdir(parents=True, exist_ok=True)
    except Exception: out = Path.cwd() / "output"; out.mkdir(parents=True, exist_ok=True)
    err, deg, chg, pend, unc = [], [], [], [], []
    case = {}
    if (inp / "case.json").exists():
        try:
            case = json.loads(rd(inp / "case.json")); case = case if isinstance(case, dict) else {"payload": case}
        except Exception as e:
            err.append({"stage": "parse_case_json", "file": "case.json", "error": repr(e)[:200]})
            deg.append({"what": "case.json unparsable", "effect": "recursive discovery only", "code": "CASE_JSON_BAD"})
    contract = case.get("output_contract") if isinstance(case.get("output_contract"), dict) else {}
    R = {"case_id": case.get("case_id") or case.get("caseId") or case.get("id"), "status": "partial", "output_contract": contract, "task": {}, "inputs": [],
         "sources": [], "schema": {}, "graph_summary": {}, "nodes": [], "edges": [], "claims": [], "queries": [], "merge": {}, "uncertainty": unc,
         "pending_human": pend, "errors": err, "degradations": deg, "changes": chg, "incremental": {}, "runtime": {}, "artifacts": {}, "contract_coverage": {}}
    for k in contract: R.setdefault(k, None)
    dp(out / "result.json", R); say("partial ->", out / "result.json")
    files = sorted(p for p in inp.rglob("*") if p.is_file()) if inp.exists() else []
    if not inp.exists(): unc.append({"id": "U-INPUT", "kind": "input_error", "statement": "input dir missing: %s" % inp, "evidence_class": "undetermined", "impact": "nothing parsed"})
    elif not case: unc.append({"id": "U-CASE", "kind": "input_error", "statement": "case.json not found or unreadable", "evidence_class": "undetermined", "impact": "contract fields unavailable"})
    ins = case.get("task_instruction") or case.get("instruction") or ""
    R["task"] = {"instruction": (ins if isinstance(ins, str) else json.dumps(ins, ensure_ascii=False))[:1500], "input_dir": str(inp)}
    if not contract: unc.append({"id": "U-CONTRACT", "kind": "contract", "statement": "no output_contract found in case.json", "evidence_class": "undetermined", "impact": "standard section set returned instead"})
    say("case:", R["case_id"], len(files), "files,", len(contract), "contract keys")
    raw, manifest = [], {}
    for p in files:
        if p.name.lower() == "case.json" and p.parent == inp:
            continue
        if "manifest" in p.name.lower() and p.suffix.lower() == ".json":
            manifest.update(manifest_meta(p)); continue
        rel = str(p.relative_to(inp)) if inp in p.parents else p.name
        ps, meta = pa(p, rel, err, deg)
        for x in ps:
            x.update({"prio": PRIO(rel.lower()), "f": rel, "sid": x.get("sid") or meta.get("doi"), "ti": x.get("ti") or meta.get("ti"), "au": meta.get("au")})
            raw.append(x)
    raw = [x for x in raw if not (len(x["t"]) > 250 and len(re.findall(r"\b(?:19|20)\d\d\b", x["t"])) >= 3 and ("doi" in x["t"].lower() or "pp." in x["t"].lower()))]
    raw.sort(key=lambda x: (x["prio"], x["f"]))
    seen, keep, dup = {}, [], 0
    for x in raw:
        k = h8(nm(x["t"]))
        if k in seen: dup += 1; continue
        seen[k] = x["f"]; keep.append(x)
    if dup: chg.append({"what": "de-duplicated identical paragraph text across files", "count": dup, "rule": "keep highest-priority file (primary/secondary original over aggregate material index)", "why": "the aggregate index would otherwise double-count the same paragraph"})
    docs, pidmap = {}, {}
    for x in keep:
        sid = x.get("sid") or next((m.group(0).rstrip(".") for m in re.finditer(r"10\.\d{4,9}/[^\s\"'<>,]+", x["t"])), None) or Path(x["f"]).stem
        d = docs.setdefault(sid, {"sid": sid, "ti": None, "ps": [], "files": set()})
        d["files"].add(x["f"]); d["ti"] = d["ti"] or x.get("ti"); d["au"] = d.get("au") or x.get("au")
        if not x.get("pid"):
            x["pid"] = "%s-p%04d" % (Path(x["f"]).stem[:14], len(d["ps"]) + 1)
            if not any(g["code"] == "PID_SYNTHETIC" for g in deg): deg.append({"what": "paragraphs without organizer ids", "effect": "synthetic ids (marked, not organizer ids)", "code": "PID_SYNTHETIC"})
        d["ps"].append(x); pidmap["%s||%s" % (sid, x["pid"])] = {"source_id": sid, "paragraph_id": x["pid"], "text": x["t"]}
    for sid, d in docs.items(): d["files"] = sorted(d["files"])
    for sid, d in docs.items():
        m = manifest.get(sid)
        if not m and d.get("ti"):
            for cand in manifest.values():
                if cand.get("title") and d.get("ti") and nm(cand["title"]) == nm(d["ti"]):
                    m = cand; break
        if m:
            d["ti"] = d["ti"] or m.get("title")
            d["au"] = m.get("authors") or d.get("au")
            d["lic"] = m.get("license")
            d["man"] = True
    say("papers:", {k: len(v["ps"]) for k, v in docs.items()})
    if not docs:
        unc.append({"id": "U-NOMAT", "kind": "input_error", "statement": "no parsable paper paragraphs under %s" % inp, "evidence_class": "undetermined", "impact": "graph empty; contract fields null/[]"})
        pend.append({"id": "H-NOMAT", "action": "supply paper text (JATS/JSON/txt)", "why": "extraction needs readable paragraph text"})
    N, E = {}, []
    for sid, d in docs.items():
        P, title = "n-" + h8(sid), d.get("ti") or sid
        N[P] = {"id": P, "label": title, "type": "paper", "type_basis": "source_metadata", "aliases": [sid], "sources": [sid],
                "evidence": [ev(title[:200], sid, {"kind": "source_metadata", "field": "title"})], "mention_count": 1, "confidence": "high"}
        for x in d["ps"]:
            t = x["t"][:20000]
            cand = [(m.start(), m.end(), m.group(0)) for w in W2T for m in re.finditer(r"\b" + re.escape(w) + r"\b", t, re.I)]
            cand += [(m.start(), m.end(), m.group(1)) for m in re.finditer(r"\b([A-Z][A-Za-z0-9]*(?:[ \-\u2011](?!(?:and|the|for|with|from|that|this|are|was|were|but|not)\b)[a-z][a-z\-]{2,}){0,2})\b", t)
                     if nm(m.group(1).split()[0]) not in STOP]
            cand += [(m.start(), m.end(), m.group(1)) for m in re.finditer(r"\b([A-Z]{2,}[0-9]*|[A-Z][a-z]?[0-9][A-Za-z0-9\-]*)\b", t)]
            cand.sort(key=lambda z: (z[0], -(z[1] - z[0])))
            last = -1
            for s, e, sf in cand:
                if s < last: continue
                sf = re.sub(r"\s+", " ", sf).strip(" .,-"); k = nm(sf)
                if len(sf) < 3 or not k or k in STOP or k in BLOCK: continue
                last = e
                nid = "n-" + h8(k)
                qs, qe = so(t, s)
                l = lc(x["pid"], x.get("sec", ""), [s, e])
                if nid in N:
                    N[nid]["mention_count"] += 1
                    if sid not in N[nid]["sources"]: N[nid]["sources"] = sorted(N[nid]["sources"] + [sid])
                    if sf not in N[nid]["aliases"] and sf != N[nid]["label"]: N[nid]["aliases"].append(sf)
                    if len(N[nid]["evidence"]) < 3: N[nid]["evidence"].append(ev(t[qs:qe][:400], sid, l))
                else:
                    if len(N) >= MAXN * max(1, len(docs)): continue
                    N[nid] = {"id": nid, "label": sf, "type": ty(sf), "type_basis": "cue_word" if ty(sf) != "concept" else "default", "aliases": [],
                              "sources": [sid], "evidence": [ev(t[qs:qe][:400], sid, l)], "mention_count": 1, "confidence": "medium"}
    for x in N.values():
        x["confidence"] = "medium" if len(x["sources"]) > 1 else ("high" if x["mention_count"] > 1 else "medium")
    for sid, d in docs.items():
        P = "n-" + h8(sid)
        pool = {n["label"].lower(): n["id"] for n in N.values() if sid in n["sources"] and n["id"] != P}
        pat = re.compile("|".join(re.escape(s) for s in sorted(pool, key=len, reverse=True)) or r"(?!)", re.I) if pool else None
        if not pat: continue
        ne = 0
        for x in d["ps"]:
            if ne >= MAXE: break
            t = x["t"][:20000]
            for s0, e0 in ss(t):
                sent = t[s0:e0]
                hits = sorted({(m.start(), m.end(), pool[m.group(0).lower()]) for m in pat.finditer(sent) if m.group(0).lower() in pool})
                if len(hits) < 2: continue
                done, loc = set(), lc(x["pid"], x.get("sec", ""), [s0, e0])
                for rx, pred in CR:
                    for m in rx.finditer(sent):
                        L = [h for h in hits if h[1] <= m.start()]; Rg = [h for h in hits if h[0] >= m.end()]
                        if not L or not Rg: continue
                        s1, s2 = L[-1][2], Rg[0][2]
                        if s1 == s2 or (s1, pred, s2) in done: continue
                        done.add((s1, pred, s2))
                        E.append({"id": "e-" + h8("|".join((s1, pred, s2)) + sid + x["pid"]), "subject": s1, "predicate": pred, "object": s2,
                                  "cue": sent[m.start():m.end()], "evidence": [ev(sent[:400], sid, loc)], "direction": "subject->object",
                                  "condition": {"paragraph_id": x["pid"], "section": x.get("sec", ""), "source_id": sid, "note": "cue-scoped within this paragraph only"},
                                  "evidence_strength": "direct_cue" if pred in ("uses", "measures", "improves_over") else "weak_cue"})
                        ne += 1
    bk = {}
    for nid, x in N.items(): bk.setdefault(nm(x["label"]), []).append(nid)
    for k, ids in bk.items():
        if len(ids) > 1:
            ids.sort(key=lambda i: -N[i]["mention_count"]); kp = ids[0]
            for o in ids[1:]:
                N[kp]["sources"] = sorted(set(N[kp]["sources"] + N[o]["sources"])); N[kp]["mention_count"] += N[o]["mention_count"]
                N[kp]["aliases"] = sorted(set(N[kp]["aliases"] + N[o]["aliases"] + [N[o]["label"]])); N.pop(o, None)
                chg.append({"what": "merged duplicate node on identical normalised surface", "into": kp, "from": o, "basis": k, "risk": "string identity does not prove identical sample/condition"})
    acr, conf = {}, []
    for nid, x in N.items():
        if re.match(r"^[A-Z][A-Z0-9\-]{1,9}$", x["label"]): acr.setdefault(x["label"], []).append(nid)
    for s, ids in acr.items():
        if len(ids) > 1:
            conf.append({"type": "same_acronym_multiple_nodes", "acronym": s, "nodes": ids, "handling": "kept separate; merge not forced",
                         "evidence": [{"source_id": N[i]["sources"][0], "quote": N[i]["evidence"][0]["quote"][:140], "location": N[i]["evidence"][0]["location"]} for i in ids[:3]]})
    for e in E:
        e["subject_label"], e["object_label"] = N.get(e["subject"], {}).get("label", e["subject"]), N.get(e["object"], {}).get("label", e["object"])
        e["cross_source"] = len(N.get(e["subject"], {}).get("sources", [])) > 1 or len(N.get(e["object"], {}).get("sources", [])) > 1
    cross = [n["id"] for n in N.values() if len(n["sources"]) > 1]
    R.update({"nodes": sorted(N.values(), key=lambda n: (n["type"], n["label"])), "edges": E,
              "merge": {"auto_merged": chg, "cross_source_nodes": cross, "non_merge_conflicts": conf},
              "sources": [{"source_id": s, "title": d.get("ti"), "doi": s if s.startswith("10.") else None, "authors": d.get("au"), "license": d.get("lic"),
                           "files": d["files"], "paragraphs": len(d["ps"]), "from_manifest": bool(d.get("man"))} for s, d in docs.items()]})
    unc += [{"id": "U-TYPE", "kind": "extraction", "statement": "实体类型为线索词启发式，concept 表示未定型", "evidence_class": "inferred", "impact": "类型查询可能漏掉无线索词项"},
            {"id": "U-RECALL", "kind": "extraction", "statement": "关系抽取仅覆盖含线索表述的句子", "evidence_class": "inferred", "impact": "高精度低召回；缺席不等于不存在"},
            {"id": "U-LOC", "kind": "locator", "statement": "定位为组织方 JATS 段落 ID 加引文字符区间，无 PDF 页码", "evidence_class": "directly_read", "impact": "不得当作印刷页码引用"}]
    if len(docs) < 2: unc.append({"id": "U-SRCNUM", "kind": "corpus", "statement": "only %d paper(s) parsed" % len(docs), "evidence_class": "undetermined", "impact": "cross-paper alignment unsupported"})
    R["status"] = "ok" if (docs and E) else ("partial" if (docs or N) else "input_error")
    dp(out / "graph_raw.json", {"case_id": R["case_id"], "nodes": R["nodes"], "edges": E, "sources": R["sources"], "paragraphs": pidmap, "merge": R["merge"]})
    R["artifacts"] = {"result_json": str(out / "result.json"), "graph_raw": str(out / "graph_raw.json")}
    R["runtime"] = {"elapsed_seconds": el(), "python": sys.version.split()[0], "stdlib_only": True, "network": False, "script": str(Path(__file__).resolve())}
    R["contract_coverage"] = {"provided_keys": [str(k) for k in contract], "filled": {}, "stage": "pending verify.py", "originals_preserved_in": "output_contract"}
    dp(out / "result.json", R); say("graph:", R["graph_summary"])
    vp = HD / "verify.py"
    if vp.exists():
        try:
            r = subprocess.run([sys.executable, "-B", str(vp), "--input", str(inp), "--output", str(out)], capture_output=True, timeout=300)
            say("verify rc=", r.returncode, r.stdout.decode("utf-8", "replace")[-160:].strip())
        except Exception as e:
            err.append({"stage": "run_verify", "error": repr(e)[:180]})
            deg.append({"what": "verify.py did not run", "effect": "claims, queries, CSV and contract back-fill missing; graph_raw.json intact", "code": "VERIFY_SKIPPED"})
            dp(out / "result.json", R)
    return R


if __name__ == "__main__":
    try: main()
    except SystemExit: raise
    except BaseException as exc:
        try:
            import traceback
            o = Path(os.environ.get("OUTPUT_DIR", "/app/output"))
            p = o / "result.json"
            cur = json.loads(rd(p)) if p.exists() else {}
            cur.setdefault("case_id", None); cur["status"] = "partial"
            cur.setdefault("errors", []).append({"stage": "fatal", "error": repr(exc)[:300], "traceback": traceback.format_exc()[-600:]})
            dp(p, cur)
        except Exception: pass
    os._exit(0)
