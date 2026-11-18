#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""writing-02 academic-language-polish: intake -> workpack -> assembly -> checks.
    python3 -B main.py [--input D] [--output D] [--work D] [--payload F]
Stage 2 (verify.py) assembles the payload, checks it, writes deliverables.
stdlib only; no network; no CWD dependence; exit 0."""
import argparse, json, os, re, sys, time
from pathlib import Path

V, SK = "1.0.0", "academic-language-polish"
D, T0 = Path(__file__).resolve().parent, time.time()
HE = ("may|might|could|likely|unlikely|probably|possibly|perhaps|suggest|suggests|indicate|"
      "indicates|appear|appears|seem|seems|tend|tends|approximately|about|nearly|roughly|"
      "preliminary|potential|potentially|presumably|in part|to date|consistent with|"
      "associated with|cannot exclude|cannot rule out|remains unclear|it is unclear").split("|")
HZ = "可能|或许|提示|推测|似乎|倾向于|初步|约|接近|尚不能|有待|在一定程度上|未必|不足以".split("|")
BE = ("demonstrate|demonstrates|demonstrated|prove|proves|proven|confirm|confirms|confirmed|"
      "establish|establishes|clearly|obviously|undoubtedly|certainly|definitely|always|never|must|"
      "novel|significantly|strongly|substantially|dramatically|markedly|robust|unprecedented|"
      "unique|conclusively|definitively|all|every|none").split("|")
BZ = "证明|证实|毫无疑问|必然|一定|始终|首次|显著|大幅|明显|完全|唯一|所有|从未|确保|彻底".split("|")
NUM = re.compile(
    r"(?<![A-Za-z0-9_.,])[-−]?\d+(?:[.,]\d+)*(?:\s?[eE][-+]?\d+)?"
    r"(?:\s?[×x]\s?10\s?\^?\s?[-−]?\d+)?\s?(?:%|‰|°C|mg/kg|mg/L|µg/mL|mg/mL|µg|μg|ng|pg|mg|g|kg|"
    r"mL|µL|μL|L|mM|µM|μM|nM|mmol|µmol|mol|kDa|Da|bp|kb|nm|µm|μm|mm|cm|km|min|ms|h|hr|d|wk|yr|"
    r"kPa|MPa|eV|keV|MeV|kHz|MHz|GHz|rpm|IU|CFU|ppm|ppb|wt%|vol%|copies)?")
CIT = re.compile(r"\[\s*\d+(?:\s*[-,–]\s*\d+)*\s*\]|\\cite\{[^}]*\}|\[@[^\]]+\]|"
                 r"\([A-Z][A-Za-z'\u00C0-\u024F]+(?:\s(?:et al\.?|and|&)\s?"
                 r"[A-Za-z'\u00C0-\u024F]*)?,?\s(?:19|20)\d{2}[a-z]?\)")
XREF = re.compile(r"\b(?:Fig(?:ure)?s?\.?|Figs?\.|Tab(?:le)?s?\.?|Eq(?:uation)?s?\.?|Sec(?:tion)?s?\.?"
                  r"|Scheme|Appendix|Supplementary\s(?:Fig|Table|Note)s?\.?)\s?\d+[A-Za-z]?")
DEFAB = re.compile(r"\(([A-Z][A-Za-z0-9&/\-]{1,9})\)")
HEAD = re.compile(r"^\s*(?:#{1,6}\s|\\section\{|\\subsection\{|\*\*[^*]{2,80}\*\*\s*$|"
                  r"\d+(?:\.\d+)*\.?\s+[A-Z][A-Za-z\- ]{1,60}$|[A-Z][A-Z0-9 \-&/:,]{3,70}$)")
INSK = {"task_instruction", "instruction", "instructions", "task", "task_description", "goal",
        "objective", "prompt", "requirement", "requirements", "edit_instruction"}


def nw(s):
    return re.sub(r"\s+", " ", s or "").strip()


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def jd(o, p):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(o, ensure_ascii=False, indent=2), encoding="utf-8")


def uq(s, n=400):
    o = []
    for x in s:
        if x and x not in o:
            o.append(x)
    return o[:n]


def alt(w, b=True):
    e = "|".join(re.escape(x) for x in sorted(set(w), key=len, reverse=True))
    return re.compile((r"(?<![A-Za-z])(" + e + r")(?![A-Za-z])") if b else "(" + e + ")")


HRE, BRE, HZR, BZR = alt(HE), alt(BE), alt(HZ, False), alt(BZ, False)


def cnt(t, r):
    return [m.group(0).lower() for m in r.finditer(t or "")]


def rt(p):
    b = Path(p).read_bytes()
    for e in ("utf-8-sig", "utf-8", "gb18030", "big5", "cp1252", "latin-1"):
        try:
            return b.decode(e)
        except UnicodeDecodeError:
            pass
    return b.decode("utf-8", "replace")


def walk(o, ks, out):
    if isinstance(o, dict):
        for k, v in o.items():
            if str(k).lower() in ks:
                out.append((k, v))
            walk(v, ks, out)
    elif isinstance(o, list):
        for v in o:
            walk(v, ks, out)


def flat(v):
    if isinstance(v, str):
        return v
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, list):
        return "\n".join(flat(x) for x in v)
    return "\n".join(f"{k}: {flat(x)}" for k, x in v.items()) if isinstance(v, dict) else ""


def trydir(c):
    try:
        c.mkdir(parents=True, exist_ok=True)
        (c / ".w").write_text("1", encoding="utf-8")
        (c / ".w").unlink()
        return True
    except Exception:
        return False


def rin(a):
    cs = ([Path(a)] if a else []) + [Path(x) for x in (os.environ.get("BOHR_INPUT"),
                                                       os.environ.get("INPUT_DIR")) if x] + \
         [Path("/input"), D.parent.parent / "input", Path.cwd() / "input"]
    return next((c for c in cs if c.is_dir() and (c / "case.json").exists()),
                next((c for c in cs if c.is_dir()), None))


def outd(a, work=False):
    n = "work" if work else "output"
    cs = ([Path(a)] if a else []) + [Path(os.environ.get("BOHR_" + n.upper()) or "/app/" + n),
                                     D.parent.parent / n, Path.cwd() / n]
    return next((c for c in cs if trydir(c)), Path.cwd())


def gloss(c):
    hs, out = [], []
    walk(c, {"glossary", "termbase", "terminology", "term_table", "术语表", "terms"}, hs)
    key = lambda g: (g["source"] + "|" + g["target"]).lower()
    for _, v in hs:
        for it in (v if isinstance(v, list) else (list(v.items()) if isinstance(v, dict) else [])):
            s = t = ""
            if isinstance(it, dict):
                s = it.get("source") or it.get("src") or it.get("term") or it.get("en") or ""
                t = it.get("target") or it.get("translation") or ""
            elif isinstance(it, (list, tuple)) and len(it) >= 2:
                s, t = it[0], it[1]
            elif isinstance(it, str) and re.search(r"[:=→]", it):
                s, t = re.split(r"[:=→]", it, maxsplit=1)
            g = {"source": nw(str(s)), "target": nw(str(t))}
            if g["source"] and key(g) not in [key(x) for x in out]:
                out.append(g)
    return out[:120]

def glconf(g):
    m = {}
    for x in g:
        if x["target"]:
            m.setdefault(x["source"].lower(), set()).add(x["target"])
    return [{"term": k, "targets": sorted(v)} for k, v in m.items() if len(v) > 1]


def wo(c):
    hs, out, seen = [], [], set()
    walk(c, {"organizer_workorder", "organizer_edit_workorder", "workorder", "edit_workorder",
             "checklist", "required_actions"}, hs)
    for _, v in hs:
        for it in (v if isinstance(v, list) else [v]):
            t = (it.get("instruction") or it.get("description") or it.get("text")
                 or it.get("requirement") or flat(it)) if isinstance(it, dict) else it
            t = nw(str(t or ""))[:400]
            if t and t.lower() not in seen:
                seen.add(t.lower())
                sc = nw(str(it.get("scope") or ""))[:100] if isinstance(it, dict) else ""
                out.append({"id": "WO%02d" % (len(out) + 1), "text": t, "scope": sc})
    return out[:30]


GENRE = (("response_to_reviewers", r"response to reviewer|rebuttal|审稿意见|回复审稿"),
         ("grant_proposal", r"grant|proposal|基金|申请书|specific aims"),
         ("bilingual_abstract", r"bilingual|中英|双语|中文摘要"),
         ("thesis_chapter", r"thesis|dissertation|学位论文|chapter"),
         ("journal_abstract", r"abstract|摘要"),
         ("journal_article", r"manuscript|journal|paper|论文|投稿"))


def genre(ts):
    t = " ".join(ts).lower()
    return next((n for n, p in GENRE if re.search(p, t)), "journal_article")


def tlang(ts):
    t = " ".join(ts).lower()
    if re.search(r"译成英文|翻译成英文|translate (?:in)?to english|into english|英文版", t):
        return "en"
    if re.search(r"译成中文|翻译成中文|translate (?:in)?to chinese|中文版", t):
        return "zh"
    return ""


def contract(c):
    if not isinstance(c, dict):
        return {}
    for k, v in c.items():
        if str(k).lower() in ("output_contract", "outputcontract", "output_schema", "output_fields"):
            return v
    hs = []
    walk(c, {"output_contract", "outputcontract"}, hs)
    return hs[0][1] if hs else {}


def seg(t, src):
    """Blank-line blocks are paragraphs; hard-wrapped lines are joined; list items stay separate."""
    blocks = [b for b in re.split(r"\n\s*\n", t.replace("\r\n", "\n").replace("\r", "\n")) if nw(b)]
    if len(blocks) == 1:
        lines = [l for l in blocks[0].split("\n") if nw(l)]
        if len(lines) > 3 and sum(l.rstrip().endswith((".", "。", "!", "?"))
                                  for l in lines) >= len(lines) - 1:
            blocks = lines
    ps, sec = [], ""
    for b in blocks:
        lines = [l for l in b.split("\n") if nw(l)]
        while lines and HEAD.match(nw(lines[0])) and len(nw(lines[0])) < 90:
            sec = re.sub(r"^#{1,6}\s*", "", nw(lines[0])).strip("* ")
            ps.append({"kind": "heading", "section": sec, "text": lines[0].rstrip(),
                       "source": src})
            lines = lines[1:]
        if not lines:
            continue
        mk = sum(1 for l in lines if re.match(r"^\s*(?:[-*+]|\d+[.)]|[a-z]\))\s", l))
        units = [[l] for l in lines] if mk >= max(1, len(lines) - 1) else \
            [[" ".join(nw(l) for l in lines)]]
        for u in units:
            ps.append({"kind": "body", "section": sec, "text": u[0].rstrip(), "source": src})
    for i, p in enumerate(ps, 1):
        p["id"] = "P%03d" % i
    return ps


def ftok(t):
    return [re.sub(r"\s+", "", m.group(0)).lower()
            for m in NUM.finditer(XREF.sub(" ", CIT.sub(" ", t or "")))]


def locks(p):
    t = p["text"]
    return {"numbers": uq(ftok(t), 60), "citations": uq([nw(m.group(0)) for m in CIT.finditer(t)], 30),
            "xrefs": uq([nw(m.group(0)) for m in XREF.finditer(t)], 30),
            "hedges": uq(cnt(t, HRE) + cnt(t, HZR), 40),
            "boosters": uq(cnt(t, BRE) + cnt(t, BZR), 40),
            "abbreviations": uq([nw(m.group(1)) for m in DEFAB.finditer(t)], 20)}


def new_result():
    t = now()
    r = {k: [] for k in ("preserved_facts", "evidence_map", "change_log", "glossary", "bilingual",
                         "workorder_receipts", "sources", "uncertainty", "pending_human", "errors",
                         "degradations", "changes")}
    r.update({k: {} for k in ("input", "deliverable", "checks", "coverage", "counts", "output_contract")})
    r.update({"skill": SK, "skill_version": V, "case_id": None, "status": "partial",
              "polished_text": "", "manuscript_path": None, "manuscript_text": "",
              "generated_at": t, "runtime": {"python": sys.version.split()[0], "started_at": t}})
    return r

def find_payload(w, o):
    for d in (w, o, Path("/app/work"), Path.cwd()):
        if Path(d).is_dir():
            for n in ("polish_payload.json", "polish.json", "edits.json"):
                if (Path(d) / n).exists():
                    return Path(d) / n
            hs = sorted(Path(d).glob("*payload*.json")) + sorted(Path(d).glob("*polish*.json"))
            if hs:
                return hs[0]
    return None


def load_payload(p):
    if not p:
        return None, "no payload file found"
    try:
        d = json.loads(Path(p).read_text(encoding="utf-8-sig", errors="replace"))
    except Exception as e:
        return None, "payload parse error: %s" % str(e)[:160]
    return (d, None) if isinstance(d, dict) else (None, "payload is not a JSON object")


def done(res, rp, out, verify):
    try:
        if verify:
            verify.write_outputs(res, out)
        else:
            (out / "manuscript.md").write_text(res.get("manuscript_text") or "", encoding="utf-8")
            res["manuscript_path"] = str(out / "manuscript.md")
    except Exception as e:
        res["degradations"].append({"what": "write_outputs", "detail": str(e)[:140]})
    res["runtime"] = {**(res.get("runtime") or {}), "finished_at": now(),
                      "duration_s": round(time.time() - T0, 2)}
    jd(res, rp)


def main():
    ap = argparse.ArgumentParser(
        prog="main.py", formatter_class=argparse.RawDescriptionHelpFormatter,
        description="writing-02 academic language polish: intake -> workpack -> assemble -> verify",
        epilog="intake|full|finalize; payload work/polish_payload.json (see references/"
               "payload_and_result_schema.md); outputs manuscript.md deliverable.md "
               "change_log.csv result.json; exit 0")
    ap.add_argument("--input", help="input dir")
    ap.add_argument("--output", help="output dir")
    ap.add_argument("--work", help="work dir")
    ap.add_argument("--mode", default="full", choices=["intake", "full", "finalize"])
    ap.add_argument("--payload", help="payload json")
    ap.add_argument("--version", action="version", version=f"{SK} {V}")
    a = ap.parse_args()
    sys.path.insert(0, str(D))
    try:
        import verify
    except Exception:
        verify = None
    out, work = outd(a.output), outd(a.work, True)
    rp = out / "result.json"
    res = new_result()
    res["runtime"]["mode"] = a.mode
    jd(res, rp)
    ct = {}
    try:
        indir = rin(a.input)
        case, cpath = {}, None
        if indir:
            p = indir / "case.json"
            if not p.exists():
                cs = sorted(indir.rglob("case*.json")) or sorted(indir.rglob("*.json"))
                p = cs[0] if cs else None
            if p:
                cpath = p
                try:
                    case = json.loads(p.read_text(encoding="utf-8-sig", errors="replace"))
                except Exception as e:
                    res["errors"].append({"what": "case_json_parse", "detail": str(e)[:240]})
        ct = contract(case)
        res["case_id"] = (case.get("case_id") or case.get("id")) if isinstance(case, dict) else None
        res["input"] = {"dir": str(indir) if indir else None, "mode": a.mode,
                        "case_path": str(cpath) if cpath else None}
        res["output_contract"] = ct
        jd(res, rp)
        if not indir:
            res["status"] = "input_error"
            res["errors"].append({"what": "no_input", "detail": "no /input or --input directory"})
            res["pending_human"].append({"item": "input", "why": "未找到 case.json 与材料目录"})
            return done(res, rp, out, verify)
        ih = []
        walk(case, INSK, ih)
        instr = uq([flat(v) for _, v in ih if nw(flat(v))], 30)
        if not instr and (indir / "task.md").exists():
            instr = [rt(indir / "task.md")[:8000]]
        wo_items, g_in, gn, tl = wo(case), gloss(case), genre(instr), tlang(instr)
        mats, texts, emb, dg = (verify.read_materials(case, indir, cpath, (str(out), str(work)))
                                if verify else ([], [], [], [{"what": "read_materials",
                                                             "detail": "verify.py missing"}]))
        res["sources"] = [{"id": m["name"], "path": m["path"], "kind": m["kind"],
                           "chars": m["chars"], "extraction": m["method"]} for m in mats]
        if not (texts or emb):
            res["status"] = "insufficient_evidence"
            res["errors"].append({"what": "no_text_material", "detail": "no readable manuscript"})
            res["pending_human"].append({"item": "源文本", "why": "未发现可读稿件；无法润色"})
            return done(res, rp, out, verify)
        st = "\n\n".join(t["text"] for t in emb + texts)
        if len(st) > 200000:
            dg.append({"what": "long_input", "detail": "%d chars; inventory capped" % len(st)})
        paras = seg(st, (emb + texts)[0]["name"])
        for p in paras:
            p["locks"] = locks(p)
        have = {g["source"] for g in g_in}
        auto = [{"source": m.group(1), "target": ""} for p in paras
                for m in re.finditer(r"\b([A-Z][a-z]+(?:[- ][A-Z][a-z]+){1,3})\b", p["text"])
                if m.group(1) not in have]
        gl, conf = g_in + uq(auto, 20), glconf(g_in)
        if conf:
            res["pending_human"].append({"item": "术语表内部冲突",
                                         "why": json.dumps(conf, ensure_ascii=False)[:600]})
        jd({"skill": SK, "version": V, "generated_at": now(), "case_id": res["case_id"],
            "genre": gn, "target_language": tl or None, "instruction": instr,
            "workorder": wo_items, "glossary": gl, "conflicts": conf, "paragraphs": paras,
            "material_index": mats, "hedge_lexicon": HE, "booster_lexicon": BE},
           work / "workpack.json")
        pal = work / "polish_payload.json"
        if not pal.exists():
            jd({"case_id": res["case_id"], "skill": SK,
                "instructions_for_agent": "fill paragraphs[].revised and .edits, keep locks; "
                                          "schema in references/payload_and_result_schema.md",
                "paragraphs": [{"id": p["id"], "kind": p["kind"], "revised": "", "edits": [],
                                "unchanged_reason": ""} for p in paras],
                "glossary": gl, "bilingual": [], "workorder_receipts": [], "pending_human": [],
                "uncertainty": [], "notes": ""}, pal)
        res["counts"]["paragraphs"] = len(paras)
        res["degradations"] += dg
        if a.mode == "intake":
            res["pending_human"].append({"item": "润色负载", "why": "intake 模式：仅产出 workpack"})
            return done(res, rp, out, verify)
        if not verify:
            res["degradations"].append({"what": "verify_module", "detail": "verify.py not importable"})
            return done(res, rp, out, verify)
        payload, perr = load_payload(Path(a.payload) if a.payload else find_payload(work, out))
        if perr:
            res["degradations"].append({"what": "payload", "detail": str(perr)[:200]})
            res["pending_human"].append({"item": "润色负载 polish_payload.json",
                                         "why": "未找到可用负载；本次仅产出 workpack 与原文基线。"})
        verify.assemble_payload(res, payload, paras, gl, wo_items, gn, tl, mats)
        res["counts"]["changed_paragraphs"] = res.get("n_changed", 0)
        res["output_contract"] = verify.fill_contract(ct, res) or (ct or {})
        try:
            v = verify.verify_all(res, paras, ct, payload, res)
            res["checks"], res["coverage"] = v["checks"], v["coverage"]
            res["counts"] = {**res["counts"], **v["counts"],
                             "checks_total": len(v["checks"]), "checks_failed": len(v["hard"])}
            hard = v["hard"]
        except Exception as e:
            res["degradations"].append({"what": "verify", "detail": str(e)[:180]})
            res["checks"], hard = {"verification": "unavailable"}, ["verify_unavailable"]
        res["status"] = "partial" if (hard or res["pending_human"] or not payload) else "ok"
        res["uncertainty"] += [{"hard_check_failed": h} for h in hard]
        res["output_contract"] = verify.fill_contract(ct, res) or (ct or {})
        return done(res, rp, out, verify)
    except Exception as e:
        import traceback
        res["errors"].append({"what": "fatal", "detail": repr(e)[:280],
                              "trace": traceback.format_exc()[-800:]})
        if res.get("status") != "input_error":
            res["status"] = "partial"
        try:
            res["output_contract"] = verify.fill_contract(ct, res) or ct or {}
        except Exception:
            pass
        try:
            done(res, rp, out, verify)
        except Exception:
            pass
        return 0


if __name__ == "__main__":
    try:
        sys.exit(main() or 0)
    except SystemExit:
        raise
    except BaseException:
        sys.exit(0)
