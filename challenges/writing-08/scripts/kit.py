#!/usr/bin/env python3
"""kit: vocabulary, extraction, composition, contract fill and checks (stdlib only)."""
import json, re
from pathlib import Path

V = "1.8.0"
VOCP = Path(__file__).resolve().parent.parent / "references" / "vocab.json"
try:
    VOC = json.loads(VOCP.read_text(encoding="utf-8"))
except Exception as _e:
    VOC = {"error": "%s: %s" % (type(_e).__name__, _e), "spec": [], "qf": {}, "lb": {}, "t": {}, "fm": {}}

def nm(s):
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]", "", str(s).lower())

CN, EL = {}, {}
for _l in VOC.get("spec", []):
    try:
        _a, _e, _al = _l.split("|")
    except ValueError:
        continue
    EL[_a] = _e
    for _x in _al.split(","):
        CN[nm(_x)] = _a
P = {"p": "parameters", "s": "setup", "d": "datasets", "c": "controls", "r": "repro"}
NUMK = set(VOC.get("numkeys") or [])
SPACEY = set(VOC.get("spacey") or [])
QF = VOC.get("qf") or {}
LB = VOC.get("lb") or {}
T = VOC.get("t") or {}
ELEMENTS = ["procedure", "setup", "parameters", "datasets", "controls", "repro"]
FM = {}
for _f, _al in (VOC.get("fm") or {}).items():
    for _x in _al:
        FM[nm(_x)] = _f

def canon(k):
    """Raw key -> (canonical, scope); scope comes only from dotted prefixes."""
    k = str(k).strip()
    if "." in k:
        pr, ls = k.rsplit(".", 1)
        a = CN.get(nm(ls))
        if a:
            return a, pr
    a = CN.get(nm(k))
    if a:
        return a, "global"
    for x in re.split(r"[_\-/]", k)[::-1]:
        a = CN.get(nm(x))
        if a:
            return a, "global"
    return None, "global"

N = r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?"
UN = r"%|ms|GB|MB|KB|min|h|s|x"
KV = re.compile(r"(?<![\w.])([A-Za-z][\w.]{0,40}|[\u4e00-\u9fff]{2,10})\s*[:=：]\s*([^\s,;，；|#\]\}]{1,80})([^\n|#;]{0,80})")
CJK = re.compile(r"(学习率|批大小|训练轮数|随机种子|权重衰减)\s*(?:为|是|设为|设置为)\s*(" + N + ")")
EPO = re.compile(r"epoch\s*[\[\( ]?(\d+)\s*/\s*(\d+)", re.I)
MET = re.compile(r"(?<![\w.])([A-Za-z_]*(?:acc|f1|bleu|rouge|psnr|ssim|auc|precision|recall|map|loss|perplexity|wer)[A-Za-z_@0-9]*)\s*[:=]\s*(" + N + ")", re.I)
CMD = re.compile(r"^\s*(?:CUDA_VISIBLE_DEVICES=\S+\s+)?(python3?|bash|sh|torchrun|accelerate|deepspeed|nohup|sbatch)\b")
SEED = re.compile(r"(?:manual_seed|set_seed|seed_everything|SEED|seed)\s*[\(=]\s*(\d{1,10})")
PIN = re.compile(r"((?:torch|tensorflow|jax|numpy|transformers|datasets|scikit-learn|scipy|cuda|python)\s*[=><~]{1,2}\s*\d[\w.\-]*)", re.I)
BASE = re.compile(r"(?i)\bbaselines?\b\s*[:=]?\s*([A-Za-z][\w\-.]{0,30})")
STEP = re.compile(r"^\s*(?:step\s*\d|阶段\s*\d|步骤\s*\d|\d{1,2}[.、)]\s+\S|[-*]\s*(?:首先|然后|接着|最后|first|then|next|finally))", re.I)
DEFL = re.compile(r"^\s*(?:async\s+)?def\s+([a-zA-Z_]\w{2,40})\s*\(")
LIM = re.compile(r"(limitation|局限|限制|仅|only|restricted|未能|不适用|caveat)", re.I)
DNAME = re.compile(r"(method|draft|manuscript|paper|section|稿件|方法|论文)", re.I)
DPAR = re.compile(r"(learning rate|learning_rate|学习率|batch size|batch_size|批大小|epochs?|训练轮数|weight decay|weight_decay|dropout|seed|随机种子)\s*(?:of|为|是|设为|设置为|=|:|：)?\s*(" + N + ")", re.I)
PARAMS = ("lr", "batch", "epochs", "wd", "dropout", "optim", "sched", "warmup", "hidden", "maxlen",
          "layers", "momentum", "accum")
