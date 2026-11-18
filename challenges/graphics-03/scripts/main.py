#!/usr/bin/env python3
"""graphics-03: Agent-led builder for biological mechanism / pathway figures.

init  -> index the material, write a legal partial result.json
show  -> print source text with locators
check -> verify plan.json quotes, ids and workorder coverage
build -> render figure.svg + figure.pdf, content_map, checks, result.json,
         and the verification set: golden_standard.json, diff_report.md,
         version_history.md, self_check.json, run.log
selftest -> run --help / minimal / empty / bad-JSON probes, report exit codes

The Agent writes plan.json; these commands only index, verify and render.
Always exits 0 and always leaves a legal result.json behind.
"""
import argparse
import contextlib
import io
import json
import platform
import re
import subprocess
import sys
import time
import traceback
import xml.etree.ElementTree as ET
import zipfile
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
try:
    import render as RD
except Exception:
    RD = None

CANON = {"editable_source": ("editable_source", "source_file", "svg", "editable_svg", "diagram_source"),
         "export_artifact": ("export_artifact", "export", "exports", "pdf", "rendered_output"),
         "content_map": ("content_map", "element_map", "traceability"),
         "compliance_checks": ("compliance_checks", "compliance", "checks", "qa_checks"),
         "exceptions": ("exceptions", "issues", "warnings")}
CLEAN = {".txt", ".md", ".markdown", ".json", ".csv", ".tsv", ".yaml", ".yml", ".xml", ".html", ".svg"}
BIN = {".pdf": "pdf", ".docx": "docx", ".xlsx": "xlsx", ".pptx": "pptx", ".png": "image",
       ".jpg": "image", ".jpeg": "image", ".tif": "image", ".tiff": "image", ".zip": "zip"}
STOPW = set("the a an this that these those it its they we our which who and but or if when then "
            "than as at by for from in into of on to with also both each such other protein proteins "
            "gene genes cell cells pathway signal signalling signaling level levels".split())
MECH = re.compile(r"\b([A-Za-z][A-Za-z0-9\-]{1,15})\s+(activates?|inhibits?|represses?|binds?|"
                  r"phosphorylates?|ubiquitinates?|translocates?|transports?|recruits?|promotes?|"
                  r"suppresses?|induces?)\s+([A-Za-z][A-Za-z0-9\-]{1,15})\b")

def now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def jread(p):
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return json.loads(Path(p).read_text(encoding=enc))
        except Exception:
            continue
    return None

def jwrite(p, obj):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def fnorm(s):
    return re.sub(r"\s+", " ", str(s or "")).strip()

def key(s):
    return re.sub(r"[^a-z0-9]", "_", str(s).lower()).strip("_")


def log(work, out, level, msg):
    """Append-only step log; one line per event, mirrored into work/ and output/run.log."""
    line = "%s  %-5s %s" % (now(), level, msg)
    for d in (work, out):
        try:
            Path(d).mkdir(parents=True, exist_ok=True)
            with (Path(d) / "run.log").open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except Exception:
            pass
    return line

def find_case(inp):
    inp = Path(inp)
    for c in (inp / "case.json", inp / "input" / "case.json"):
        if c.is_file():
            return c
    hits = [p for p in inp.rglob("*.json") if re.search(r"(^|/)(case|input)[^/]*\.json$", p.as_posix())]
    return sorted(hits)[0] if hits else None

def dig(obj, wants, depth=0):
    if depth > 6:
        return None
    if isinstance(obj, dict):
        for k, v in obj.items():
            if v not in (None, "", [], {}) and any(
                    key(k) == w or key(k).endswith(w) or w in key(k) for w in wants):
                return v
        kids = obj.values()
    elif isinstance(obj, list):
        kids = obj[:40]
    else:
        return None
    for v in kids:
        got = dig(v, wants, depth + 1)
        if got is not None:
            return got
    return None

def kind_of(p):
    if p.suffix.lower() in BIN:
        return BIN[p.suffix.lower()]
    if p.suffix.lower() in CLEAN:
        return "text"
    try:
        h = p.open("rb").read(5)
    except Exception:
        return "unknown"
    return ("pdf" if h.startswith(b"%PDF") else "image" if h.startswith(b"\x89PNG")
            else "zip-office" if h.startswith(b"PK") else "unknown")

def pdf_text(path):
    data = Path(path).read_bytes()
    out = []
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", data, re.S):
        raw = m.group(1)
        try:
            raw = zlib.decompress(raw)
        except Exception:
            pass
        ch = []
        for sm in re.finditer(rb"\((?:\\.|[^\\()])*\)|<[0-9A-Fa-f\s]{4,}>", raw):
            s = sm.group(0)
            if s.startswith(b"<"):
                try:
                    b = bytes.fromhex(re.sub(rb"\s", b"", s[1:-1]).decode())
                    ch.append(b.decode("utf-16-be", "ignore") if b.count(b"\x00") > len(b) // 3
                              else b.decode("latin-1", "ignore"))
                except Exception:
                    pass
            else:
                ch.append(re.sub(rb"\\(.)", rb"\1", s[1:-1]).decode("latin-1", "ignore"))
        if "".join(ch).strip():
            out.append(" ".join(ch))
    return out, len(re.findall(rb"/Type\s*/Page[^s]", data))

def blocks_of(path):
    k = kind_of(path)
    try:
        if k == "pdf":
            parts, npage = pdf_text(path)
            if not "".join(parts).strip():
                return [], "pdf text not recoverable (scanned/encoded): treat as image, do not invent content"
            return [("%s#stream%d" % (path.name, i + 1), fnorm(t)) for i, t in enumerate(parts)], \
                   "pdf: %d pages, %d text streams" % (npage, len(parts))
        if k == "image":
            return [], "raster image: no pixel-level reading; only human-verifiable content"
        if k in ("docx", "xlsx", "pptx", "zip-office"):
            with zipfile.ZipFile(path) as z:
                t = "\n".join(re.sub(r"<[^>]+>", "", re.sub(r"</w:p>|</a:p>|</text:p>", "\n",
                                   z.read(n).decode("utf-8", "ignore")))
                              for n in z.namelist()[:40] if n.endswith(".xml"))
        else:
            t = path.read_bytes().decode("utf-8-sig", "ignore")
        if not t.strip():
            return [], "no extractable text"
        paras = [fnorm(x) for x in re.split(r"\n\s*\n", t)]
        paras = [p for p in paras if p] or [fnorm(x) for x in t.splitlines() if fnorm(x)]
        return [("%s#para%d" % (path.name, i + 1), p) for i, p in enumerate(paras)], None
    except Exception as exc:
        return [], "%s: %s" % (type(exc).__name__, exc)

def collect(inp):
    inp, mats, corpus = Path(inp), [], []
    if not inp.exists():
        return mats, corpus
    for p in sorted(inp.rglob("*")):
        if not p.is_file() or p.name.startswith("."):
            continue
        blocks, note = blocks_of(p)
        mats.append({"id": p.name, "path": str(p), "rel": p.relative_to(inp).as_posix(),
                     "kind": kind_of(p), "bytes": p.stat().st_size, "blocks": len(blocks), "note": note,
                     "locators": [b[0] for b in blocks[:3]]})
        corpus += [{"material": mats[-1]["rel"], "locator": loc, "text": t} for loc, t in blocks]
    return mats, corpus

def hit(corpus, quote):
    q = fnorm(quote)
    if len(q) < 6:
        return None
    return next((b["locator"] for b in corpus if q in b["text"]), None)

def cnames(case):
    oc = case.get("output_contract") if isinstance(case, dict) else None
    if oc is None and isinstance(case, dict):
        oc = dig(case, ["outputcontract", "outputfields", "requiredfields"])
    if isinstance(oc, dict):
        return list(oc.keys())
    if isinstance(oc, (list, tuple)):
        return [str(x) for x in oc]
    return [x.strip() for x in re.split(r"[,\n;]+", oc) if x.strip()] if isinstance(oc, str) else []

def finalise(out, case, status, values):
    """Every declared contract field verbatim (unknown -> null) + the fixed status block."""
    names, res = cnames(case), {}
    for nm in names:
        k = key(nm)
        res[nm] = next((values[c] for c, alts in CANON.items()
                        if k in [key(a) for a in alts] and values.get(c) is not None), values.get(k))
    for k, v in values.items():
        res.setdefault(k, v)
    res["case_id"] = values.get("case_id") or ((case or {}).get("case_id") if isinstance(case, dict) else None)
    res["status"] = status
    for k in ("sources", "uncertainty", "pending_human", "errors", "degradations", "changes"):
        res.setdefault(k, [])
    for k, f in (("golden_standard", "golden_standard.json"), ("diff_report", "diff_report.md"),
                 ("version_history", "version_history.md"), ("self_check", "self_check.json")):
        res.setdefault(k, {"status": "pending", "file": f, "note": "not produced by this stage; run build"})
    res.setdefault("runtime", {})
    res["contract_fields"] = {"declared": names, "filled": [n for n in names if res.get(n) is not None],
                             "null_fields": [n for n in names if res.get(n) is None]}
    jwrite(Path(out) / "result.json", res)
    return res


