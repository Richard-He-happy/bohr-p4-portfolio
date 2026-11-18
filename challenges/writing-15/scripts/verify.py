#!/usr/bin/env python3
"""writing-11 | deterministic checks for long-document chapter revision (library + CLI).

  python3 verify.py audit --index work/source_index.json --draft work/draft.json \
      --manuscript output/manuscript.md --out-dir output
  python3 verify.py quote --index work/source_index.json --quote "<exact sentence>"

Findings are computed from the supplied text; stdlib only, no network, CWD-free.
"""
import argparse
import json
import re
import sys
from pathlib import Path

SPELL = [(r"\b3D\b", r"\b3-D\b", "3D / 3-D"),
         (r"\bmodel(?:ing|ed)\b", r"\bmodell(?:ing|ed)\b", "modeling / modelling"),
         (r"\bfiber", r"\bfibre", "fiber / fibre"),
         (r"\bbehavior", r"\bbehaviour", "behavior / behaviour"),
         (r"\banalyz(?:e|ed|ing)\b", r"\banalys(?:e|ed|ing)\b", "analyze / analyse"),
         (r"\blabel(?:ed|ing)\b", r"\blabell(?:ed|ing)\b", "labeled / labelled"),
         (r"\bcolor", r"\bcolour", "color / colour"),
         (r"µm", r"\bum\b", "µm / um")]
ADEF = re.compile(r"([A-Z][A-Za-z\-]+(?:\s+[A-Za-z\-]+){0,5})\s*\(([A-Z]{2,6}s?)\)")
LREF = re.compile(r"\b(Table|Tables|Figure|Fig\.|Equation|Eq\.|Section|Sec\.|Appendix|Algorithm)"
                  r"\s*\(?(\d+(?:\.\d+)*)\)?")
HEDN = re.compile(r"^#{1,6}\s*(\d+(?:\.\d+)*)")
CITE = re.compile(r"\[(\d+(?:\s*[,\u2013\-]\s*\d+)*)\]")
REFL = re.compile(r"^\s*\[(\d+)\]|^\s*(\d+)\.\s+[A-Z]")
PH = re.compile(r"\[(?:CITATION|CITE|REF|TODO|TBD|待补)\w*\s*\]|\?\?|\[\?\]", re.I)
UNIT = re.compile(r"(\d+(?:[.,]\d+)?)\s*(MPa|GPa|kPa|Pa|kN|N·m|Nm|mm|cm|nm|µm|um|kg|mg|µg|ms|min|h"
                  r"|°C|K|mL|ml|L|%)(?![A-Za-z])")
DIM = {"mpa": "pressure", "gpa": "pressure", "kpa": "pressure", "pa": "pressure", "kn": "force",
       "n·m": "moment", "mm": "length", "cm": "length", "nm": "length", "kg": "mass",
       "mg": "mass", "µg": "mass", "ms": "time", "min": "time", "h": "time", "°c": "temperature",
       "k": "temperature", "ml": "volume", "l": "volume", "%": "ratio"}


def norm(s):
    s = s or ""
    for a, b in (("\u00a0", " "), ("\u2018", "'"), ("\u2019", "'"), ("\u201c", '"'), ("\u201d", '"'),
                 ("\u2013", "-"), ("\u2014", "-"), ("\u2212", "-"), ("\ufb01", "fi"), ("\ufb02", "fl")):
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", s).strip()


def _f(store, check, sev, msg, loc=None, action=""):
    store.append({"id": "V%03d" % (len(store) + 1), "check": check, "severity": sev,
                  "status": "open" if sev in ("high", "warn") else "ok", "message": msg,
                  "locators": [x for x in (loc or []) if x], "action": action})
    return store[-1]


def resolve(index, target_id):
    """Workorder target id -> the source block that carries it."""
    tid = (target_id or "").strip()
    if not tid:
        return None
    for b in index.get("blocks", []):
        if tid in (b.get("anchors") or []):
            return b
    for b in index.get("blocks", []):
        if tid in (b.get("text") or ""):
            return b
    m = re.search(r"P(\d{1,5})$", tid)  # C01-P002 -> paragraph 2, flagged as heuristic
    blocks = index.get("blocks") or []
    if m and 1 <= int(m.group(1)) <= len(blocks):
        b = dict(blocks[int(m.group(1)) - 1])
        b["_heuristic"] = "paragraph index from the target id, not an explicit anchor"
        return b
    return None