BUD = ("材料未记录各对照是否同预算运行，本节不作同预算表述〔%s〕。",
       "Materials do not record whether controls shared budget; no same-budget claim is made [%s].")
LIMG = ("材料未记录 %s（%s），该环节无法复核，可复现范围受限。",
        "The materials omit %s (%s); that part cannot be re-checked.")
LIMN = ("材料未提供可界定失效场景的记录，需作者补充。",
        "No record supports a specific failure scenario; author to supply.")

def num(v):
    m = re.match(N, str(v).strip())
    try:
        return float(m.group(0)) if m else None
    except Exception:
        return None

def add(fs, seen, m, c, val, loc, q, via, e=None, name=None):
    k = (c, str(val))
    if k in seen or len(fs) >= 400:
        return
    seen.add(k)
    u = re.search(r"(" + UN + r")$", str(val).strip())
    fs.append({"element": e or P.get(EL.get(c, ""), "setup"), "canon": c, "name": name or c,
               "value": str(val)[:120], "num": num(val), "unit": u.group(1) if u else "",
               "source": m["id"], "loc": loc, "quote": q[:300], "via": via})

def ex(m, fs, seen):
    """Extract evidence-backed facts from one parsed material."""
    for s in m["segments"]:
        t, loc = s["text"], s["loc"]
        for k, v, rest in KV.findall(t):
            c, ob = canon(k)
            if not c:
                continue
            if c in SPACEY and rest.strip() and not re.match(r"[A-Za-z_][\w.\-]{0,20}\s*[:=]", rest.strip()):
                v = (v + rest).strip(" .;")
            if c in NUMK and num(v) is None:
                continue
            add(fs, seen, m, c, v[:120], loc, t, "kv", None, (ob + "." + c) if ob != "global" else None)
        for g in CJK.findall(t):
            c, _ = canon(g[0])
            if c:
                add(fs, seen, m, c, g[1], loc, t, "prose")
        for g in MET.findall(t):
            add(fs, seen, m, nm(g[0]), g[1], loc, t, "metric", "controls", g[0])
        if CMD.search(t):
            add(fs, seen, m, "command", t[:160], loc, t, "command", "repro")
        for g in PIN.findall(t):
            add(fs, seen, m, "pkg", g, loc, t, "version", "setup")
        for g in SEED.findall(t):
            add(fs, seen, m, "seed", g, loc, t, "seed", "repro")
        for g in BASE.findall(t):
            if len(g) > 2 and (any(c.isdigit() for c in g) or g.isupper()) and g.lower() not in ("same", "budget"):
                add(fs, seen, m, "baseline", g, loc, t, "baseline-prose", "controls")
        g = EPO.search(t)
        if g:
            add(fs, seen, m, "epochs", g.group(2), loc, t, "progress", "parameters")
        if LIM.search(t) and len(t) > 40 and m["kind"] in ("md", "docx", "pdf"):
            add(fs, seen, m, "limit", t[:200], loc, t, "limit-sentence", "limits")