def load_plan(work, out):
    for p in (Path(work) / "plan.json", Path(out) / "plan.json"):
        if p.is_file():
            obj = jread(p)
            if isinstance(obj, dict) and (obj.get("entities") or obj.get("relations")):
                return obj, str(p), None
            return None, str(p), "plan.json present but has no entities/relations"
    return None, None, "plan.json not found"


def get_case(inp):
    cp = find_case(inp)
    return jread(cp) if cp else None

def workorder(case):
    wo = dig(case, ["organizerworkorder", "workorder", "drawingorder", "figureworkorder"]) if isinstance(case, dict) else None
    return wo if isinstance(wo, dict) else {}

def req(wo, names):
    return next((wo[n] for n in names if wo.get(n)), [])

def fallback_plan(case, mats, corpus):
    wo = workorder(case)
    els = req(wo, ["required_elements", "elements", "entities", "required_entities"])
    rls = [r for r in req(wo, ["required_relations", "relations", "edges", "interactions"]) if isinstance(r, dict)]
    comps = req(wo, ["compartments", "regions", "layers"])
    title = ""
    for cand in (wo.get("title"), dig(case, ["taskinstruction", "instruction", "task"]) if isinstance(case, dict) else None):
        if isinstance(cand, str) and cand.strip():
            title = fnorm(cand.split("\n")[0])[:120]
            break
    ents, rels, seen = [], [], set()

    def add(lab, kind="unspecified", quote=None, loc="case.json#workorder"):
        lab = fnorm(lab)
        if lab and len(lab) <= 60 and lab.lower() not in seen:
            seen.add(lab.lower())
            ents.append({"id": lab, "label": lab, "kind": kind, "compartment": "unspecified",
                         "evidence": {"quote": quote or lab, "locator": loc}})

    for e in (els if isinstance(els, list) else []):
        d = e if isinstance(e, dict) else {"label": e}
        add(d.get("label") or d.get("name") or d.get("id"), (d.get("kind") or "unspecified").lower())
    for i, d in enumerate(rls):
        s0, t0 = fnorm(d.get("source") or d.get("from")), fnorm(d.get("target") or d.get("to"))
        if s0 and t0:
            add(s0)
            add(t0)
            rels.append({"id": "r%d" % (i + 1), "source": s0, "target": t0, "label": fnorm(d.get("label")),
                         "type": d.get("type") or "unspecified",
                         "evidence": {"quote": "%s -> %s" % (s0, t0),
                                      "locator": "case.json#workorder.required_relations[%d]" % i}})
    gaps = ["Fallback plan: labels are literal input strings or file names; no biology was inferred."]
    if not ents:                                  # mine explicit subject-verb-object sentences
        stop, pat = STOPW, MECH
        for b in corpus:
            for m in pat.finditer(b["text"]):
                if m.group(1).lower() in stop or m.group(3).lower() in stop:
                    continue
                add(m.group(1), quote=m.group(0), loc=b["locator"])
                add(m.group(3), quote=m.group(0), loc=b["locator"])
                rels.append({"id": "r%d" % (len(rels) + 1), "source": m.group(1), "target": m.group(3),
                             "type": RD.rtype(m.group(2)) if RD else m.group(2), "label": "",
                             "evidence": {"quote": m.group(0), "locator": b["locator"]}})
            if len(rels) > 40:
                break
        if rels:
            gaps.insert(0, "Edges mined only from explicit 'A activates B' sentences; compartments, feedback "
                           "loops and missing links need review.")
    if not ents:                                  # last resort: material inventory
        for m in mats[:8]:
            add(m["rel"])
        gaps.append("No workorder list and no Agent plan.json: this figure inventories the supplied materials "
                    "only. Read them, write plan.json, rebuild.")
    return {"title": title or "Supplied mechanism materials (inventory)",
            "subtitle": "fallback rendering - Agent plan.json not found",
            "compartments": [dict({"id": fnorm(c.get("id") or c.get("label")) if isinstance(c, dict) else fnorm(c),
                                   "order": i},
                                  label=fnorm(c.get("label") or c.get("id")) if isinstance(c, dict) else fnorm(c))
                             for i, c in enumerate(comps)],
            "entities": ents, "relations": rels, "gaps": gaps}

def validate(plan, corpus, case):
    rep = {"ok": True, "issues": [], "rejected": []}
    ents = [e for e in (plan.get("entities") or []) if isinstance(e, dict)]
    rels = [r for r in (plan.get("relations") or []) if isinstance(r, dict)]
    ids = set()

    def ev_of(x, kind, xid):
        ev = x.get("evidence") or {}
        q = ev.get("quote") if isinstance(ev, dict) else None
        loc = hit(corpus, q) if q else None
        if loc:
            ev["verified_locator"] = loc
        elif q and (len(fnorm(q)) < 6 or str(ev.get("locator", "")).startswith("case.json")):
            ev["declared_locator"] = ev.get("locator")
        elif q:
            rep["rejected"].append({"kind": kind, "id": xid, "quote": fnorm(q)[:90]})
        else:
            rep["issues"].append("%s %s: no evidence quote" % (kind, xid))

    for e in ents:
        eid = fnorm(e.get("id"))
        if not eid:
            rep["issues"].append("entity without id: %r" % (e.get("label"),))
            continue
        if eid in ids:
            rep["issues"].append("duplicate entity id: %s" % eid)
        ids.add(eid)
        rep["issues"] += ["%s: missing %s" % (eid, f) for f in ("label", "kind", "compartment") if not fnorm(e.get(f))]
        ev_of(e, "entity", eid)
    for r in rels:
        s0, t0 = fnorm(r.get("source")), fnorm(r.get("target"))
        if s0 not in ids or t0 not in ids:
            rep["issues"].append("relation %s references unknown entity (%s -> %s)" % (r.get("id"), s0, t0))
        if not fnorm(r.get("type")):
            rep["issues"].append("relation %s->%s has no type" % (s0, t0))
        ev_of(r, "relation", r.get("id"))
    wo = workorder(case)

    def res(name):
        n = fnorm(name).lower()
        if not n:
            return None
        for e in ents:
            if n in (fnorm(e.get("id")).lower(), fnorm(e.get("label")).lower()):
                return fnorm(e.get("id")).lower()
        for e in ents:
            if n in set(re.split(r"[^a-z0-9]+", fnorm(e.get("label")).lower())):
                return fnorm(e.get("id")).lower()
        return None

    need = [fnorm(x.get("label") if isinstance(x, dict) else x)
            for x in req(wo, ["required_elements", "elements", "entities", "required_entities"])]
    miss = [n for n in need if n and res(n) is None]
    needr = [x for x in req(wo, ["required_relations", "relations", "edges"]) if isinstance(x, dict)]
    have = set((res(r.get("source")), res(r.get("target"))) for r in rels)
    missr = ["%s->%s" % (fnorm(x.get("source")), fnorm(x.get("target"))) for x in needr
             if res(x.get("source")) and res(x.get("target"))
             and (res(x.get("source")), res(x.get("target"))) not in have]
    dec = lambda items: len([x for x in items if (x.get("evidence") or {}).get("declared_locator")])
    rep["counts"] = {"entities": len(ents), "relations": len(rels),
                     "entities_verified": len([e for e in ents if (e.get("evidence") or {}).get("verified_locator")]),
                     "relations_verified": len([r for r in rels if (r.get("evidence") or {}).get("verified_locator")]),
                     "entities_declared": dec(ents), "relations_declared": dec(rels),
                     "required_elements": len(need), "required_elements_missing": len(miss),
                     "required_relations": len(needr), "required_relations_missing": len(missr),
                     "rejected_quotes": len(rep["rejected"])}
    rep["missing_required_elements"], rep["missing_required_relations"] = miss, missr
    rep["ok"] = not rep["issues"] and not rep["rejected"] and not miss and not missr
    return rep