def find_quote(index, quote, limit=3):
    """Whitespace-insensitive verbatim search: block first, then whole material."""
    nq = norm(quote)
    if len(nq) < 8:
        return []
    hits = [{"block_id": b["bid"], "material": b["material"], "locator": b["locator"],
             "exact_block": True} for b in index.get("blocks", []) if nq in norm(b.get("text", ""))]
    if hits:
        return hits[:limit]
    for m in index.get("materials", []):
        if nq in norm(m.get("text", "")):
            hits.append({"block_id": None, "material": m["id"], "exact_block": False,
                         "locator": m["rel"] + " (match spans blocks)"})
    return hits[:limit]


def check_draft(index, draft):
    """Scope, verbatim anchors, evidence and per-target receipts."""
    out, draft = [], draft if isinstance(draft, dict) else {}
    anns = draft.get("annotations") if isinstance(draft.get("annotations"), list) else []
    targets = [it.get("target_id") for it in (index.get("workorder_items") or [])]
    if not anns:
        _f(out, "workorder_receipt", "high", "no annotations in draft; build falls back to "
           "deterministic notes", action="one proposal per target")
    seen = {}
    for i, a in enumerate(anns):
        if not isinstance(a, dict):
            _f(out, "draft_schema", "high", "#%d not an object" % (i + 1))
            continue
        aid, tid = a.get("annotation_id") or "EA-%02d" % (i + 1), (a.get("target_id") or "").strip()
        blk = resolve(index, tid)
        if not tid:
            _f(out, "draft_schema", "high", "%s has no target_id" % aid)
        elif targets and tid not in targets:
            _f(out, "annotation_scope", "high", "%s targets %s outside the workorder" % (aid, tid),
               action="not applied")
        elif blk is None:
            _f(out, "workorder_receipt", "high", "%s: target %s absent from materials" % (aid, tid),
               action="pending_human; never invent it")
        anchor = a.get("anchor_quote") or ""
        if blk is not None:
            if not anchor:
                _f(out, "quote_traceability", "warn", "%s has no anchor_quote" % aid, [blk["locator"]])
            elif norm(anchor) not in norm(blk.get("text", "")):
                h = find_quote(index, anchor)
                where = " (found at %s)" % h[0]["locator"] if h else "; not verbatim anywhere"
                _f(out, "quote_traceability", "high", "%s anchor_quote not in %s%s" % (aid, tid, where),
                   [h[0]["locator"]] if h else [], "quote the target exactly")
        text = norm(a.get("text"))
        if len(text) < 60:
            _f(out, "annotation_quality", "warn", "%s text under 60 chars" % aid)
        if text in seen:
            _f(out, "annotation_quality", "warn", "%s duplicates %s" % (aid, seen[text]))
        seen[text] = aid
        ev = a.get("evidence") if isinstance(a.get("evidence"), list) else []
        if not ev:
            _f(out, "quote_traceability", "warn", "%s has no evidence" % aid)
        for j, e in enumerate(ev):
            q = e.get("quote") if isinstance(e, dict) else None
            if not q:
                _f(out, "quote_traceability", "high", "%s evidence #%d has no quote" % (aid, j + 1))
            elif not find_quote(index, q):
                _f(out, "quote_traceability", "high", "%s evidence #%d not verbatim" % (aid, j + 1),
                   action="use an exact source sentence")
        if (a.get("status") or "").lower() in ("rejected", "reject") and not (a.get("reason") or a.get("rationale")):
            _f(out, "workorder_receipt", "warn", "%s rejected without a reason" % aid)
        if a.get("revised_original") or a.get("replace_original"):
            _f(out, "annotation_scope", "high", "%s would rewrite original text" % aid)
    covered = {(a.get("target_id") or "").strip() for a in anns if isinstance(a, dict)}
    for t in targets:
        if t not in covered:
            _f(out, "workorder_receipt", "high", "target %s has no proposal/receipt" % t,
               action="accept or explicitly reject every item")
    have = {(c.get("id") or c.get("heading") or "").strip()
            for c in (draft.get("chapter_drafts") or []) if isinstance(c, dict)}
    for o in (draft.get("outline") or []):
        key = ((o.get("id") or o.get("heading") or "") if isinstance(o, dict) else str(o)).strip()
        if key and key not in have:
            _f(out, "coverage", "warn", "outline chapter %s has no draft section" % key)
    hi, wn = sum(1 for f in out if f["severity"] == "high"), sum(1 for f in out if f["severity"] == "warn")
    return {"findings": out, "pass": hi == 0,
            "counts": {"checks": len(out), "high": hi, "warn": wn, "info": len(out) - hi - wn,
                       "annotations": len(anns), "targets": len(targets),
                       "targets_covered": len(covered & set(targets))}}

