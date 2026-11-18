#!/usr/bin/env python3
"""lens engine: extraction, normalisation, trend/topic/gap statistics (stdlib only)."""
import argparse, csv, hashlib, html, json, re, shutil, subprocess, sys, time, unicodedata, zipfile, zlib
from collections import Counter, defaultdict
from pathlib import Path

NM, VR = "research-trend-lens", "1.0.0"
REF = Path(__file__).resolve().parent.parent / "references"
T0 = time.time()
ER, DG, LG, CH = [], [], [], []

def el(): return round(time.time() - T0, 2)
def S2(x): return hashlib.sha256(str(x).encode("utf-8", "replace")).hexdigest()[:16]
def N(s): return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", "" if s is None else str(s))).strip()
def E(c, m, **k): ER.append(dict(code=c, msg=N(m)[:260], t=el(), **k))
def D(w, y, **k): DG.append(dict(what=w, why=N(y)[:220], t=el(), **k))
def G(s, **k): LG.append(dict(i=len(LG) + 1, step=s, t=el(), **k))

def wj(p, o):
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(o, ensure_ascii=False, indent=1), encoding="utf-8"); return p

def wc(p, rows, cols):
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore"); w.writeheader()
        for r in rows: w.writerow({c: r.get(c, "") for c in cols})
    return p

def tb(h, rows):
    o = ["| " + " | ".join(h) + " |", "|" + "-|" * len(h)]
    for r in rows: o.append("| " + " | ".join(N(x).replace("|", "/")[:100] for x in r) + " |")
    return "\n".join(o)

def fk(o, k, d=0):
    if d > 7: return None
    if isinstance(o, dict):
        if k in o: return o[k]
        for v in o.values():
            r = fk(v, k, d + 1)
            if r is not None: return r
    elif isinstance(o, list):
        for v in o[:25]:
            r = fk(v, k, d + 1)
            if r is not None: return r
    return None

def jl(p, tag):
    try: t = Path(p).read_text(encoding="utf-8-sig", errors="replace")
    except Exception as e: E("READ_FAIL", "%s: %s" % (tag, e)); return None
    last = None
    for f in (lambda x: x, lambda x: re.sub(r",(\s*[}\]])", r"\1", x)):
        try: return json.loads(f(t))
        except Exception as e: last = e
    i = min([k for k in (t.find("{"), t.find("[")) if k >= 0] or [-1])
    if i < 0: E("JSON_FAIL", "%s: %s" % (tag, last)); return None
    try:
        o, _ = json.JSONDecoder().raw_decode(t[i:]); D("json_repaired", N(tag)[:60]); return o
    except Exception: E("JSON_FAIL", "%s: %s" % (tag, last)); return None

def cmap(c):
    if isinstance(c, list):
        out = {}
        for it in c:
            if isinstance(it, str):
                out[str(it)] = None
            elif isinstance(it, dict):
                key = it.get("name") or it.get("field") or it.get("key")
                if key: out[str(key)] = it.get("value", it.get("default"))
                else: out.update(cmap(it))
            else:
                out.update(cmap(it))
        return out
    if not isinstance(c, dict): return {}
    out = {}
    for k, v in c.items():
        out.update(cmap(v) if is_grp(k, v) else {k: v})
    return out

def is_grp(k, v):
    return k in ("fields", "required", "required_fields", "schema", "outputs", "items") and isinstance(v, (dict, list))

FX = {".pdf": "pdf", ".ris": "ris", ".csv": "csv", ".tsv": "csv", ".json": "json", ".jsonl": "json", ".md": "text", ".txt": "text"}


def fmt(p):
    try: h = p.open("rb").read(4)
    except Exception: h = b""
    return "pdf" if h == b"%PDF" else ("skip" if h[:2] == b"PK" else FX.get(p.suffix.lower(), "skip"))

def qr(s):
    return 0.0 if not s else len(re.findall(r"[A-Za-z0-9\s.,;:()\[\]%+/='\"<>-]|[\u4e00-\u9fff]", s)) / len(s)