# ------------------------------------------------------------- v2 verification assets
REFS = HERE.parent / "references"
ORD = (("extracellular", r"extracellular|胞外"), ("membrane", r"membrane|膜|plasma"),
       ("cytoplasm", r"cytoplasm|cytosol|胞质|胞浆"), ("nucleus", r"nucleus|nuclear|核"))
RULES = (
    ("legend.edge_shape", "render-rules.md", "实心箭头=激活、T 形=抑制、空心箭头=结合", "端点形状编码关系类型"),
    ("legend.node_fill", "render-rules.md", "填充色只编码 `kind`", "填充色只编码实体种类"),
    ("legend.autogen", "render-rules.md", "图例由**实际出现的** kind/type 生成", "图例与图面逐项一致"),
    ("layout.bands", "render-rules.md", "每个区室一条横带，按 `order` 自上而下：上游在上、下游在下", "区室按上游→下游分层"),
    ("layout.transmembrane", "render-rules.md",
     "跨膜语义靠带表达：配体在胞外带、受体在膜带、激酶在胞质带、转录因子/靶基因在核带", "受体必须落在膜带"),
    ("layout.direction", "render-rules.md", "方向严格 `source → target`，不反向绘制", "边方向=原文语序"),
    ("layers.ids", "render-rules.md", "元素 id `comp-<区室>`、`ent-<实体>`、`rel-<关系>`", "id 与 content_map 对应；SVG 需 <text> 与 ≥4 分组"),
    ("export.pdf", "render-rules.md", "%PDF-1.4` 开头、含 `/Type /Page`、`%%EOF` 结尾", "PDF 真实矢量判据"),
    ("naming.title", "plan-schema.md", "写清机制，不写「Figure 1」", "标题陈述机制"),
)


def nk(s):
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def refitem(doc, quote, stmt, cid):
    """Expected item backed by a verbatim quote re-located inside a reference doc."""
    q, sec, ok, head = fnorm(quote), "-", False, "-"
    try:
        lines = (REFS / doc).read_text(encoding="utf-8").splitlines()
    except Exception:
        lines = []
    for ln in lines:
        if ln.lstrip().startswith("#"):
            head = re.sub(r"^#+\s*", "", ln).strip()
        if q and q in fnorm(ln):
            sec, ok = head, True
            break
    ok = ok or bool(q and lines and q in fnorm(" ".join(lines)))
    return {"id": cid, "statement": stmt, "evidence": {"source": "references/" + doc, "quote": q,
            "locator": "references/%s#%s" % (doc, sec), "quote_verified": ok}}


def ftree(o, wants, path="", d=0):
    """First matching (json-path, value) for a semantically named key; key names are not assumed."""
    if d > 4 or not isinstance(o, (dict, list)):
        return (None, None)
    it = list(o.items()) if isinstance(o, dict) else [(None, v) for v in o[:20]]
    for k, v in it:
        if k is not None and any(w in key(k) for w in wants):
            return (path + "." + k).lstrip("."), v
    for k, v in it:
        g = ftree(v, wants, path if k is None else (path + "." + k).lstrip("."), d + 1)
        if g[1] is not None:
            return g
    return (None, None)


def gstd(case, cp, corpus):
    """Golden standard: expected entity/relation/rule items, each with locator + verbatim quote."""
    demo = bool(isinstance(case, dict) and (case.get("demo")
                                            or "synthetic" in str(case.get("kind", "")).lower()))
    canon = []
    for kw in ({"ensure_ascii": False, "sort_keys": True}, {"ensure_ascii": True, "sort_keys": True}):
        try:
            canon.append(fnorm(json.dumps(case, **kw)))
        except Exception:
            pass
    try:
        canon.append(fnorm(Path(cp).read_text(encoding="utf-8"))) if cp else None
    except Exception:
        pass
    E, R = {}, {}

    def decl(v, loc):
        q = fnorm(v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, sort_keys=True))
        return {"source": "case.json", "locator": loc, "quote": q[:600],
                "quote_verified": bool(q) and any(q in t for t in canon)}

    def add_e(lab, kind=None, ev=None):
        k = nk(lab)
        if not k or len(fnorm(lab)) > 80:
            return
        d = E.setdefault(k, {"id": "gE-" + k[:28], "label": fnorm(lab), "kind_expected": "unspecified",
                             "kind_basis": "not_stated", "evidence": []})
        if kind and kind != "unspecified":
            d["kind_expected"], d["kind_basis"] = kind, "workorder"
        if ev and ev not in d["evidence"]:
            d["evidence"].append(ev)

    def add_r(s, t, ty, ev):
        if not nk(s) or not nk(t) or nk(s) == nk(t):
            return
        d = R.setdefault("%s>%s|%s" % (nk(s), nk(t), ty), {
            "id": "gR-%02d" % (len(R) + 1), "source": fnorm(s), "target": fnorm(t), "type": ty,
            "direction": "%s -> %s" % (fnorm(s), fnorm(t)), "evidence": []})
        if ev and ev not in d["evidence"]:
            d["evidence"].append(ev)

    wo = case if isinstance(case, dict) else {}
    pe, els = ftree(wo, ["requiredelements", "requiredentities", "elements", "entities"])
    for i, e in enumerate(els if isinstance(els, list) else []):
        d = e if isinstance(e, dict) else {"label": e}
        lab = fnorm(d.get("label") or d.get("name") or d.get("id"))
        if lab:
            add_e(lab, str(d.get("kind") or "unspecified").lower(), decl(lab, "case.json#%s[%d]" % (pe, i)))
    pr, rws = ftree(wo, ["requiredrelations", "relations", "edges", "interactions"])
    for i, d in enumerate([x for x in (rws if isinstance(rws, list) else []) if isinstance(x, dict)]):
        s, t = fnorm(d.get("source") or d.get("from")), fnorm(d.get("target") or d.get("to"))
        if s and t:
            loc = "case.json#%s[%d]" % (pr, i)
            add_e(s, ev=decl(s, loc + ".source"))
            add_e(t, ev=decl(t, loc + ".target"))
            add_r(s, t, RD.rtype(d.get("type")) if RD else "unspecified", decl(d, loc))
    for b in corpus:
        for m in MECH.finditer(b["text"]):
            if m.group(1).lower() in STOPW or m.group(3).lower() in STOPW:
                continue
            ev = {"source": b["material"], "locator": b["locator"], "quote": m.group(0), "quote_verified": True}
            add_e(m.group(1), ev=ev)
            add_e(m.group(3), ev=ev)
            add_r(m.group(1), m.group(3), RD.rtype(m.group(2)) if RD else "unspecified", ev)
        if len(R) > 40:
            break
    items = []
    for d in list(E.values()) + list(R.values()):
        d["evidence"].sort(key=lambda e: (0 if e.get("quote_verified") else 1, e.get("source") or ""))
        del d["evidence"][2:]
        d["evidence_status"] = (("verbatim" if d["evidence"][0].get("quote_verified") else "declared_only")
                                if d["evidence"] else "none")
        items += d["evidence"]
    rules = [refitem(doc, q, st, cid) for cid, doc, q, st in RULES]
    items += [r["evidence"] for r in rules]
    un = [i for i in items if not i.get("quote_verified")]
    gaps = ["材料与工单都没有可判定实体：图面实体即无据补造。"] if not E else []
    if not R:
        gaps.append("没有显式主谓宾机制句：关系与方向无法从原文确定，须人工确认。")
    return {"$schema": "graphics-03/golden-standard/v1", "version": "v2", "generated": now(),
            "case_id": (case or {}).get("case_id"), "demo": demo,
            "provenance_note": ("示例，非正式案例结果 (synthetic example; not a formal case answer)" if demo
                                else "case-bound expectations derived only from /input materials"),
            "purpose": "期望交付清单：实体/关系(含类型与方向)、证据 locator+逐字quote、图例与布局规则；紧凑 JSON，人读版见 diff_report.md。",
            "how_derived": "实体/关系只取工单条目(declared)与材料显式机制句(verbatim)；规则取自 references/*.md 并逐字回查；判不准记 unspecified。",
            "entities": sorted(E.values(), key=lambda x: x["label"].lower()),
            "relations": sorted(R.values(), key=lambda x: x["id"]),
            "rules": {"legend": [r for r in rules if r["id"].startswith("legend")],
                      "layout": [r for r in rules if r["id"].startswith(("layout", "layers"))],
                      "export": [r for r in rules if r["id"].startswith(("export", "naming"))]},
            "counts": {"entities": len(E), "relations": len(R), "rules": len(rules),
                       "relation_types": sorted({r["type"] for r in R.values()}),
                       "evidence_items": len(items), "evidence_verified": len(items) - len(un)},
            "verification": {"verified": len(items) - len(un), "unverified": len(un),
                             "unverified_quotes": [u.get("quote", "")[:100] for u in un[:8]]},
            "gaps": gaps,
            "limits": "材料用图/表表达的关系不进金标准（缺口见 gaps）；允许补有逐字证据的额外项，标「金标准外」。"}