def _paras(t):
    return [p for p in re.split(r"\n\s*\n", t or "") if p.strip()]


def scan_manuscript(index, mtext):
    """Terminology, numbering, citations, units and value conflicts."""
    out, paras = [], _paras(mtext)
    sdefs = {}
    for b in index.get("blocks", []):
        for m in ADEF.finditer(b["text"]):
            sdefs.setdefault(m.group(2), set()).add(norm(m.group(1)))
    for ab, exps in sorted(sdefs.items()):
        if len(exps) > 1:
            _f(out, "terminology", "high", "%s has %d expansions in source: %s"
               % (ab, len(exps), "; ".join(sorted(exps))), ["source materials"],
               "keep source wording; author decides")
    mdefs = {}
    for i, p in enumerate(paras, 1):
        for m in ADEF.finditer(p):
            mdefs.setdefault(m.group(2), []).append((i, norm(m.group(1))))
    for ab, occ in sorted(mdefs.items()):
        same = len({e for _, e in occ}) == 1
        if len(occ) > 1:
            _f(out, "terminology", "warn" if same else "high", "%s defined %d times (%s)"
               % (ab, len(occ), "same" if same else "different expansion"),
               ["manuscript ¶%d" % i for i, _ in occ])
    for ab in sorted(set(sdefs) | set(mdefs)):
        use = [i for i, p in enumerate(paras, 1) if re.search(r"\b%s\b" % re.escape(ab), p)]
        dfn = [i for i, _ in mdefs.get(ab, [])]
        if use and dfn and min(use) < min(dfn):
            _f(out, "terminology", "warn", "%s used (¶%d) before definition (¶%d)"
               % (ab, min(use), min(dfn)))
    for pa, pb, lab in SPELL:
        a = [i for i, p in enumerate(paras, 1) if re.search(pa, p)]
        b = [i for i, p in enumerate(paras, 1) if re.search(pb, p)]
        if a and b:
            _f(out, "terminology", "warn", "two spellings coexist: %s" % lab,
               ["manuscript ¶%d" % a[0], "manuscript ¶%d" % b[0]], "unify spellings only")
    inv, caps = {}, {}
    for i, p in enumerate(paras, 1):
        for m in LREF.finditer(p):
            lab = norm(m.group(1)).rstrip(".").rstrip("s")
            lab = {"fig": "figure", "eq": "equation", "sec": "section"}.get(lab, lab)
            inv.setdefault(lab, []).append((m.group(2), i))
            if re.search(r"(?i)\b%s\s*%s\s*[:.|]" % (re.escape(m.group(1)), re.escape(m.group(2))), p):
                caps.setdefault(lab, []).append(m.group(2))
    for lab in ("table", "figure", "equation"):
        ints = sorted({int(n) for n in (x for x, _ in inv.get(lab, [])) if n.isdigit()})
        gaps = [x for x in range(1, ints[-1] + 1) if x not in ints] if ints else []
        if gaps:
            _f(out, "numbering", "info", "%s numbering missing %s"
               % (lab, ", ".join(map(str, gaps))), ["numbering inventory"])
        for n in sorted({n for n in caps.get(lab, []) if caps[lab].count(n) > 1}):
            _f(out, "numbering", "warn", "two %s captions numbered %s" % (lab, n),
               ["manuscript ¶%d" % i for x, i in inv.get(lab, []) if x == n][:4])
    heads = {m.group(1) for p in paras for m in [HEDN.match(p.strip())] if m}
    for num, i in inv.get("section", []):
        if heads and num not in heads:
            _f(out, "numbering", "warn", "'Section %s' matches no heading" % num,
               ["manuscript ¶%d" % i], "fix the cross-reference")
    cited, refs = set(), set()
    for i, p in enumerate(paras, 1):
        for m in CITE.finditer(p):
            for part in m.group(1).split(","):
                if re.match(r"^\d+\s*[\u2013\-]\s*\d+$", part.strip()):
                    a, b = [int(x) for x in re.split(r"[\u2013\-]", part.strip())]
                    cited.update(range(min(a, b), max(a, b) + 1))
                elif part.strip().isdigit():
                    cited.add(int(part))
        m = REFL.match(p.strip())
        if m:
            refs.add(int(m.group(1) or m.group(2)))
        if PH.search(p):
            _f(out, "citation", "high", "unresolved citation placeholder", ["manuscript ¶%d" % i],
               "pending_human; never invent a reference")
    if refs:
        miss, unc = sorted(c for c in cited if c not in refs), sorted(r for r in refs if r not in cited)
        if miss:
            _f(out, "citation", "high", "cited but missing from reference list: %s" % miss[:12],
               ["reference list"], "restore the entry or drop the citation")
        if unc:
            _f(out, "citation", "info", "reference entries never cited: %s" % unc[:12])
    elif cited:
        _f(out, "citation", "info", "%d citations carried verbatim; no reference list in materials"
           % len(cited), action="author confirms the bibliography")
    seen = {}
    for i, p in enumerate(paras, 1):
        rng = re.search(r"\bfrom\b.{0,60}\bto\b", p)  # "from 28.5 MPa to 41.2 MPa" is a range
        for m in UNIT.finditer(p):
            if rng and rng.start() < m.start() < rng.end():
                continue
            key = (" ".join(re.findall(r"[A-Za-z][A-Za-z\-]{3,}", norm(p[max(0, m.start() - 60):m.start()]).lower())[-3:]),
                   DIM.get(m.group(2).lower(), "other"))
            seen.setdefault(key, []).append((m.group(1).replace(",", "."), m.group(2), i))
    for (ctx, dim), occ in sorted(seen.items()):
        vals = {(v, u) for v, u, _ in occ}
        if len({v for v, _ in vals}) > 1 and len({u for _, u in vals}) == 1:
            _f(out, "numeric_conflict", "warn", "different values for '%s': %s"
               % (ctx or "context", ", ".join("%s %s" % x for x in sorted(vals))),
               sorted({"manuscript ¶%d" % i for _, _, i in occ}), "preserve both; do not correct")
        units = {u for _, u, _ in occ}
        if len(units) > 1 and dim in ("pressure", "length", "temperature"):
            _f(out, "units", "info", "mixed units for '%s': %s"
               % (ctx or "context", ", ".join(sorted(units))))
    return out