def pages(p):
    if shutil.which("pdftotext"):
        try:
            r = subprocess.run(["pdftotext", "-layout", "-enc", "UTF-8", str(p), "-"], capture_output=True, timeout=150)
            t = r.stdout.decode("utf-8", "replace")
            if r.returncode == 0 and len(N(t)) > 40:
                pg = t.split("\f"); return (pg[:-1] if pg and not N(pg[-1]) else pg), "pdftotext"
        except Exception as e: E("PDF_TOOL_FAIL", "%s: %s" % (p.name, e))
    try: raw = p.read_bytes()
    except Exception as e: E("PDF_READ_FAIL", str(e)); return [], "none"
    out = []
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", raw, re.S):
        d = m.group(1)
        try: d = zlib.decompress(d)
        except Exception: pass
        if b"BT" not in d: continue
        t = " ".join(re.sub(rb"\\([()\\])", rb"\1", g[1:-1]).decode("utf-8", "replace") for g in re.findall(rb"\((?:\\.|[^\\()])*\)", d))
        if t.strip(): out.append(t)
    return out, "builtin"

def ris(t):
    rs, cur = [], None
    for ln in t.splitlines():
        m = re.match(r"^([A-Z][A-Z0-9])  - ?(.*)$", ln)
        if not m: continue
        if cur is None: cur = {}
        if m.group(1) == "ER": rs.append(cur); cur = None
        else: cur.setdefault(m.group(1), []).append(m.group(2).strip())
    if cur: rs.append(cur)
    return rs

def walk(o, out, d=0):
    if d > 6 or len(out) > 3000: return out
    if isinstance(o, dict):
        ks = set(str(k).lower() for k in o)
        if ks & {"title", "ti", "t1", "name"} and ks & {"year", "py", "y1", "doi", "do", "author", "authors", "abstract"}: out.append(o)
        for v in o.values(): walk(v, out, d + 1)
    elif isinstance(o, list):
        for v in o[:600]: walk(v, out, d + 1)
    return out

def gv(d, *ks):
    for k in ks:
        v = d.get(k)
        v = v[0] if isinstance(v, list) and v and not isinstance(v[0], (dict, list)) else v
        if isinstance(v, str) and v.strip(): return N(v)
    return ""

def read(p, f):
    if f == "pdf":
        pg, how = pages(p); t = "\n".join(pg); return [], t, pg, round(qr(t), 3), how
    if f == "text":
        t = p.read_text(encoding="utf-8", errors="replace"); return [], t, t.split("\n"), round(qr(t), 3), "text"
    if f == "ris":
        return [dict((k.lower(), v) for k, v in r.items()) for r in ris(p.read_text(encoding="utf-8", errors="replace"))], "", [], 1.0, "ris"
    if f == "csv":
        raw = list(csv.reader(p.read_text(encoding="utf-8", errors="replace").splitlines()))
        if not raw: return [], "", [], 1.0, "csv"
        h = [N(c).lower() for c in raw[0]]
        return [dict((h[i] if i < len(h) else "c%d" % i, N(v)) for i, v in enumerate(r)) for r in raw[1:] if any(N(x) for x in r)], "", [], 1.0, "csv"
    o = jl(p, p.name)
    if o is None: return [], "", [], 0.0, "json"
    return [dict((str(k).lower(), v) for k, v in d.items()) for d in walk(o, [])], "", [], 1.0, "json"

def yr(v):
    if isinstance(v, int) and 1900 <= v <= 2035: return v
    m = re.search(r"(?<!\d)(19[5-9]\d|20[0-3]\d)(?!\d)", N(v))
    return int(m.group(1)) if m else None