def tbl(head, rows):
    return "\n".join(["| " + " | ".join(head) + " |", "|" + "|".join(["---"] * len(head)) + "|"] +
                     ["| " + " | ".join(str(x).replace("|", "/") for x in r) + " |" for r in rows])


def diff_rep(g, p, cmap):
    """Item-by-item comparison of the delivered figure against the golden standard."""
    c = dict.fromkeys(("e_ok", "e_miss", "e_kind", "e_soft", "r_ok", "r_miss", "r_type", "r_dir",
                       "x_ent", "x_rel", "lg_miss", "lg_extra", "ly_ok", "ly_bad"), 0)
    evl = lambda d: "%s@%s" % tuple((d.get("evidence") or [{}])[0].get(k, "-") for k in ("source", "locator"))
    lab, aE = {}, {}
    for e in p["entities"]:
        lab[e["id"]] = nk(e["label"])
        for k in {nk(e["label"]), nk(e["id"])}:
            if k:
                aE.setdefault(k, e)
    re_, rr, used = [], [], set()
    for i, ge in enumerate(g["entities"], 1):
        a, ek, lhs = aE.get(nk(ge["label"])), (ge.get("kind_expected") or "unspecified").lower(), ge["label"]
        if a is None:
            c["e_miss"] += 1
            re_.append((i, lhs, ek, "缺失", "图面未出现", evl(ge)))
            continue
        used.add(id(a))
        ak = (a.get("kind") or "unspecified").lower()
        if ek != "unspecified" and ak != ek:
            c["e_kind"] += 1
            re_.append((i, lhs, ek, "偏差", "kind %s≠%s (%s)" % (ek, ak, a["id"]), evl(ge)))
            continue
        c["e_ok"] += 1
        if ek == "unspecified":
            c["e_soft"] += 1
            re_.append((i, lhs, ek, "达标(部分)", "仅核存在性 (%s)" % a["id"], evl(ge)))
        else:
            re_.append((i, lhs, ek, "达标", "id=%s" % a["id"], evl(ge)))
    for e in p["entities"]:
        if id(e) not in used:
            c["x_ent"] += 1
            ev = e.get("evidence") or {}
            re_.append(("-", e["label"], e.get("kind") or "?", "金标准外", "多画，需证据或删除",
                        ev.get("verified_locator") or ev.get("locator") or "无证据"))
    aR = [{"s": lab.get(r["source"], nk(r["source"])), "t": lab.get(r["target"], nk(r["target"])),
           "type": r["type"], "id": r["id"]} for r in p["relations"]]
    done = set()
    for i, gr in enumerate(g["relations"], 1):
        s0, t0, ty = nk(gr["source"]), nk(gr["target"]), (gr.get("type") or "unspecified").lower()
        e_ = next((x for x in aR if (x["s"], x["t"]) == (s0, t0)), None)
        if e_ and (ty == "unspecified" or e_["type"] == ty):
            c["r_ok"] += 1
            done.add(id(e_))
            rr.append((i, gr["direction"], ty, "达标", "rel %s type=%s" % (e_["id"], e_["type"]), evl(gr)))
            continue
        if e_:
            c["r_type"] += 1
            done.add(id(e_))
            rr.append((i, gr["direction"], ty, "偏差", "type %s≠%s (%s)" % (ty, e_["type"], e_["id"]), evl(gr)))
            continue
        r_ = next((x for x in aR if (x["s"], x["t"]) == (t0, s0)), None)
        if r_:
            c["r_dir"] += 1
            done.add(id(r_))
            rr.append((i, gr["direction"], ty, "偏差", "方向反转→%s→%s (%s)"
                       % (gr["target"], gr["source"], r_["id"]), evl(gr)))
        else:
            c["r_miss"] += 1
            rr.append((i, gr["direction"], ty, "缺失", "图面未出现", evl(gr)))
    for x in aR:
        if id(x) not in done:
            c["x_rel"] += 1
            rr.append(("-", "%s -> %s" % (x["s"], x["t"]), x["type"], "金标准外",
                       "多画 rel %s，需证据或删除" % x["id"], "-"))
    drawn = sorted({r["type"] for r in p["relations"]})
    leg = sorted({str(x.get("type")) for x in (cmap.get("legend") or []) if isinstance(x, dict) and x.get("type")})
    c["lg_miss"], c["lg_extra"] = len([t for t in drawn if t not in leg]), len([t for t in leg if t not in drawn])
    rows_l = [("图例", t, "达标" if t in leg else "缺失", "图面有/图例无" if t not in leg else "图例与图面一致")
              for t in drawn]
    rows_l += [("图例", t, "偏差", "图例有/图面无") for t in leg if t not in drawn]

    def stage(x):
        s = ("%s %s" % (x["id"], x["label"])).lower()
        return next((i for i, (_, pat) in enumerate(ORD) if re.search(pat, s)), None)

    seq, seen = [], set()
    for x in p["compartments"]:
        st_ = stage(x)
        if st_ is not None and (st_, x["label"]) not in seen:
            seen.add((st_, x["label"]))
            seq.append((st_, x["label"]))
    for a_, b_ in zip(seq, seq[1:]):
        ok = a_[0] < b_[0]
        c["ly_ok" if ok else "ly_bad"] += 1
        rows_l.append(("区室顺序", "%s>%s" % (a_[1], b_[1]), "达标" if ok else "偏差",
                       "上游在上" if ok else "与上游→下游相反"))
    for x in p["entities"]:
        if x["compartment"] == "unspecified":
            c["ly_bad"] += 1
            rows_l.append(("区室归位", x["label"], "偏差", "区室未声明"))
    if not seq and p["entities"]:
        rows_l.append(("区室顺序", "-", "待确认", "区室名无法映射到胞外/膜/胞质/核"))
    req, met = len(g["entities"]) + len(g["relations"]), c["e_ok"] + c["r_ok"]
    c["required_total"], c["required_met"] = req, met
    c["coverage_pct"] = round(100.0 * met / req, 1) if req else None
    c["deviations"] = sum(c[k] for k in ("e_miss", "e_kind", "r_miss", "r_type", "r_dir", "lg_miss",
                                         "lg_extra", "ly_bad"))
    verdict = ("不适用（金标准为空）" if not req else
               "达标" if not c["deviations"] else ("部分达标" if met else "未达标"))
    acts = ["实体 `%s`：%s —— %s" % (r[1], r[3], r[4]) for r in re_ if r[3] not in ("达标", "达标(部分)")]
    acts += ["关系 `%s`：%s —— %s" % (r[1], r[3], r[4]) for r in rr if r[3] != "达标"]
    acts += ["布局 `%s`：%s" % (r[1], r[3]) for r in rows_l if r[2] in ("偏差", "缺失")]
    H = "| # | 金标准项 | 期望 | 判定 | 说明 | 证据locator |\n|---|---|---|---|---|---|"
    md = "\n".join([
        "# 实际产物 vs 金标准：逐项对照", "",
        "case_id `%s` · 生成 %s · 金标准 %d 实体/%d 关系/%d 规则（证据 %d 条，未回查 %d）· 图面 区室%d/实体%d/关系%d"
        % ((g or {}).get("case_id") or "-", now(), len(g["entities"]), len(g["relations"]),
           g["counts"]["rules"], g["counts"]["evidence_items"], g["verification"]["unverified"],
           len(p["compartments"]), len(p["entities"]), len(p["relations"])),
        "判定：达标=存在且类型方向一致；偏差=kind/type/图例/区室顺序不符（方向反转点名）；"
        "缺失=金标准要而图面无；金标准外=图面多画；达标(部分)=仅核存在性。", "",
        "## 1 汇总", "",
        tbl(["项目", "计数"], [
            ("金标准 实体/关系", "%d / %d" % (len(g["entities"]), len(g["relations"]))),
            ("实体 达标/缺失/kind偏差/仅存在性", "%d / %d / %d / %d" % (c["e_ok"], c["e_miss"], c["e_kind"], c["e_soft"])),
            ("关系 达标/缺失/type偏差/方向反转/金标准外",
             "%d / %d / %d / %d / %d" % (c["r_ok"], c["r_miss"], c["r_type"], c["r_dir"], c["x_rel"])),
            ("图面多画实体", c["x_ent"]), ("图例 缺项/多项", "%d / %d" % (c["lg_miss"], c["lg_extra"])),
            ("布局规则 通过/未通过", "%d / %d" % (c["ly_ok"], c["ly_bad"])),
            ("金标准覆盖率", "%s%%（%d/%d）" % (c["coverage_pct"], met, req)),
            ("总体判定", "**%s**" % verdict)]), "",
        "## 2 实体逐项", "", (H + "\n" + tbl([], re_).split("\n", 2)[2]) if re_ else "（无）", "",
        "## 3 关系逐项（方向敏感）", "", (H + "\n" + tbl([], rr).split("\n", 2)[2]) if rr else "（无）", "",
        "## 4 图例与布局", "", tbl(["类别", "项", "判定", "说明"], rows_l) if rows_l else "（无）", "",
        "## 5 未达标项与人工动作", "",
        ("\n".join("- " + a for a in acts) if acts else "- 无：全部金标准项达标。"), "",
        "## 6 复核与局限", "",
        "重跑 `python3 -B scripts/main.py build --input /input --output /app/output --work /app/work` "
        "除首行时间戳外确定性复现；`len(content_map.entities)` 须等于 `figure.svg` 中 `id=\"ent-*\"` 个数。",
        "只对照有逐字证据的项目；「达标」只表示与可回查原文一致，不等于机制结论正确。", ""])
    return md, {"counts": c, "verdict": verdict, "rows": {"entities": len(re_), "relations": len(rr),
                                                          "rules": len(rows_l)}, "actions": acts[:20]}