def preserved_facts(index, mtext, limit=90):
    """Source sentences carrying values, citations or defined terms, and their carry-over."""
    out, seen, nm = [], set(), norm(mtext)
    for b in index.get("blocks", []):
        for sent in re.split(r"(?<=[.!?])\s+", b["text"]):
            sent = sent.strip()
            if len(sent) < 12:
                continue
            kinds = [k for k, p in (("measurement", UNIT), ("citation", CITE), ("term", ADEF)) if p.search(sent)]
            if not kinds or sent[:70] in seen:
                continue
            seen.add(sent[:70])
            out.append({"fact_id": "F%03d" % (len(out) + 1), "kind": kinds[0], "quote": sent,
                        "source_locator": b["locator"], "preserved": sent[:70] in nm,
                        "note": "verbatim carry-over; annotations must not alter it"})
            if len(out) >= limit:
                return out
    return out


def consistency_markdown(index, findings, facts, drep=None):
    """Human-readable report from the computed findings."""
    L = ["# Cross-chapter consistency report", "",
         "Computed from the supplied text by `writing-11` (`scripts/verify.py`); counts and "
         "locators come from the files, not from prose claims.", "",
         "## 1. Inputs", "", "| id | file | kind | blocks | extraction |", "|---|---|---|---|---|"]
    L += ["| %s | %s | %s | %d | %s |" % (m["id"], m["rel"], m["kind"], m.get("blocks_n", 0),
                                          m.get("extraction", "")) for m in index.get("materials", [])]
    L += ["", "## 2. Findings", "", "| id | check | severity | message | locators |", "|---|---|---|---|---|"]
    L += (["| %s | %s | %s | %s | %s |" % (f["id"], f["check"], f["severity"],
                                           f["message"].replace("|", "/"),
                                           "<br>".join(f["locators"]).replace("|", "/") or "-")
           for f in findings] or ["| - | - | ok | implemented checks found no inconsistency | - |"])
    sev = {k: sum(1 for f in findings if f["severity"] == k) for k in ("high", "warn", "info")}
    L += ["", "**Totals:** %d checks — %d high, %d warn, %d info."
          % (len(findings), sev["high"], sev["warn"], sev["info"]), "",
          "## 3. Preserved facts", "", "%d facts tracked; %d verified verbatim."
          % (len(facts), sum(1 for f in facts if f["preserved"]))]
    L += ["- **%s not preserved** `%s` (%s)" % (f["fact_id"], f["quote"][:100], f["source_locator"])
          for f in [x for x in facts if not x["preserved"]][:12]]
    if drep and drep.get("counts"):
        c = drep["counts"]
        L += ["", "## 4. Draft validation", "",
              "- checks: %s / high: %s / warn: %s / annotations: %s / targets covered: %s of %s"
              % (c.get("checks"), c.get("high"), c.get("warn"), c.get("annotations"),
                 c.get("targets_covered"), c.get("targets"))]
        L += ["- **%s/%s** %s (%s)" % (f["check"], f["severity"], f["message"],
                                       "; ".join(f["locators"]) or "-")
              for f in drep.get("findings", []) if f["severity"] in ("high", "warn")]
    L += ["", "## 5. Limits of these checks", "",
          "- Entailment of an annotation by its cited sentence is not machine-judged (verbatim "
          "presence, scope, lexical overlap only).",
          "- Source correctness is out of scope: contradictions are reported, not corrected.",
          "- Bibliography completeness cannot be judged when materials carry no reference list.", ""]
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="verify.py", description=__doc__.splitlines()[0])
    ap.add_argument("mode", nargs="?", default="audit", choices=["audit", "quote"])
    for flag in ("--index", "--draft", "--manuscript", "--quote", "--out-dir"):
        ap.add_argument(flag)
    a = ap.parse_args(argv)
    index = {}
    if a.index:
        try:
            index = json.loads(Path(a.index).read_text(encoding="utf-8-sig"))
        except Exception as exc:
            print("index unreadable: %s" % exc)
    if a.mode == "quote":
        hits = find_quote(index, a.quote or "")
        print(json.dumps(hits, ensure_ascii=False, indent=2) if hits else "NOT FOUND (verbatim)")
        return 0
    mtext, draft = "", {}
    for path, name in ((a.manuscript, "manuscript"), (a.draft, "draft")):
        if not path:
            continue
        try:
            obj = Path(path).read_text(encoding="utf-8-sig")
            if name == "manuscript":
                mtext = obj
            else:
                draft = json.loads(obj)
        except Exception as exc:
            print("%s unreadable: %s" % (name, exc))
    drep = check_draft(index, draft) if index else {"findings": [], "counts": {}, "pass": False}
    findings = scan_manuscript(index, mtext) if index else []
    facts = preserved_facts(index, mtext) if index else []
    if a.out_dir:
        od = Path(a.out_dir)
        od.mkdir(parents=True, exist_ok=True)
        (od / "consistency_report.md").write_text(
            consistency_markdown(index, findings, facts, drep) + "\n", encoding="utf-8")
        (od / "consistency_report.json").write_text(json.dumps(
            {"findings": findings, "draft_validation": drep,
             "preserved_facts_summary": {"total": len(facts),
                                         "verified": sum(1 for f in facts if f["preserved"])}},
            ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("wrote %s/consistency_report.md and .json" % od)
    sev = {k: sum(1 for f in findings if f["severity"] == k) for k in ("high", "warn", "info")}
    print("consistency: %d findings (high=%d warn=%d info=%d); facts %d/%d verbatim; draft pass=%s"
          % (len(findings), sev["high"], sev["warn"], sev["info"],
             sum(1 for f in facts if f["preserved"]), len(facts), drep.get("pass")))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print("verify.py internal error (reported, exit 0): %r" % (exc,))
        sys.exit(0)