def steps_of(ms):
    st = []
    for m in ms:
        if m["kind"] in ("image", "zip", "csv", "xlsx"):
            continue
        for s in m["segments"]:
            t = s["text"].strip()
            if STEP.match(t) and 6 < len(t) < 300:
                st.append({"text": re.sub(r"^\s*(?:step\s*\d+|\d{1,2}[.、)])\s*", "", t, flags=re.I)[:200],
                           "source": m["id"], "loc": s["loc"], "via": "marker"})
        if len(st) >= 12:
            break
    if not st:
        for m in ms:
            if m["kind"] == "code":
                for s in m["segments"]:
                    g = DEFL.match(s["text"])
                    if g and g.group(1) != "main" and not g.group(1).startswith("_"):
                        st.append({"text": g.group(1), "source": m["id"], "loc": s["loc"], "via": "code-order"})
                if st:
                    break
    return st[:12]

def draft_of(ms):
    for m in ms:
        if m["kind"] in ("md", "docx", "pdf") and DNAME.search(m["name"]) and \
                len(" ".join(s["text"] for s in m["segments"])) > 60:
            return m
    return None

def reconcile(dr, fs):
    """Numeric conflicts between an author draft and config/log values."""
    if not dr:
        return []
    out, cfg = [], {}
    for f in fs:
        if f["element"] in ("parameters", "datasets") and f["num"] is not None:
            cfg.setdefault(f["canon"], []).append(f)
    for s in dr["segments"]:
        for g in DPAR.finditer(s["text"]):
            c, _ = canon(g[1])
            dv = num(g[2])
            if not c or dv is None or not cfg.get(c) or any(f["num"] == dv for f in cfg[c]):
                continue
            src = cfg[c][0]
            out.append({"canon": c, "element": src["element"], "draft_value": g[2], "draft_quote": s["text"][:200],
                        "draft_loc": "%s#%s" % (dr["id"], s["loc"]), "source_value": src["value"],
                        "source": src["source"], "source_loc": "%s#%s" % (src["source"], src["loc"])})
    return out[:20]

def lab(c, lg):
    v = LB.get(c)
    return v[0 if lg == "zh" else 1] if v else c

CHK = [("lr", "parameters"), ("batch", "parameters"), ("epochs", "parameters"), ("hardware", "setup"),
       ("framework", "setup"), ("seed", "repro"), ("repeats", "repro"), ("dataset", "datasets"),
       ("split", "datasets"), ("preprocess", "datasets"), ("baseline", "controls"), ("metric", "controls"),
       ("budget", "controls"), ("command", "repro"), ("commit", "repro"), ("version", "repro")]

def gaps_of(lg, fs, st, cf):
    zh = lg == "zh"
    have = {f["canon"] for f in fs}
    if any(f["canon"] == "pkg" for f in fs):
        have.add("framework")
    if any(f["via"] == "metric" for f in fs):
        have.add("metric")
    g, pend, n = {}, [], 0

    def mk(key, elem, blocking):
        nonlocal n
        n += 1
        q = QF.get(key, [key, key])
        g[key] = "Q%d" % n
        pend.append({"id": "Q%d" % n, "element": elem, "item": key, "question": q[0 if zh else 1],
                     "basis": "材料未出现" if zh else "absent from materials", "blocking": blocking,
                     "action": "作者从代码/配置补充" if zh else "author to supply from code/config"})

    for c, e in CHK:
        if c not in have:
            mk(c, e, c in ("dataset", "split", "lr", "batch", "epochs"))
    if not st:
        mk("steps", "procedure", True)
    if not any(f["element"] == "limits" for f in fs):
        mk("limit", "repro", False)
    for j, c in enumerate(cf, 1):
        q = ("%s 在草稿中为 %s，在 %s 中为 %s，应以哪个为准？" % (c["canon"], c["draft_value"], c["source"], c["source_value"])
             if zh else "%s is %s in the draft but %s in %s; which is authoritative?"
             % (c["canon"], c["draft_value"], c["source_value"], c["source"]))
        pend.append({"id": "C%d" % j, "element": c["element"], "item": c["canon"], "question": q,
                     "basis": c["source_loc"], "blocking": True,
                     "action": "作者裁决并统一" if zh else "author to adjudicate"})
    return g, pend