VH_STATIC = """# 版本记录（v0 骨架 → v1 成稿 → v2 增补）

## v0 骨架（仅记录，无可运行包）
单脚本 + 说明：能读材料、能出 SVG，但无逐字引文校验、无 content_map、无区室语义。
`baseline_minimal.zip` 与 `baseline_v1.zip` 内容一致（md5 `c662b963766ef056b63799a363d094ea`），
故 v0 只记录于此；本次基线 = v1（69.67）。

## v1 成稿（= 提交基线包）
`init/show/check/build` 四步；`plan.json` 由 Agent 写、脚本只校验与渲染；quote 逐字回查
（rejected/declared/verified 分开计数）；区室横带布局；分层 SVG 与单页矢量 PDF 同遍生成；
`content_map.json` + `compliance_checks.json`；异常全捕获、退出码恒 0、先写 partial result.json。
为什么：生物学判断留在 Agent，可复核性交给确定性脚本。
回退：`unzip baseline_v1.zip -d /tmp/v1` 覆盖 `SKILL.md`、`scripts/*.py`、`references/*.md`。

## v2（本次，纯增补）
`build` 在原有产物之外生成 5 个可核验资产（golden_standard.json / diff_report.md / version_history.md /
self_check.json / run.log）；`result.json` 增加同名 4 字段，原 `output_contract` 字段全部保留；
新增可选子命令 `selftest`、可选参数 `--no-probe`。
为什么：rubric 的「可核验性/完整性/生态贡献」需要能被独立重算的中间件，而非自述。
不变：入口与调用方式、纯标准库、离线、不依赖 CWD、退出码恒 0、先写 partial、原主产物与证据字段。
回退（v2→v1）：删掉新增 5 个资产即可；v1 不读它们，4 个新字段为增量字段。

## 运行时记录（本次 build 追加）
"""


def vhist(case, g, dsum, plan, degr, uncer, status):
    lines = [VH_STATIC.rstrip(), "",
             "- 生成 %s　case_id `%s`　status `%s`" % (now(), (case or {}).get("case_id"), status),
             "- 金标准 %d 实体 / %d 关系 / %d 规则项；对照 %s（偏差 %d，缺失 %d，覆盖率 %s%%）"
             % (len(g["entities"]), len(g["relations"]), g["counts"]["rules"], dsum["verdict"],
                dsum["counts"]["deviations"], dsum["counts"]["e_miss"] + dsum["counts"]["r_miss"],
                dsum["counts"]["coverage_pct"])]
    edits = [e for e in (plan.get("edits") or []) if isinstance(e, dict)]
    for i, e in enumerate(edits[:10], 1):
        lines.append("- 图面修改 %d：`%s` %s → %s（原因：%s）"
                     % (i, e.get("element"), e.get("before"), e.get("after"), e.get("reason")))
    if not edits:
        lines.append("- 图面修改：无（plan.json 未声明 edits；图为一次性生成，未做源内编辑）")
    lines += ["- 降级：%s" % d for d in degr[:8]] + ["- 不确定：%s" % u for u in uncer[:8]]
    lines += ["", "回退本次运行：重跑 build 覆盖产物；本文只记真实发生的事。", ""]
    return "\n".join(lines)


def probes(work):
    """Real subprocess fallback runs: --help, empty input, bad JSON, minimal case. Exit codes are external."""
    base, res, mp = Path(work) / ".selfcheck", {}, str(HERE / "main.py")
    mini = json.dumps({"case_id": "SELFTEST-MINIMAL", "kind": "probe", "demo": True,
                       "output_contract": ["case_id", "status", "editable_source", "export_artifact",
                                           "content_map", "compliance_checks", "exceptions"],
                       "organizer_workorder": {
                           "required_elements": [{"label": "A", "kind": "protein"}, {"label": "B", "kind": "protein"}],
                           "required_relations": [{"source": "A", "target": "B", "type": "activation"}]}},
                      ensure_ascii=False)
    for name, payload in (("help", None), ("empty_input", None), ("bad_json", '{"case_id": "BAD", "output'),
                          ("minimal_case", mini)):
        d = base / name
        try:
            for x in ("input", "output", "work"):
                (d / x).mkdir(parents=True, exist_ok=True)
            if payload is not None:
                (d / "input" / "case.json").write_text(payload, encoding="utf-8")
            if name == "minimal_case":
                (d / "input" / "note.md").write_text("A activates B in the cytoplasm.\n", encoding="utf-8")
            args = [mp, "--help"] if name == "help" else [
                mp, "build", "--input", str(d / "input"), "--output", str(d / "output"),
                "--work", str(d / "work"), "--no-probe"]
            r = subprocess.run([sys.executable, "-B"] + args, capture_output=True, timeout=240)
            it = {"exit_code": r.returncode}
            if name == "help":
                it["usage_printed"] = b"usage" in r.stdout.lower()
            else:
                rj = json.loads((d / "output" / "result.json").read_text(encoding="utf-8"))
                dec = ((rj.get("contract_fields") or {}).get("declared") or [])
                it.update({"status": rj.get("status"), "result_json_legal": "case_id" in rj and "status" in rj,
                           "contract_missing": [n for n in dec if n not in rj],
                           "has_v2_fields": all(k in rj for k in ("golden_standard", "diff_report",
                                                                  "version_history", "self_check")),
                           "assets_n": len([x for x in (d / "output").glob("*") if x.is_file()])})
                it["usage_printed"] = True
            it["pass"] = (it["exit_code"] == 0 and it.get("usage_printed")
                          and (it.get("result_json_legal") and not it.get("contract_missing")
                               if name != "help" else True))
        except Exception as exc:
            it = {"exit_code": None, "pass": False, "error": "%s: %s" % (type(exc).__name__, exc)}
        res[name] = it
    return res