def yrt(t):
    s = N(t)[:4000]
    for p in (r"\((19[5-9]\d|20[0-3]\d)\)", r"(?:\u00a9|\(c\)|copyright)\s*(19[5-9]\d|20[0-3]\d)", r"(?:19[5-9]\d|20[0-3]\d)\s*[.,]", r"(?:19[5-9]\d|20[0-3]\d)"):
        m = re.search(p, s, re.I)
        if m: return int(m.group(1) if m.groups() else m.group(0)[:4])
    return None

def ntt(t): return re.sub(r"\s+", " ", re.sub(r"[^0-9a-z\u4e00-\u9fff ]+", " ", N(t).lower())).strip()
def toks(t): return [w for w in re.split(r"[^0-9a-z\u4e00-\u9fff]+", ntt(t)) if len(w) > 1 or w[:1].isdigit()]

def jac(a, b):
    A, B = set(a), set(b)
    return 0.0 if not A or not B else len(A & B) / len(A | B)

def lexf():
    L = dict(topics=[], gap={}, method=[], exclude=[])
    p = REF / "lexicon.md"
    if not p.is_file():
        D("lexicon_missing", "references/lexicon.md absent: no topic labels; trend/gaps still produced"); return L
    sec = None
    for ln in [x.strip() for x in p.read_text(encoding="utf-8").splitlines()]:
        m = re.match(r"^\[(\w+)\]$", ln)
        if m: sec = m.group(1).lower(); continue
        if not ln or ln.startswith("#"): continue
        q = [x.strip() for x in ln.split("|")]
        if sec == "topics" and len(q) > 1 and q[0]: L["topics"].append(dict(id=q[0], al=[q[0]] + [x for x in q[1].split(";") if x], pa=q[2] if len(q) > 2 else ""))
        elif sec == "gap" and len(q) > 1: L["gap"].setdefault(q[0], []).extend([x for x in q[1].split(";") if x])
        elif sec in ("method", "exclude"): L[sec].extend([x.lower() if sec == "exclude" else x for x in ln.replace("|", ";").split(";") if x])
    return L

def hits(t, ts):
    t = N(t).lower(); n = 0
    for w in ts:
        w = N(w).lower()
        if not w: continue
        n += len(re.findall(r"(?<![a-z0-9])" + re.escape(w) + r"(?![a-z0-9])", t)) if re.search(r"[a-z]", w) else t.count(w)
    return n

def tps_of(r, L):
    b = " ".join([r["title"], r.get("abstract") or "", (r.get("text") or "")[:1500]])
    return sorted([dict(id=t["id"], h=c, pa=t["pa"]) for t in L["topics"] for c in [hits(b, t["al"])] if c > 0], key=lambda x: -x["h"])