def compose(lg, fs, st, g, cf, eid, nmat):
    """Render the section from the vocab.json template (tpl) plus filled slots."""
    t = T.get(lg) or T.get("en") or {}
    if "tpl" not in t:
        return "# Methods and Experimental Setup\n\n- vocabulary resource missing (references/vocab.json)\n"
    zh = lg == "zh"
    it = lambda xs: "[E%s]" % ",".join(str(eid[id(x)]) for x in xs)

    def item(x, bare=False):
        if bare:
            return "- %s = %s%s" % (x["name"], x["value"], it([x]))
        return "- %s%s%s" % (("%s：" if zh else "%s: ") % lab(x["canon"], lg), x["value"], it([x]))

    def blk(xs, lim=10, bare=False):
        return "\n".join(item(x, bare) for x in xs[:lim]) or "- " + t["na"]

    hdr = lambda s: "| " + " | ".join(s.split("|")) + " |\n|" + "---|" * len(s.split("|"))
    pr = [x for x in fs if x["canon"] in PARAMS]
    params = "\n".join([t["tbl"], "", hdr(t["h"])] + ["| %s | %s | %s | %s | %s#%s |" % (
        lab(x["canon"], lg), x["value"], x["name"].split(".")[0] if "." in x["name"] else "-", x["source"],
        x["source"], x["loc"]) for x in pr[:30]]) if pr else "- " + t["na"]
    mts = [x for x in fs if x["via"] == "metric"]
    ctl = [item(x) for x in fs if x["element"] == "controls" and x["via"] != "metric"][:6]
    ctl += [item(x, True) for x in mts[:6]]
    if "budget" in g and ctl:
        ctl.append("- " + BUD[0 if zh else 1] % g["budget"])
    rl = [item(x) for x in fs if x["canon"] == "pkg"
          or (x["element"] == "repro" and x["canon"] in ("seed", "repeats", "commit", "version"))][:12]
    cm = [x for x in fs if x["canon"] == "command"]
    if cm:
        rl.append("- %s `%s`%s" % ("复现命令" if zh else "reproduction command", cm[0]["value"][:150], it(cm[:1])))
    lm = [x for x in fs if x["element"] == "limits"]
    k = next((z for z in ("split", "repeats", "budget", "seed") if z in g), None)
    lim = "\n".join("- " + x["value"][:220] + it([x]) for x in lm[:6]) if lm else \
        "- " + (LIMG[0 if zh else 1] % (lab(k, lg), g[k]) if k else LIMN[0 if zh else 1])
    grow = ["| %s | %s | %s | %s |" % (q, lab(z, lg), QF.get(z, [z, z])[0 if zh else 1], t["absent"]) for z, q in g.items()]
    grow += ["| C%d | %s | %s | %s / %s |" % (j, x["canon"], ("草稿 %s vs 配置 %s" if zh else "draft %s vs config %s")
                                               % (x["draft_value"], x["source_value"]), x["source_loc"], x["draft_loc"])
             for j, x in enumerate(cf, 1)]
    d = {"s%d" % i: t["s"][i] for i in range(9)}
    d.update(title=t["t"], note=t["note"].format(m=nmat, n=len(eid)), a=t["a"], b=t["b"], ia=hdr(t["ia"]), ib=hdr(t["ib"]),
             lead=t["lead"].format(c=len({x["element"] for x in fs}), n=len(fs), g=len(g)),
             datasets=blk([x for x in fs if x["element"] == "datasets"]),
             steps="\n".join("%d. %s（%s#%s）" % (i, s["text"], s["source"], s["loc"]) for i, s in enumerate(st, 1)) if st else t["noord"],
             ord=t["ord"] if st else "", setup=blk([x for x in fs if x["element"] == "setup"]),
             params=params, controls="\n".join(ctl) or "- " + t["na"], metrics=blk(mts, 8, True),
             repro="\n".join(rl) or "- " + t["na"], limits=lim,
             evrows="\n".join("| E%d | %s | %s | %s |" % (eid[id(x)], x["source"], x["loc"],
                                                          x["quote"].replace("|", "/")[:150]) for x in fs if id(x) in eid),
             gaprows="\n".join(grow))
    return t["tpl"].format(**d)