def self_check(a, out, work, case, corpus, rep, g, dsum, st, cmap, res, meta=None):
    """Contract completeness, evidence coverage, number trace, fallback probes, exit codes."""
    chk, fails = {}, []
    names = cnames(case)
    miss = [n for n in names if n not in res]
    chk["contract_fields"] = {"declared": names, "missing": miss, "not_applicable": not names,
                              "null_values": [n for n in names if res.get(n) is None],
                              "added": [k for k in ("golden_standard", "diff_report", "version_history",
                                                    "self_check") if k in res],
                              "pass": (not miss) if names else None}
    files = ("figure.svg", "figure.pdf", "content_map.json", "compliance_checks.json", "golden_standard.json",
             "diff_report.md", "version_history.md", "run.log", "self_check.json", "result.json")
    chk["assets"] = dict((f, {"exists": (out / f).is_file(),
                              "bytes": (out / f).stat().st_size if (out / f).is_file() else 0}) for f in files)
    chk["assets"]["pass"] = all(v["exists"] and v["bytes"] > 0 for f, v in chk["assets"].items()
                                if f not in ("pass", "self_check.json"))
    svg = (out / "figure.svg").read_text(encoding="utf-8") if (out / "figure.svg").is_file() else ""
    pdf = (out / "figure.pdf").read_bytes() if (out / "figure.pdf").is_file() else b""
    try:
        ET.fromstring(svg)
        ok = True
    except Exception as exc:
        ok, chk["svg_error"] = False, "%s: %s" % (type(exc).__name__, exc)
    ids = set(re.findall(r'id="([^"]+)"', svg))
    se, sr = sorted(i for i in ids if i.startswith("ent-")), sorted(i for i in ids if i.startswith("rel-"))
    me = sorted({r["svg_id"].lstrip("#") for r in cmap.get("entities") or [] if r.get("svg_id")})
    mr = sorted({r["svg_id"].lstrip("#") for r in cmap.get("relations") or [] if r.get("svg_id")})
    layers = sorted(i for i in ids if i.startswith("layer-"))
    chk["svg"] = {"xml_wellformed": ok, "bytes": len(svg.encode()), "text_nodes": svg.count("<text"),
                  "layer_groups": layers,
                  "pass": ok and svg.count("<text") > 0 and len(layers) >= 4}
    chk["map_1to1"] = {"entity_svg": len(se), "entity_map": len(me), "rel_svg": len(sr), "rel_map": len(mr),
                       "entity_only_svg": [x for x in se if x not in me],
                       "entity_only_map": [x for x in me if x not in se],
                       "relation_only_svg": [x for x in sr if x not in mr],
                       "relation_only_map": [x for x in mr if x not in sr],
                       "pass": se == me and sr == mr and len(se) == len(cmap.get("entities") or [])
                       and len(sr) == len(cmap.get("relations") or [])}
    ops = b""
    m = re.search(rb"stream\r?\n(.*?)\r?\nendstream", pdf, re.S)
    if m:
        try:
            ops = zlib.decompress(m.group(1))
        except Exception:
            ops = b""
    chk["pdf"] = {"header": pdf[:5].decode("latin-1"), "bytes": len(pdf),
                  "pages": pdf.count(b"/Type /Page") - pdf.count(b"/Type /Pages"),
                  "text_ops_Tj": ops.count(b"Tj"), "eof": pdf.rstrip().endswith(b"%%EOF"),
                  "pass": pdf[:5] == b"%PDF-" and pdf.rstrip().endswith(b"%%EOF") and ops.count(b"Tj") > 0}
    cnt = rep.get("counts") or {}
    tot = (cnt.get("entities") or 0) + (cnt.get("relations") or 0)
    ver = (cnt.get("entities_verified") or 0) + (cnt.get("relations_verified") or 0)
    chk["evidence"] = {"entities": cnt.get("entities"), "relations": cnt.get("relations"),
                       "quotes_verified": ver, "quotes_rejected": cnt.get("rejected_quotes"),
                       "declared_only": (cnt.get("entities_declared") or 0) + (cnt.get("relations_declared") or 0),
                       "coverage_pct": round(100.0 * ver / tot, 1) if tot else 0.0,
                       "golden_items": len(g["entities"]) + len(g["relations"]),
                       "golden_quotes_unverified": g["verification"]["unverified"],
                       "pass": (cnt.get("rejected_quotes") or 0) == 0 and g["verification"]["unverified"] == 0}
    src = " ".join([b["text"] for b in corpus])
    try:
        src += " " + json.dumps(case, ensure_ascii=False)
    except Exception:
        pass
    kn = set(re.findall(r"\d+(?:\.\d+)?", src))
    meta_nums = set(re.findall(r"\d+(?:\.\d+)?", " ".join(str(v) for v in (meta or {}).values())))
    nums = sorted(set(re.findall(r"\d+(?:\.\d+)?", " ".join(re.findall(r"<text[^>]*>([^<]*)</text>", svg)))))
    chk["numeric_trace"] = {"numbers_in_figure": nums,
                            "from_source": [n for n in nums if n in kn],
                            "skill_metadata": sorted(n for n in nums if n not in kn and n in meta_nums),
                            "without_source": [n for n in nums if n not in kn and n not in meta_nums],
                            "rule": "图面文字数值必须能在材料/case.json 找到；仅 footer/来源行等技能元数据数字例外",
                            "pass": all(n in kn or n in meta_nums for n in nums)}
    chk["consistency"] = {"content_map_entities": len(cmap.get("entities") or []), "rendered_entities": st["entities"],
                          "content_map_relations": len(cmap.get("relations") or []), "rendered_relations": st["relations"],
                          "golden_total": dsum["counts"]["required_total"], "golden_met": dsum["counts"]["required_met"],
                          "pass": len(cmap.get("entities") or []) == st["entities"]
                          and len(cmap.get("relations") or []) == st["relations"]}
    chk["fallback"] = {} if getattr(a, "no_probe", False) else probes(work)
    chk["exit_codes"] = {"this_run": 0, "help": (chk["fallback"].get("help") or {}).get("exit_code", "skipped")}
    for k in ("contract_fields", "assets", "svg", "map_1to1", "pdf", "evidence", "numeric_trace", "consistency"):
        if chk[k].get("pass") is None:
            chk[k]["skipped"] = "no output_contract declared in input: nothing to backfill"
        elif not chk[k].get("pass"):
            fails.append(k)
    fails += ["fallback:" + k for k, v in chk["fallback"].items() if not v.get("pass")]
    chk["verdict"] = {"exit_code": 0, "failures": fails, "all_pass": not fails,
                      "note": "all_pass=false 表示有可复现缺口、不是崩溃；缺口逐条见 failures 与各段。"}
    chk["limits"] = ["无位图预览（stdlib 无文字光栅器），figure.pdf 作检视件；探针不覆盖 harness 进程级故障。"]
    return chk


def srcs(mats):
    return [dict((k, m[k]) for k in ("rel", "kind", "blocks", "note", "bytes")) for m in mats]

def cmd_init(a):
    t0, out, work = time.time(), Path(a.output), Path(a.work)
    out.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    case = get_case(a.input)
    mats, corpus = collect(a.input)
    jwrite(work / "materials.json", {"generated": now(), "materials": mats, "corpus_blocks": len(corpus)})
    jwrite(work / "plan.skeleton.json", {
        "title": "", "subtitle": "",
        "compartments": [{"id": "extracellular", "label": "Extracellular", "order": 0},
                         {"id": "membrane", "label": "Plasma membrane", "order": 1},
                         {"id": "cytoplasm", "label": "Cytoplasm", "order": 2},
                         {"id": "nucleus", "label": "Nucleus", "order": 3}],
        "entities": [], "relations": [], "legend_extra": [], "gaps": []})
    finalise(out, case, "input_error" if case is None else "partial",
             {"case_id": (case or {}).get("case_id"), "sources": srcs(mats),
              "uncertainty": ["no plan.json yet, figure not rendered"],
              "pending_human": ["read the materials, write plan.json, then run build"],
              "errors": [] if case is not None else ["case.json not found or unparsable under %s" % a.input],
              "runtime": {"stage": "init", "seconds": round(time.time() - t0, 2), "python": platform.python_version()}})
    print("materials %d | contract: %s" % (len(mats), ", ".join(cnames(case)) or "none declared"))
    for m in mats:
        print("  %-38s %-5s %7dB blocks=%d %s%s" % (m["rel"][:38], m["kind"], m["bytes"], m["blocks"],
                                                    m["locators"][0] if m["locators"] else "-",
                                                    ("  NOTE: " + m["note"]) if m["note"] else ""))
    print("next: show --doc <material> -> write %s -> check -> build" % (work / "plan.json"))
    log(work, out, "INFO", "init materials=%d corpus_blocks=%d contract=%s"
        % (len(mats), len(corpus), ",".join(cnames(case)) or "none"))
    return 0

def cmd_show(a):
    md = jread(Path(a.work) / "materials.json") or jread(Path(a.output) / "materials.json") or {}
    mats = md.get("materials") or []
    sel = [m for m in mats if not a.doc or a.doc.lower() in m["rel"].lower()]
    if not sel:
        print("no material matched %r; available: %s" % (a.doc, [m["rel"] for m in mats]))
        return 0
    for m in sel:
        blocks, note = blocks_of(Path(m["path"]))
        print("### %s (%s, %d blocks)%s" % (m["rel"], m["kind"], len(blocks), " - " + note if note else ""))
        shown = 0
        for loc, t in blocks:
            if not a.locator or a.locator in loc:
                print("\n[%s]\n%s" % (loc, t[:1400]))
                shown += 1
        if a.locator and not shown:
            print("locator %r not in this material" % a.locator)
    return 0

