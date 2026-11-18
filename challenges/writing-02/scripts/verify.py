#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""writing-02 academic-language-polish, stage 2 (imported by main.py):
extraction, payload assembly, contract filling, checks, deliverable writing.
standalone: python3 -B verify.py --output DIR"""
import argparse, csv, hashlib, html, json, re, shutil, subprocess, sys, zipfile, zlib
from collections import Counter
from pathlib import Path

from main import BRE, BZR, CIT, HRE, HZR, NUM, XREF, cnt, nw

CT = set("grammar agreement tense voice article preposition punctuation sentence_split word_order "
         "collocation redundancy nominalization chinglish terminology abbreviation register hedging "
         "citation_format unit_format typography structure translation no_change unclassified".split())
DONE = {"done", "covered", "completed", "not_applicable", "n/a"}
EXT = {".md", ".txt", ".tex", ".rst", ".csv", ".tsv", ".json", ".docx", ".pdf"}
IMG = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp"}


def rt(p):
    b = Path(p).read_bytes()
    for e in ("utf-8-sig", "utf-8", "gb18030", "big5", "cp1252", "latin-1"):
        try:
            return b.decode(e)
        except UnicodeDecodeError:
            pass
    return b.decode("utf-8", "replace")


def pdf_text(p, dg):
    """pdftotext -> pypdf -> FlateDecode scan; returns (text, method)."""
    try:
        ex = shutil.which("pdftotext")
        if ex:
            t = subprocess.run([ex, "-q", "-layout", str(p), "-"], timeout=90,
                               capture_output=True).stdout.decode("utf-8", "replace")
            if len(nw(t)) > 200:
                return t, "pdftotext"
    except Exception:
        pass
    try:
        out = []
        for m in re.finditer(rb"stream\r?\n(.*?)endstream", Path(p).read_bytes(), re.S):
            try:
                d = zlib.decompress(m.group(1))
            except Exception:
                d = m.group(1)
            for x in re.finditer(rb"\((?:\\.|[^\\()])*\)", d):
                out.append(re.sub(rb"\\([()\\])", rb"\1", x.group(0)[1:-1]).decode("latin-1"))
        t = " ".join(out)
        if len(nw(t)) < 100:
            dg.append({"what": "pdf_text", "file": p.name, "detail": "no text layer (scanned?)"})
        return t, "builtin-flate"
    except Exception as e:
        dg.append({"what": "pdf_parse", "file": p.name, "detail": str(e)[:110]})
        return "", "failed"


def docx_text(p, dg):
    try:
        with zipfile.ZipFile(p) as z:
            x = z.read("word/document.xml").decode("utf-8", "replace")
        x = re.sub(r"<w:br[^>]*/>", "\n", x.replace("</w:p>", "\n\n").replace("<w:tab/>", "\t"))
        return html.unescape(re.sub(r"<[^>]+>", "", x)), "zipxml"
    except Exception as e:
        dg.append({"what": "docx", "file": p.name, "detail": str(e)[:110]})
        return "", "failed"


def read_materials(case, indir, cpath, skip=()):
    """input scan -> (mats, texts, embedded, degradations)."""
    dg, mats, texts = [], [], []
    for p in [m for m in sorted(indir.rglob("*")) if m.is_file() and not m.name.startswith(".")
              and m.suffix.lower() in (EXT | IMG) and m != cpath
              and not any(str(m).startswith(x) for x in skip)][:40]:
        e = p.suffix.lower()
        rec = {"name": p.name, "path": str(p), "kind": e.lstrip("."), "chars": 0, "method": ""}
        if e in IMG:
            rec["method"] = "not_read"
            dg.append({"what": "image_material", "file": p.name, "detail": "not OCR'd"})
            mats.append(rec)
            continue
        try:
            t, m = (pdf_text(p, dg) if e == ".pdf" else docx_text(p, dg) if e == ".docx"
                    else (rt(p), "text"))
        except Exception as x:
            dg.append({"what": "material_read", "file": p.name, "detail": str(x)[:110]})
            t, m = "", "failed"
        rec["chars"], rec["method"] = len(t or ""), m
        mats.append(rec)
        if t and nw(t) and p.name.lower() not in ("case.json", "task.md"):
            texts.append({"name": p.name, "text": t})
    emb = [{"name": "case.json#" + k, "text": v}
           for k, v in (case.items() if isinstance(case, dict) else [])
           if str(k).lower() in ("source_text", "manuscript", "original_text", "text", "draft",
                                 "abstract", "content", "section_text", "raw_text")
           and isinstance(v, str) and len(nw(v)) > 80]
    return mats, texts, emb, dg


def assemble_payload(res, payload, paras, gl, wo_items, gn, tl, mats):
    """Merge the agent payload with the source baseline; validate every edit quote."""
    by = {str(p["id"]): p for p in (payload or {}).get("paragraphs") or []
          if isinstance(p, dict) and p.get("id")}
    lines, edits, missing, changed = [], [], [], 0
    for p in paras:
        g = by.get(p["id"], {})
        rv = (g.get("revised") or "").strip()
        if not rv:
            rv = p["text"]
            if p["kind"] == "body" and not g.get("unchanged_reason"):
                missing.append(p["id"])
        elif nw(rv) != nw(p["text"]):
            changed += 1
        lines.append(rv)
        ed = [e for e in g.get("edits") or [] if isinstance(e, dict)]
        for e in ed:
            oq = nw(str(e.get("original_quote") or e.get("original") or ""))
            rq = nw(str(e.get("revised_quote") or e.get("revised") or ""))
            edits.append({**e, "paragraph_id": p["id"], "original_quote": oq, "revised_quote": rq,
                          "type": str(e.get("type") or "unclassified").lower(),
                          "reason": str(e.get("reason") or e.get("why") or ""),
                          "locator": e.get("locator") or p["source"] + "#" + p["id"],
                          "verified": bool(oq) and oq in nw(p["text"])
                          and (not rq or rq in nw(rv))})
        if rv and nw(rv) != nw(p["text"]) and not ed:
            edits.append({"paragraph_id": p["id"], "type": "unclassified", "verified": True,
                          "original_quote": nw(p["text"])[:160], "revised_quote": nw(rv)[:160],
                          "reason": "payload 仅给改文，未给逐条说明",
                          "locator": p["source"] + "#" + p["id"]})
            res["pending_human"].append({"item": p["id"] + " 缺逐条修改说明",
                                         "why": "改写段未提供 original/revised/reason"})
    man = "\n\n".join(lines).strip() or next(
        (payload[k].strip() for k in ("deliverable", "revised_text", "polished_text")
         if isinstance((payload or {}).get(k), str) and len(nw(payload[k])) > 50), "")
    gl2 = list(gl)
    facts, seen = [], set()
    for p in paras:
        for k in ("numbers", "citations", "xrefs", "abbreviations"):
            for v in p["locks"].get(k, []):
                if (k, v) not in seen:
                    seen.add((k, v))
                    facts.append({"kind": k[:-1], "value": v, "locator": p["source"] + "#" + p["id"],
                                  "present_in_revision": re.sub(r"\s+", "", v.lower()) in re.sub(r"\s+", "", man.lower())})
    facts = facts[:400]
    em = [{"claim_id": f["kind"] + ":" + str(i), "claim": f["value"], "locator": f["locator"],
           "quote": (next((x["text"] for x in paras if x["id"] == f["locator"].split("#")[-1]), "") or "")[:160]}
          for i, f in enumerate(facts[:200], 1)]
    pm = {str(r.get("id") or "").upper(): r for r in (payload or {}).get("workorder_receipts") or []
          if isinstance(r, dict)}
    wr = [{"id": w["id"], "requirement": w["text"][:200],
           "status": (pm.get(w["id"].upper()) or {}).get("status")
           or ("not_reported" if payload else "not_started"),
           "evidence": (pm.get(w["id"].upper()) or {}).get("evidence") or "",
           "locator": (pm.get(w["id"].upper()) or {}).get("locator") or ""} for w in wo_items]
    if missing:
        res["pending_human"].append({"item": "%d 段未收到润色稿" % len(missing),
                                     "why": "payload.revised 为空：" + ", ".join(missing[:20])})
    for x in (payload or {}).get("pending_human") or []:
        res["pending_human"].append(x if isinstance(x, dict) else {"item": str(x), "why": ""})
    res["uncertainty"] += [x if isinstance(x, dict) else {"note": str(x)}
                           for x in (payload or {}).get("uncertainty") or []]
    bad = [r["id"] for r in wr if r["status"] not in DONE]
    if bad:
        res["pending_human"].append({"item": "workorder 回执不完整", "why": "未回报：" + ", ".join(bad)})
    res.update({
        "manuscript_text": man, "n_paras": len(paras), "n_changed": changed,
        "revised": {p["id"]: ((by.get(p["id"], {}).get("revised") or "").strip() or p["text"])
                    for p in paras},
        "change_log": edits, "glossary": gl2[:120], "preserved_facts": facts, "evidence_map": em,
        "workorder_receipts": wr, "genre": gn, "target_language": tl,
        "bilingual": [x for x in (payload or {}).get("bilingual") or []
                      if isinstance(x, (dict, str))],
        "sources": [{"id": m["name"], "path": m["path"], "kind": m["kind"], "chars": m["chars"],
                     "extraction": m["method"]} for m in mats]})
    return res


MAP = {"change": "change_log", "修改": "change_log", "gloss": "glossary", "termin": "glossary",
       "术语": "glossary",
       "preserv": "preserved_facts", "evidence": "evidence_map", "bilingual": "bilingual",
       "workorder": "workorder_receipts", "receipt": "workorder_receipts", "status": "status",
       "uncertain": "uncertainty", "pending": "pending_human", "human": "pending_human",
       "check": "checks", "path": "manuscript_path", "text": "manuscript_text",
       "manuscript": "manuscript_text", "deliverable": "manuscript_text", "error": "errors"}


def fill_contract(ct, res):
    """Copy every output_contract field, keeping key names and example value types."""
    def pick(name, ex):
        k = name.lower().replace("-", "_").replace(" ", "_")
        v = res.get(next((p for pat, p in MAP.items() if pat in k), ""))
        if v is None:
            return [] if isinstance(ex, list) else (dict.fromkeys(ex) if isinstance(ex, dict) else None)
        if isinstance(ex, list) and not isinstance(v, list):
            v = [v]
        if isinstance(ex, dict) and not isinstance(v, dict):
            v = {"value": v}
        if isinstance(ex, str) and not isinstance(v, str):
            v = json.dumps(v, ensure_ascii=False)[:20000] if isinstance(v, (list, dict)) else str(v)
        return v
    if isinstance(ct, list):
        out = {}
        for it in ct:
            n = it if isinstance(it, str) else str(it.get("field") or it.get("name") or it.get("key") or "")
            if n:
                out[n] = pick(n, None)
        return out
    return {k: pick(str(k), v) for k, v in ct.items()} if isinstance(ct, dict) else {}


def _tk(t):
    return [re.sub(r"\s+", "", m.group(0)).lower()
            for m in NUM.finditer(XREF.sub(" ", CIT.sub(" ", t or "")))]


def verify_all(b, paras, ct, payload, res):
    C, H = [], []

    def add(i, st, d, c=None):
        C.append({"id": i, "status": st, "detail": str(d)[:300], "counts": c or {}})
        if st == "fail":
            H.append(i)

    man, rev = b.get("manuscript_text") or "", b.get("revised") or {}
    src = {p["id"]: p["text"] for p in paras}
    got = res.get("output_contract") if isinstance(res.get("output_contract"), dict) else {}
    if isinstance(ct, dict) and ct:
        m = [k for k in ct if k not in got]
        add("contract_fields", "pass" if not m else "fail",
            "%d/%d contract fields%s" % (len(ct) - len(m), len(ct),
                                         "; missing " + ",".join(m[:8]) if m else ""),
            {"fields": len(ct), "missing": len(m)})
    sc, rc, cs, cr, xs, xr = Counter(), Counter(), Counter(), Counter(), Counter(), Counter()
    for p in paras:
        sc.update(_tk(p["text"]))
        cs.update(nw(x.group(0)) for x in CIT.finditer(p["text"]))
        xs.update(nw(x.group(0)) for x in XREF.finditer(p["text"]))
    rc.update(_tk(man))
    cr.update(nw(x.group(0)) for x in CIT.finditer(man))
    xr.update(nw(x.group(0)) for x in XREF.finditer(man))
    lost = sorted(k for k in sc if rc.get(k, 0) < sc[k])
    new = sorted(k for k in rc if not sc.get(k))
    cl = sorted(k for k in cs if cr.get(k, 0) < cs[k])
    xl = sorted(k for k in xs if xr.get(k, 0) < xs[k])
    miss_n = len(lost) + len(cl) + len(xl)
    add("fact_locks", "fail" if miss_n else ("warn" if new else "pass"),
        "missing=%d (numbers %s; citations %s; xrefs %s); new numbers %s" % (
            miss_n, ",".join(lost[:6]) or "-", ",".join(cl[:4]) or "-", ",".join(xl[:4]) or "-",
            ",".join(new[:6]) or "-"),
        {"source_numbers": sum(sc.values()), "missing": miss_n, "new": len(new)})
    if new:
        res["pending_human"].append({"item": "改文出现原文没有的数字", "why": ", ".join(new[:10])})
    dz, zero = [], []
    for p in paras:
        r = rev.get(p["id"], "")
        a, c = (len(cnt(p["text"], HRE)) + len(cnt(p["text"], HZR)),
                len(cnt(r, HRE)) + len(cnt(r, HZR)))
        ba, bc = (len(cnt(p["text"], BRE)) + len(cnt(p["text"], BZR)),
                  len(cnt(r, BRE)) + len(cnt(r, BZR)))
        if c < a or bc > ba:
            dz.append("%s H%d>%d B%d>%d" % (p["id"], a, c, ba, bc))
            zero += [p["id"]] if (a and not c) else []
    add("hedge_strength", "fail" if zero else ("warn" if dz else "pass"),
        "; ".join(dz[:6]) or "hedge/booster counts unchanged",
        {"changed": len(dz), "lost_all": len(zero)})
    if dz:
        res["pending_human"].append({"item": "限定强度需复核", "why": "; ".join(dz[:6])})
    gl = [g for g in (b.get("glossary") or []) if g.get("target")]
    allsrc = " ".join(src.values()).lower()
    mt = [g["source"] for g in gl
          if g["source"].lower() in allsrc and g["target"].lower() not in man.lower()]
    add("terminology", "fail" if mt else "pass",
        "term not applied: " + ", ".join(mt[:8]) if mt else "%d term entries checked" % len(gl),
        {"entries": len(gl), "missing": len(mt)})
    ed = b.get("change_log") or []
    badq = [e["paragraph_id"] for e in ed if not e.get("verified")]
    badt = [e["paragraph_id"] for e in ed if e.get("type") not in CT]
    nore = [e["paragraph_id"] for e in ed if len(nw(e.get("reason") or "")) < 3]
    ok = not (badq or badt or nore)
    add("edit_traceability", "pass" if ok else "fail",
        "%d edits traceable" % len(ed) if ok
        else "edits %d; quote mismatch %d; bad type %d; no reason %d"
        % (len(ed), len(badq), len(badt), len(nore)),
        {"edits": len(ed), "unverified": len(badq), "bad_type": len(badt), "no_reason": len(nore)})
    n = len(paras)
    rv = sum(1 for p in paras if rev.get(p["id"]))
    add("coverage", "pass" if (n and rv == n) else ("fail" if payload and not rv else "warn"),
        "%d/%d revised; %d changed" % (rv, n, b.get("n_changed", 0)),
        {"paragraphs": n, "revised": rv, "changed": b.get("n_changed", 0)})
    h = hashlib.sha256("\n".join(rev.get(p["id"], "") for p in paras).encode()).hexdigest()[:16]
    add("revision_hash", "pass", "sha256:" + h, {})
    return {"checks": C, "hard": H,
            "counts": {"paragraphs": n, "revised_paragraphs": rv,
                       "changed_paragraphs": b.get("n_changed", 0), "edits": len(ed),
                       "edits_verified": len(ed) - len(badq), "missing_numbers": len(lost),
                       "new_numbers": len(new), "missing_citations": len(cl) + len(xl),
                       "hedge_drops": len(dz),
                       "workorder_items": len(b.get("workorder_receipts") or [])},
            "coverage": {"paragraphs": n, "revised": rv,
                         "ratio": round(rv / n, 3) if n else 0,
                         "changed": b.get("n_changed", 0), "edits": len(ed)}}


def render_deliverable(res):
    A = res.get("change_log") or []
    L = ["# 学术语言润色交付包 · %s" % (res.get("case_id") or "case"), "",
         "- status `%s` | edits %d | facts %d" % (
             res.get("status"), len(A), len(res.get("preserved_facts") or [])),
         "", "## 1. 润色后全文（可编辑）", "", res.get("manuscript_text") or "_（无正文）_", "",
         "## 2. 修改清单（原文 → 改文 → 理由 → 定位）", "",
         "| # | 段落 | 类型 | 原文 | 改文 | 理由 | 定位 | 校验 |", "|---|---|---|---|---|---|---|---|"]
    L += ["| %d | %s | %s | %s | %s | %s | %s | %s |" % (
        i, e.get("paragraph_id", ""), e.get("type", ""),
        str(e.get("original_quote", ""))[:120].replace("|", "/"),
        str(e.get("revised_quote", ""))[:120].replace("|", "/"),
        str(e.get("reason", ""))[:140].replace("|", "/"), e.get("locator", ""),
        "ok" if e.get("verified") else "待核") for i, e in enumerate(A, 1)]
    L += ["", "## 3. 术语表", ""]
    L += ["- `%s` → `%s`" % (g.get("source"), g.get("target")) for g in (res.get("glossary") or [])] \
        or ["- _未提供_"]
    L += ["", "## 4. 待确认 / 降级 / 边界", ""]
    L += ["- human `%s`: %s" % (x.get("item"), str(x.get("why", ""))[:200])
          for x in (res.get("pending_human") or [])] or ["- 无待确认项"]
    L += ["- %s `%s` %s" % (k, x.get("what"), str(x.get("detail", ""))[:120])
          for k, key in (("degradation", "degradations"), ("error", "errors"))
          for x in (res.get(key) or [])]
    L += ["- 明细见 result.json；未确认内容不改写，不补造文献或数值。"]
    return "\n".join(L) + "\n"

def write_outputs(res, out):
    out = Path(out)
    man = res.get("manuscript_text") or ""
    manp, bunp, csvp = out / "manuscript.md", out / "deliverable.md", out / "change_log.csv"
    fs = [str(manp), str(csvp), str(bunp)]
    res["manuscript_path"], res["polished_text"] = str(manp), man
    cols = ["paragraph_id", "type", "original_quote", "revised_quote", "reason", "locator",
            "verified"]
    try:
        manp.write_text(man.strip() + "\n", encoding="utf-8")
        bunp.write_text(render_deliverable(res), encoding="utf-8")
        with open(csvp, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            for r in res.get("change_log") or []:
                w.writerow({c: r.get(c, "") for c in cols})
    except Exception as e:
        res["degradations"].append({"what": "write_outputs", "detail": str(e)[:130]})
    res["deliverable"] = {"main_path": str(manp), "bundle_path": str(bunp), "files": fs,
                          "word_count": len(re.findall(r"\S+", man))}
    res["changes"] = [{"file": x, "action": "written"} for x in fs]
    c = dict(res.get("counts") or {})
    for k, key in (("change_log_items", "change_log"), ("preserved_facts", "preserved_facts"),
                   ("pending_human", "pending_human"), ("errors", "errors"),
                   ("degradations", "degradations")):
        c[k] = len(res.get(key) or [])
    res["counts"] = c
    if not man and res.get("status") == "ok":
        res["status"] = "partial"
    return fs


def main():
    ap = argparse.ArgumentParser(prog="verify.py", description="print checks of result.json")
    ap.add_argument("--output", default="/app/output")
    a = ap.parse_args()
    p = Path(a.output) / "result.json"
    try:
        r = json.loads(p.read_text(encoding="utf-8"))
        print("case=%s status=%s" % (r.get("case_id"), r.get("status")))
        for c in (r.get("checks") or []):
            print("  %-22s %-5s %s" % (c["id"], c["status"], str(c.get("detail", ""))[:100]))
        print("counts:", json.dumps(r.get("counts") or {}, ensure_ascii=False))
    except Exception as e:
        print("no readable result.json at %s: %s" % (p, e))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