WR = [(("参数", "parameter", "hyperparameter"), "parameters"), (("步骤", "step", "procedure"), "procedure"),
      (("数据", "dataset", "split"), "datasets"), (("对照", "baseline", "control", "ablation"), "controls"),
      (("复现", "reproduc", "seed", "版本"), "repro"), (("限制", "limit", "局限"), "repro"),
      (("设置", "setup", "硬件"), "setup")]


def workorder(case):
    it = []
    for k in ("organizer_workorder", "organizer_edit_workorder", "workorder", "edit_workorder"):
        v = case.get(k) if isinstance(case, dict) else None
        for i, x in enumerate([v] if isinstance(v, str) else (v or []), 1):
            t = " ".join(str(x.get(z, "")) for z in ("text", "item", "instruction", "requirement", "content")) \
                if isinstance(x, dict) else str(x)
            if t.strip():
                it.append({"id": str(x.get("id") or i) if isinstance(x, dict) else str(i), "text": t.strip()[:400]})
    return it

def apply_wo(items):
    rep, secs = [], set()
    for x in items:
        low = x["text"].lower()
        act, st = "noted", "noted"
        for kws, e in WR:
            if any(k.lower() in low for k in kws):
                secs.add(e)
                act, st = "section %s, evidence-marked" % e, "done"
                break
        if any(k in low for k in ("表", "table")):
            act, st = act + "; tables emitted", "done"
        if any(k in low for k in ("不增加", "不得", "不要", "不新增", "do not add")):
            act, st = act + "; no out-of-material facts", "done"
        rep.append({"id": x["id"], "requirement": x["text"], "action": act, "status": st,
                    "section_or_field": ", ".join(sorted(secs)) or "manuscript"})
    return rep

def fill(c, p, d=0):
    """Deep-copy the contract shape; fill recognised leaves from the payload."""
    if isinstance(c, dict):
        o = {}
        for k, v in c.items():
            if isinstance(v, (dict, list)) and d < 3:
                o[k] = fill(v, p, d + 1)
            else:
                f = FM.get(nm(k))
                o[k] = p[f] if (f and p.get(f) not in (None, "", [], {})) else v
        return o
    if isinstance(c, list) and d < 3 and 0 < len(c) <= 3 and all(isinstance(x, dict) for x in c):
        return [fill(x, p, d + 1) for x in c]
    return c

REQ = "case_id status sources uncertainty pending_human errors degradations changes runtime outputs".split()

def skel(con, cid, st):
    p = dict.fromkeys(REQ)
    p.update({"case_id": cid, "status": st, "sources": [], "uncertainty": [], "pending_human": [], "errors": [],
              "degradations": [], "changes": [], "outputs": [], "checks": {}, "runtime": {"skill": "methods-experiments-writer", "version": V}})
    if isinstance(con, dict):
        o = fill(con, p)
        for k in REQ:
            o.setdefault(k, p[k])
        return o
    return p

DIRX = r"(10\.\d{4,9}/[-._;()/:a-z0-9]+|arXiv:\d{4}\.\d{4,5})"
STRIP = [r"\[E[\d,\s]+\]", r"\b[QCAG]\d+\b", r"^\s*#{1,6}\s*\d+(?:\.\d+)*", r"^\s*\d+[.)]\s+",
         r"(?:表|Table)\s*\d+", r"§\s*\d+", r"^\|\s*-"]