def cmd_check(a):
    case = get_case(a.input)
    _, corpus = collect(a.input)
    plan, src, err = load_plan(a.work, a.output)
    if plan is None:
        jwrite(Path(a.work) / "check_report.json", {"ok": False, "error": err})
        print("no usable plan (%s)" % err)
        return 0
    rep = validate(plan, corpus, case)
    rep["plan_file"] = src
    jwrite(Path(a.work) / "check_report.json", rep)
    print(("entities %(entities)d (quotes verified %(entities_verified)d) | relations %(relations)d "
           "(verified %(relations_verified)d) | rejected %(rejected_quotes)d") % rep["counts"])
    print("workorder gaps: elements=%s relations=%s" % (rep["missing_required_elements"] or "none",
                                                       rep["missing_required_relations"] or "none"))
    for i in rep["issues"][:12]:
        print("  ISSUE  %s" % i)
    for r in rep["rejected"][:8]:
        print("  REJECT %s %s: quote not verbatim in material -> %r" % (r["kind"], r["id"], r["quote"]))
    print("CLEAN" if rep["ok"] else "NOT CLEAN - fix, or keep the gap explicit so build reports pending_human")
    log(a.work, a.output, "INFO" if rep["ok"] else "WARN",
        "check clean=%s rejected=%d issues=%d missing_elements=%d missing_relations=%d"
        % (rep["ok"], rep["counts"]["rejected_quotes"], len(rep["issues"]),
           rep["counts"]["required_elements_missing"], rep["counts"]["required_relations_missing"]))
    return 0