def wnd(y0, y1):
    sp = y1 - y0 + 1
    w = 1 if sp <= 5 else (2 if sp <= 10 else max(3, min(5, -(-sp // 5))))
    out, s = [], y0
    while s <= y1: out.append((s, min(s + w - 1, y1))); s += w
    if len(out) > 1 and out[-1][1] - out[-1][0] + 1 < w / 2.0: out[-2] = (out[-2][0], out[-1][1]); out = out[:-1]
    return out, w

def mv(x): return sum(x) / float(len(x)) if x else 0.0

def cpts(ys, c, tot):
    a = [c.get(y, 0) for y in ys]
    R = dict(method="3-year centred mean, 1 breakpoint", candidates=[],
             note="<5 years or <8 records: no turning point claimed")
    if len(ys) < 5 or tot < 8: return R
    R["note"] = ""
    sm = [mv([a[max(0, i - 1)], a[i], a[min(len(a) - 1, i + 1)]]) for i in range(len(a))]
    _, i = max([(abs(mv(sm[i:]) - mv(sm[:i])), i) for i in range(2, len(a) - 1)])
    b, f = mv(sm[:i]), mv(sm[i:])
    if abs(f - b) < .5:
        R["note"] = "level change %.2f -> %.2f too small for a breakpoint" % (b, f); return R
    rt = (f / b) if b > 0 else None
    strong = (f > b and rt is not None and rt >= 1.5) or (f <= b and b > 0 and f <= .67 * b)
    R["candidates"] = [dict(year=ys[i], direction="up" if f > b else "down", before_mean=round(b, 2), after_mean=round(f, 2),
                            ratio=(round(rt, 2) if rt is not None else None), strength="supported_change" if strong else "candidate_only")]
    m = mv(a) or 1.0
    R["cv"] = round((sum((x - m) ** 2 for x in a) / len(a)) ** .5 / m, 2)
    R["fluctuation_only"] = bool(R["cv"] > .8 and not strong)
    return R

def tst(se, nw_, tot, NT):
    nz = [i for i, c in enumerate(se) if c > 0]
    if not nz: return "absent", "absent in every window"
    if tot <= 1: return "single_mention", "one record, not a trend"
    pk, pi = max(se), se.index(max(se))
    if nz[0] >= 1 and se[nz[0]] >= max(2, .02 * NT): return "emergence", "first in window %d/%d with %d records" % (nz[0] + 1, nw_, se[nz[0]])
    if pk >= 2 and pi <= nw_ - 2 and se[-1] < .5 * pk: return "decline", "peak %d at window %d/%d, last %d" % (pk, pi + 1, nw_, se[-1])
    if len(nz) >= max(2, int(.6 * nw_)): return "persistence", "present in %d/%d windows" % (len(nz), nw_)
    return "intermittent", "present in %d/%d windows, no direction" % (len(nz), nw_)

def sents(t): return [N(x) for x in re.split(r"(?<=[.!?\u3002\uff01\uff1f])\s+|\n+", N(t)) if len(N(x)) >= 30]
def vq(q, r): return len(N(q)) >= 10 and any(N(q) in N(r.get(f) or "") for f in ("text", "title", "abstract"))

def ploc(r, q):
    for i, p in enumerate(r.get("pages") or [], 1):
        if q and q in N(p): return "%s#p%d" % (r["file"], i)
    return r["loc"]


def evq(r):
    if (r.get("q") or 0) >= 0.55:
        s = [x for x in sents(r.get("text") or "") if len(x) >= 10]
        if s: return s[0][:280]
    return N(r.get("title"))[:280] if len(N(r.get("title"))) >= 10 else ""

POS = ("improve", "increase", "significan", "outperform", "effective", "\u63d0\u9ad8")
NEG = ("no significan", "did not", "fail", "decrease", "ineffective", "\u65e0\u663e\u8457", "\u5e76\u672a")

def ana(Y, cnt, ys, NT, L, meta, nrec, un):
    ws, ww = wnd(ys[0], ys[-1]); cp = cpts(ys, cnt, len(Y))
    tt = dict(span=[ys[0], ys[-1]], window_width=ww, windows=["%d-%d" % a for a in ws],
              annual=[dict(year=y, count=cnt[y], share=round(cnt[y] / float(len(Y)), 3), delta=cnt[y] - cnt.get(y - 1, 0)) for y in ys],
              change_points=cp, caveats=["year from metadata else text; source per record in evidence_map.csv",
                                         "supplied records only; no external DB, no completeness claim",
                                         "a thin final year may be incomplete indexing, not a decline"])
    if len(ys) > 1 and cnt[ys[-1]] < max(1, cnt[ys[-2]] * .6): tt["caveats"].append("final year %d much thinner than %d" % (ys[-1], ys[-2]))
    if cp.get("note"): un.append(dict(type="trend_weak", detail=cp["note"], basis="%d records / %d years" % (len(Y), len(ys))))
    if cp.get("fluctuation_only"): un.append(dict(type="trend_fluctuation", detail="CV=%s without sustained direction: fluctuation, not a turning point" % cp.get("cv"), basis="change-point test"))
    wi = dict((r["id"], next((i for i, ab in enumerate(ws) if ab[0] <= r["year"] <= ab[1]), -1)) for r in Y)
    bw = defaultdict(list); ser = dict((t["id"], [0] * len(ws)) for t in L["topics"])
    for r in Y:
        i = wi[r["id"]]
        if i < 0: continue
        bw[i].append(r)
        for t in r["topics"]: ser[t["id"]][i] += 1
    rows = []
    for t in L["topics"]:
        se = ser[t["id"]]
        if not any(se): continue
        st, why = tst(se, len(ws), sum(se), NT)
        rows.append(dict(topic=t["id"], series=se, total=sum(se), status=st, basis=why, parent=t["pa"]))
    mrg = []
    for r in rows:
        kid = [t["id"] for t in L["topics"] if t["pa"] == r["topic"]]
        if kid and r["status"] == "decline" and all(sum(ser[k]) >= 2 for k in kid): mrg.append(dict(pair=[r["topic"]] + kid, status="candidate_split", basis="parent declines, 2+ children hold records"))
    tev = dict(n_windows=len(ws), window_width=ww, topics=rows, merge_split_candidates=mrg, unmapped_count=len([r for r in Y if not r["topics"]]),
               rule="emergence: first non-zero window>=2 and count>=max(2,2%N); decline: last<=50% of peak; persistence: >=60% windows; single_mention: total<=1")
    rp, ind = {}, meta.get("ind", {})
    for i, ab in enumerate(ws):
        wt = set(t["id"] for r in bw[i] for t in r["topics"])
        sc = []
        for r in bw[i]:
            cen = (len(set(t["id"] for t in r["topics"]) & wt) / float(len(wt))) if wt else 0.0
            di = ind.get((r.get("doi") or "").lower()) or ind.get(ntt(r["title"])) or 0
            mf = hits((r.get("title") or "") + " " + (r.get("abstract") or ""), L["method"])
            sc.append((round(.45 * cen + .35 * min(di / 5., 1.) + .2 * min(mf, 3) / 3., 3), di, mf, r))
        sc.sort(key=lambda x: (-x[0], -x[2]))
        top = sc[:3]; tail = [x for x in sc if x[2] > 0 and x not in top][:1]
        rp["%d-%d" % ab] = [dict(record=r["id"], title=N(r["title"])[:150], year=r.get("year"), doi=r.get("doi"), locator=r["loc"],
                                 score=s, in_degree=d, long_tail=bool(m and d <= 1), rationale="centrality + in-degree %d + method-first cue %d" % (d, m))
                            for s, d, m, r in top + tail]
    reps = dict(by_window=rp, coverage=dict(windows=len(ws), long_tail=sum(1 for v in rp.values() for x in v if x["long_tail"])), ind_source="supplied reference-graph edges only; none => 0",
                rule="0.45*topic centrality +0.35*in-degree +0.20*method-first cue; top3/window +1 long-tail")
    gl = defaultdict(list)
    for r in Y:
        for s in sents(r.get("text") or "")[:200]:
            for typ, cues in L["gap"].items():
                if hits(s, cues) > 0: gl[(typ, r["topics"][0]["id"] if r["topics"] else "")].append(dict(rec=r["id"], loc=ploc(r, s), quote=s[:280], ok=vq(s, r), year=r.get("year"), doi=r.get("doi")))
    gaps = []
    for (typ, tp), it in sorted(gl.items(), key=lambda kv: -len(kv[1])):
        src = sorted(set(x["rec"] for x in it))
        gaps.append(dict(gap_id="G%02d" % (len(gaps) + 1), type=typ, topic=tp, mention_count=len(it), source_count=len(src), sources=src[:8], quotes=it[:2],
                         basis="%d records of %d screened; not from missing hits" % (len(src), nrec),
                         status="directly_supported" if len(src) >= 2 else "insufficient"))
    bt = defaultdict(lambda: dict(pos=[], neg=[]))
    for r in Y:
        if not r["topics"]: continue
        for s in sents(r.get("text") or "")[:200]:
            if hits(s, NEG): bt[r["topics"][0]["id"]]["neg"].append(dict(rec=r["id"], loc=ploc(r, s), quote=s[:240], year=r.get("year")))
            elif hits(s, POS): bt[r["topics"][0]["id"]]["pos"].append(dict(rec=r["id"], loc=ploc(r, s), quote=s[:240], year=r.get("year")))
    conf = [dict(topic=t, positive=v["pos"][:2], negative=v["neg"][:2], status="unresolved_in_corpus", basis="opposite-direction statements from different records; no meta-analysis done")
            for t, v in bt.items() if v["pos"] and v["neg"] and len(set(x["rec"] for x in v["pos"] + v["neg"])) >= 2]
    return tt, tev, reps, gaps, conf

def render(res, ex, un, cm, fl):
    tt = res["time_trend"]; cp = (tt.get("change_points", {}).get("candidates") or [None])[0]
    ctx = dict(CASE=str(res["case_id"]), TOPIC=str(res["research_question"].get("topic") or "not stated in case.json"),
               META="- files %s | parsed %s | included %s | excluded %s | span %s | window %s y" % (
                   res["corpus"]["files"], res["screening"]["records_parsed"], res["screening"]["records_included"], res["screening"]["records_excluded"],
                   "%d-%d" % tuple(tt["span"]) if tt.get("span") else "n/a", tt.get("window_width", "n/a")),
               QTAB=tb(["sub-question", "weight", "product"], [[d["q"], d["weight"], d["product"]] for d in res["research_question"]["decomposition"]]),
               SCREEN="\n".join("- %s: %s" % (x["record"], x["reason"]) for x in ex[:8]) or "- no record excluded",
               TREND=tb(["year", "count", "share", "delta"], [[a["year"], a["count"], a["share"], a["delta"]] for a in tt.get("annual", [])]),
               TRENDNOTE=("change point: year %d %s (%s; %.2f -> %.2f records/year)" % (cp["year"], cp["direction"], cp["strength"], cp["before_mean"], cp["after_mean"]))
               if cp else "change point: " + (tt.get("change_points", {}).get("note") or "none detected"),
               EVOL=tb(["topic", "per-window", "total", "status", "basis"], [[t["topic"], "/".join(map(str, t["series"])), t["total"], t["status"], t["basis"]] for t in res["topic_evolution"].get("topics", [])]),
               REPS=tb(["window", "record", "title", "year", "score", "long-tail"], [[w, p["record"], p["title"], p["year"], p["score"], p["long_tail"]] for w, v in res["representative_works"].get("by_window", {}).items() for p in v]),
               GAPS="\n".join("- **%s [%s]** %s: %d msgs / %d recs, %s; %s" % (x["gap_id"], x["type"], x["topic"], x["mention_count"], x["source_count"], x["status"], x["basis"]) for x in res["research_gaps"][:6])
               or "- no quotable gap wording found in this corpus; that is not evidence of absence",
               CONF="\n".join("- `%s`: %d positive / %d negative statements, unresolved" % (c["topic"], len(c["positive"]), len(c["negative"])) for c in res["conflicts"][:5])
               or "- no opposite-direction statement pair found",
               EVID=tb(["claim", "strength", "source", "locator", "quote"], [[e["claim_id"], e["strength"], e["source_id"], e["locator"], e["quote"][:50]] for e in res["evidence_matrix"][:18]]),
               LIMIT="\n".join("- %s" % u["detail"] for u in un) + "\n- contract keys %d/%d, quotes verified %d/%d" % (
                   fl, len(cm), res["verification"]["quotes_verified"], res["verification"]["quotes"]))
    p = REF / "report_template.md"
    t = p.read_text(encoding="utf-8") if p.is_file() else "# Research trend report\n\n{{TREND}}\n\n{{EVOL}}\n\n{{GAPS}}\n\n{{LIMIT}}\n"
    for k, v in ctx.items(): t = t.replace("{{" + k + "}}", str(v))
    return t