def mach(txt):
    t = txt or ""
    for p in STRIP:
        t = re.sub(p, " ", t, flags=re.M)
    return [m.group(0) for m in re.finditer(r"(?<![\w.])[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", t)]

def fset(vals):
    s = set()
    for v in vals:
        try:
            s.add(round(float(str(v).replace("%", "").strip()), 9))
        except Exception:
            pass
    return s

def check_all(res, corpus="", contract=None, out=None):
    ch = []

    def ck(n, ok, detail="", count=None):
        ch.append({"check": n, "ok": bool(ok), "detail": str(detail)[:400], "count": count})

    def miss(con, r, pre="", acc=None):
        acc = acc if acc is not None else []
        if isinstance(con, dict):
            for k, v in con.items():
                if not isinstance(r, dict):
                    acc.append(pre or "/")
                    break
                if k not in r:
                    acc.append((pre + "/" + k) if pre else k)
                elif isinstance(v, dict):
                    miss(v, r.get(k), (pre + "/" + k) if pre else k, acc)
        return acc

    try:
        m = miss(contract or {}, res)
    except Exception:
        m = ["<contract unreadable>"]
    man, cn = res.get("manuscript") or "", re.sub(r"\s+", " ", corpus)
    ev = [e for e in (res.get("evidence_map") or []) if isinstance(e, dict)]
    nrm = lambda q: re.sub(r"\s+", " ", q or "")
    bad = [str(e.get("evidence_id")) for e in ev if len(nrm(e.get("quote"))) < 3 or nrm(e.get("quote")) not in cn]
    allowed = fset(mach(cn)) | fset(list((res.get("derived_counts") or {}).values()))
    uns = sorted({n for n in mach(man) if fset([n]) - allowed}) if man else ["<no manuscript>"]
    ids = {e.get("evidence_id") for e in ev}
    flat = set()
    for u in re.findall(r"\[E([\d,]+)\]", man):
        flat |= {"E" + x for x in u.split(",") if x}
    dang, cov = sorted(flat - ids), res.get("element_coverage") or {}
    gaps = [e for e in ELEMENTS if not (isinstance(cov.get(e), dict) and (cov[e].get("items") or 0) > 0)]
    pend = res.get("pending_human") or []
    arts = [a.get("path") for a in (res.get("outputs") or []) if isinstance(a, dict)]
    absent = [a for a in arts if not out or not (Path(out) / a).is_file() or (Path(out) / a).stat().st_size < 20]
    idsrc = set(re.findall(DIRX, corpus or "", re.I))
    fab = sorted(set(re.findall(DIRX, man, re.I)) - idsrc)
    st = res.get("status")
    for n, ok, det in (("output_contract_fields", not m, ",".join(m[:10])),
                       ("quotes_verbatim_in_materials", not bad, ",".join(bad[:10])),
                       ("numerals_supported_by_materials", not uns, ",".join(uns[:10])),
                       ("evidence_markers_resolve", not dang, ",".join(dang[:10])),
                       ("six_element_coverage", len(gaps) <= 2 or bool(pend), ",".join(gaps)),
                       ("gaps_sent_to_pending_human", (not gaps) or bool(pend), "pending=%d" % len(pend)),
                       ("artifacts_written", bool(arts) and not absent, ",".join(absent[:6])),
                       ("no_invented_identifiers", not fab, ",".join(fab[:5])),
                       ("status_consistent", st in ("ok", "partial", "insufficient_evidence", "input_error")
                        and not (st == "ok" and (gaps or pend or res.get("errors"))), "status=%s" % st)):
        ck(n, ok, det, len(det.split(",")) if det else 0)
    passed = sum(1 for c in ch if c["ok"])
    return {"checks": ch, "passed": passed, "failed": len(ch) - passed, "ok": passed == len(ch),
            "failed_items": [c["check"] for c in ch if not c["ok"]]}