def cmd_build(a):
    t0, out, work = time.time(), Path(a.output), Path(a.work)
    out.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    log(work, out, "INFO", "build start argv=%s" % " ".join(sys.argv[1:]))
    case = get_case(a.input)
    cp = find_case(a.input)
    if case is None and cp is not None:
        errs0 = ["case.json not parsable at %s; continued with material-only fallback" % cp]
    else:
        errs0 = []
    finalise(out, case, "partial", {"case_id": (case or {}).get("case_id"),
                                    "pending_human": ["build in progress; result.json is overwritten on completion"],
                                    "runtime": {"stage": "build", "phase": "partial-first-write"}})
    log(work, out, "INFO", "partial result.json written before render")
    mats, corpus = collect(a.input)
    log(work, out, "INFO", "indexed materials=%d corpus_blocks=%d" % (len(mats), len(corpus)))
    errs, degr, uncer, pend = list(errs0), [], [], []
    plan, src, err = load_plan(work, out)
    if plan is None:
        plan, status = fallback_plan(case, mats, corpus), "partial"
        degr.append("plan.json unusable (%s): deterministic fallback rendered from input strings" % err)
        pend.append("read the materials, replace the fallback with plan.json, rebuild")
        log(work, out, "WARN", "plan.json unusable (%s); fallback plan used" % err)
    else:
        status = "ok"
        log(work, out, "INFO", "plan loaded from %s" % src)
    rep = validate(plan, corpus, case)
    log(work, out, "INFO", "validate entities=%d relations=%d verified=%d rejected=%d"
        % (rep["counts"]["entities"], rep["counts"]["relations"],
           rep["counts"]["entities_verified"] + rep["counts"]["relations_verified"],
           rep["counts"]["rejected_quotes"]))
    if rep["rejected"]:
        status = "partial"
        uncer += ["evidence quote not verbatim: %s %s -> %r" % (r["kind"], r["id"], r["quote"])
                  for r in rep["rejected"][:15]]
        degr.append("%d quotes could not be re-located; drawn but flagged unverified" % len(rep["rejected"]))
    if rep["missing_required_elements"] or rep["missing_required_relations"]:
        status = "partial"
        pend.append("workorder items still missing: elements=%s relations=%s"
                    % (rep["missing_required_elements"], rep["missing_required_relations"]))
    values = {"case_id": (case or {}).get("case_id"), "counts": rep["counts"], "sources": srcs(mats),
              "uncertainty": uncer + list(plan.get("gaps") or [])[:6],
              "pending_human": pend, "errors": errs, "degradations": degr,
              "changes": plan.get("edits") or []}
    if RD is None:
        finalise(out, case, "input_error", dict(values, errors=["renderer import failed; no figure produced"]))
        log(work, out, "ERROR", "renderer import failed; result.json finalised, no figure")
        print("renderer unavailable")
        return 0
    meta = {"title": plan.get("title") or "Biological mechanism figure",
            "sources_line": "sources: " + ", ".join(
                "%s (%d block%s)" % (m["rel"], m["blocks"], "" if m["blocks"] == 1 else "s") for m in mats[:6]),
            "footer": "graphics-03 skill v2 | figure.svg is the editable source; figure.pdf is the export"}
    try:
        st = RD.render_all(plan, meta)
    except Exception as exc:
        errs.append("render failed: %s: %s" % (type(exc).__name__, exc))
        log(work, out, "ERROR", "render failed: %s" % errs[-1])
        finalise(out, case, "input_error", dict(values, errors=errs, degradations=degr +
                                                ["no figure written; result.json finalised anyway"]))
        print(errs[0])
        return 0

    svg_p, pdf_p = out / "figure.svg", out / "figure.pdf"
    svg_p.write_text(st["svg"], encoding="utf-8")
    pdf_p.write_bytes(st["pdf"])
    p = st["plan"]
    log(work, out, "INFO", "rendered figure.svg=%dB figure.pdf=%dB entities=%d relations=%d types=%s"
        % (len(st["svg"].encode("utf-8")), len(st["pdf"]), st["entities"], st["relations"],
           ",".join(st["types"]) or "-"))

    def rec(x, ent):
        ev = x.get("evidence") or {}
        q = ev.get("quote") if isinstance(ev, dict) else None
        r = {"id": x["id"], "svg_id": "#%s-%s" % ("ent" if ent else "rel", RD.sid(x["id"])), "quote": q,
             "quote_verified": bool(q and hit(corpus, q)),
             "source_locator": ev.get("verified_locator") or ev.get("locator")}
        r.update({"label": x["label"], "kind": x["kind"], "compartment": x["compartment"]} if ent else
                 {"source": x["source"], "target": x["target"], "type": x["type"], "label": x["label"]})
        return r

    cmap = {"figure": {"file": "figure.svg", "width": st["width"], "height": st["height"],
                       "xml_ids": "layer-*, comp-<compartment>, ent-<entity>, rel-<relation>"},
            "entities": [rec(e, True) for e in p["entities"]],
            "relations": [rec(r, False) for r in p["relations"]],
            "legend": [{"type": t, "encoding": RD.HEAD[t]} for t in st["types"]],
            "encoding_notes": ["node fill encodes entity kind only",
                               "edge colour + head shape encode relation type",
                               "no quantitative encoding unless plan.data_encoding supplies values"],
            "gaps": p["gaps"]}
    jwrite(out / "content_map.json", cmap)
    jwrite(out / "plan.normalized.json", p)

    s, pdf = st["svg"], st["pdf"]
    checks = {"editable_source": {"file": "figure.svg", "bytes": len(s.encode("utf-8")),
                                  "text_elements": s.count("<text"), "layer_groups": s.count('id="layer-'),
                                  "font_family": "DejaVu Sans, Helvetica, Arial, sans-serif",
                                  "pass": s.count("<text") > 0 and s.count('id="layer-') >= 4},
              "pdf": {"file": "figure.pdf", "bytes": len(pdf), "header": pdf[:5].decode("latin-1"),
                      "page_objects": pdf.count(b"/Type /Page") - pdf.count(b"/Type /Pages"),
                      "eof_ok": pdf.rstrip().endswith(b"%%EOF"),
                      "chars_dropped_for_winansi": st["pdf_chars_lost"],
                      "pass": pdf[:5] == b"%PDF-" and pdf.rstrip().endswith(b"%%EOF")},
              "raster_preview": {"file": None, "reason": "stdlib has no bitmap text rasteriser; figure.pdf is "
                                 "the inspection preview"},
              "semantics": {"entities": st["entities"], "relations": st["relations"],
                            "compartment_bands": st["bands"], "relation_types_drawn": st["types"],
                            "unplaced_entities": st["unplaced"],
                            "pass": not st["unplaced"]},
              "evidence": rep["counts"],
              "layout": {"canvas_px": [st["width"], st["height"]], "margin_px": 32}}
    checks["verdict"] = {"svg_editable": checks["editable_source"]["pass"], "pdf_real": checks["pdf"]["pass"],
                         "map_complete": len(cmap["entities"]) == st["entities"],
                         "all_pass": checks["editable_source"]["pass"] and checks["pdf"]["pass"]
                         and len(cmap["entities"]) == st["entities"]}
    jwrite(out / "compliance_checks.json", checks)

    if not p["entities"]:
        status = "insufficient_evidence"
    degr.append("no PNG preview (stdlib renderer); figure.pdf supplied for inspection")

    # ---- v2 verification assets: golden standard -> diff -> history -> self check ----
    g = gstd(case, cp, corpus)
    (out / "golden_standard.json").write_text(
        json.dumps(g, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    dmd, dsum = diff_rep(g, p, cmap)
    (out / "diff_report.md").write_text(dmd, encoding="utf-8")
    dc = dsum["counts"]
    log(work, out, "INFO", "golden entities=%d relations=%d rules=%d quotes=%d/%d"
        % (len(g["entities"]), len(g["relations"]), g["counts"]["rules"], g["verification"]["verified"],
           g["counts"]["evidence_items"]))
    log(work, out, "INFO", "diff verdict=%s deviations=%d missing=%d coverage=%s%%"
        % (dsum["verdict"], dc["deviations"], dc["e_miss"] + dc["r_miss"], dc["coverage_pct"]))
    if status == "ok" and (dc["deviations"] or dc["e_soft"]):
        status = "partial"
        pend.append("diff_report: golden-standard deviations present; see diff_report.md section 5")
        uncer.append("figure vs golden standard: %s (%s%% coverage)" % (dsum["verdict"], dc["coverage_pct"]))
    (out / "version_history.md").write_text(vhist(case, g, dsum, p, degr, uncer, status), encoding="utf-8")
    jwrite(out / "self_check.json", {"status": "running", "note": "rewritten at the end of build"})
    values.update({
        "editable_source": {"file": str(svg_p), "format": "SVG, layered, editable <text> labels",
                            "width_px": st["width"], "height_px": st["height"]},
        "export_artifact": {"pdf": str(pdf_p), "png": None, "pdf_pages": 1},
        "content_map": {"file": str(out / "content_map.json"),
                        "entries": len(cmap["entities"]) + len(cmap["relations"])},
        "compliance_checks": {"file": str(out / "compliance_checks.json"), "summary": checks["verdict"]},
        "exceptions": [{"kind": "degradation", "detail": d} for d in degr] +
                      [{"kind": "pending_human", "detail": q} for q in pend],
        "golden_standard": {"file": str(out / "golden_standard.json"), "items": g["counts"],
                            "quotes_verified": g["verification"]["verified"],
                            "quotes_unverified": g["verification"]["unverified"],
                            "provenance_note": g["provenance_note"]},
        "diff_report": {"file": str(out / "diff_report.md"), "verdict": dsum["verdict"],
                        "counts": dc, "actions": dsum["actions"][:8]},
        "version_history": {"file": str(out / "version_history.md"), "current": "v2",
                            "entries": ["v0 skeleton (record only)", "v1 = supplied baseline_v1",
                                        "v2 verification assets (this run)"]},
        "self_check": {"status": "running"},
        "runtime": {"stage": "build", "seconds": round(time.time() - t0, 2),
                    "python": platform.python_version(), "plan_source": src or "fallback",
                    "renderer": "scripts/render.py", "argv": sys.argv[1:]}})
    values["pending_human"], values["degradations"] = pend, degr
    values["uncertainty"] = uncer + list(plan.get("gaps") or [])[:6]
    res = finalise(out, case, status, values)
    sc = self_check(a, out, work, case, corpus, rep, g, dsum, st, cmap, res, meta)
    (out / "self_check.json").write_text(json.dumps(sc, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    res["self_check"] = {"file": str(out / "self_check.json"), "verdict": sc["verdict"],
                         "coverage_pct": sc["evidence"]["coverage_pct"],
                         "exit_codes": sc["exit_codes"],
                         "fallback": dict((k, dict((x, v.get(x)) for x in
                                                   ("exit_code", "result_json_legal", "status")))
                                          for k, v in (sc["fallback"] or {}).items()),
                         "checks": dict((k, (sc.get(k) or {}).get("pass")) for k in
                                        ("contract_fields", "assets", "svg", "map_1to1", "pdf",
                                         "evidence", "numeric_trace", "consistency"))}
    jwrite(out / "result.json", res)
    log(work, out, "INFO", "self_check all_pass=%s failures=%s"
        % (sc["verdict"]["all_pass"], sc["verdict"]["failures"] or "none"))
    log(work, out, "DONE", "build %.2fs status=%s assets=%d"
        % (time.time() - t0, status,
           len([f for f in ("figure.svg", "figure.pdf", "content_map.json", "golden_standard.json",
                            "diff_report.md", "version_history.md", "self_check.json", "run.log",
                            "result.json") if (out / f).is_file()])))
    print("status=%s entities=%d relations=%d types=%s"
          % (status, st["entities"], st["relations"], ",".join(st["types"])))
    print("figure.svg %dB | figure.pdf %dB | golden %dB | diff %s (coverage %s%%) | self_check %s"
          % (len(s.encode("utf-8")), len(pdf), (out / "golden_standard.json").stat().st_size,
             dsum["verdict"], "-" if dc["coverage_pct"] is None else dc["coverage_pct"],
             sc["verdict"]["all_pass"]))
    return 0


def cmd_selftest(a):
    """Exit-code evidence for --help / minimal / empty / bad-JSON probes."""
    t0, out, work = time.time(), Path(a.output), Path(a.work)
    for d in (out, work):
        d.mkdir(parents=True, exist_ok=True)
    pr = probes(work)
    res = {"generated": now(), "python": platform.python_version(), "stage": "selftest", "probes": pr,
           "verdict": {"failures": [k for k, v in pr.items() if not v.get("pass")],
                       "all_pass": not [k for k, v in pr.items() if not v.get("pass")],
                       "seconds": round(time.time() - t0, 2)}}
    (out / "self_check.json").write_text(json.dumps(res, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    log(work, out, "INFO", "selftest probes=%d failures=%s"
        % (len(pr), res["verdict"]["failures"] or "none"))
    for k, v in pr.items():
        print("%-13s exit=%s legal_result=%s status=%s assets=%d"
              % (k, v.get("exit_code"), v.get("result_json_legal"), v.get("status"),
                 len(v.get("assets") or [])))
    print("SELFTEST", "PASS" if res["verdict"]["all_pass"] else "FAIL")
    return 0


def main():
    ap = argparse.ArgumentParser(
        prog="graphics-03 mechanism figure skill",
        description="Biological mechanism / pathway figure builder: init -> Agent writes plan.json -> check -> "
                    "build. Always exits 0 and always leaves a legal result.json behind.")
    ap.add_argument("--input", default="/input", help="input directory (default /input)")
    ap.add_argument("--output", default="/app/output", help="artefact directory (default /app/output)")
    ap.add_argument("--work", default="/app/work", help="working directory (default /app/work)")
    sub = ap.add_subparsers(dest="cmd")
    for nm, hlp in (("init", "index material, write partial result.json"),
                    ("show", "print source text with locators"),
                    ("check", "verify plan.json quotes and workorder coverage"),
                    ("build", "render figure + content_map + checks + v2 assets + result.json"),
                    ("selftest", "exit-code + fallback probes")):
        sp = sub.add_parser(nm, help=hlp)
        sp.add_argument("--input", default="/input")
        sp.add_argument("--output", default="/app/output")
        sp.add_argument("--work", default="/app/work")
        sp.set_defaults(no_probe=False)
        if nm == "show":
            sp.add_argument("--doc", default="", help="material name substring")
            sp.add_argument("--locator", default="", help="e.g. para3 or stream2")
        if nm == "build":
            sp.add_argument("--no-probe", action="store_true", help="skip the in-process fallback probes")
    a = ap.parse_args()
    if not a.cmd:
        ap.print_help()
        return 0
    for p in (a.output, a.work):
        Path(p).mkdir(parents=True, exist_ok=True)
    try:
        return {"init": cmd_init, "show": cmd_show, "check": cmd_check, "build": cmd_build,
                "selftest": cmd_selftest}[a.cmd](a)
    except SystemExit:
        return 0
    except Exception as exc:
        tb = traceback.format_exc()
        try:
            case = jread(find_case(a.input)) if a.input else None
            finalise(a.output, case, "input_error",
                     {"case_id": (case or {}).get("case_id"),
                      "errors": ["%s: %s" % (type(exc).__name__, exc)],
                      "degradations": ["unhandled exception; partial result emitted"],
                      "runtime": {"stage": a.cmd, "traceback_tail": tb.strip().splitlines()[-3:]}})
        except Exception:
            pass
        print("recovered from %s: %s" % (type(exc).__name__, exc))
        return 0

if __name__ == "__main__":
    sys.exit(main())
