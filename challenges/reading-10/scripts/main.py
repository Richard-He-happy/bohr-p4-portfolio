#!/usr/bin/env python3
"""main.py - reproduction / method verification: init | show | check | build.

init : index /input, PRE-declare tolerance, write a legal partial result.json first
show : print material text with locators (--id / --grep)
check: validate /app/work/draft.json (evidence quotes, sections, tolerance widening)
build: run candidate implementations, compare with reported values, attribute the
       differences, write reproduction.md/.json + result.json (always finalizes)
stdlib only, no network, CWD independent, exit code always 0.
"""
import argparse, hashlib, json, os, platform, re, shlex, shutil, subprocess, sys, time, traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify as V

T0, DL = time.time(), time.time() + 780
NUM = r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?"
REQ = ("case_id", "status", "sources", "uncertainty", "pending_human", "errors",
       "degradations", "changes", "runtime")
VER = ("reproduced", "partially_reproduced", "not_reproduced", "insufficient_evidence")
PCL = ("paper", "code_inferred", "chosen")
HINT = ("report", "paper", "expect", "reference", "target", "metric", "result", "accura",
        "score", "f1", "auc", "rmse", "mae", "r2")
now = lambda: time.strftime("%Y-%m-%dT%H:%M:%S%z")
log = lambda s="": print(s, flush=True)
nk = lambda s: re.sub(r"[^a-z0-9]", "", str(s).lower())


def paths():
    P = lambda k, d: Path(os.environ.get(k) or d)
    i, o, w = P("SCIM_INPUT", "/input"), P("SCIM_OUTPUT", "/app/output"), P("SCIM_WORK", "/app/work")
    if not i.exists():
        i = next((c for c in (Path.cwd() / "input", Path("/bohr-workspace/input")) if c.is_dir()), i)
    for d in (o, w):
        try:
            d.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
    return i, o, w


def load_case(i):
    for c in [i / "case.json"] + sorted(i.rglob("case*.json")):
        if c.is_file():
            o, e = V.load_json(c)
            return (o if isinstance(o, dict) else {}), c, (None if isinstance(o, dict) else (e or "bad_case_json"))
    return {}, None, "case_json_not_found"


def idx_build(inp):
    ms, used = [], set()
    for p in sorted(inp.rglob("*")):
        if not p.is_file() or p.name == "case.json":
            continue
        b = re.sub(r"[^0-9A-Za-z_]+", "_", p.stem).strip("_") or "mat"
        mid, k = b, 1
        while mid in used:
            k += 1
            mid = "%s%d" % (b, k)
        used.add(mid)
        sz = p.stat().st_size
        if sz > 25 << 20:
            ms.append(dict(id=mid, path=str(p), rel=str(p.relative_to(inp)), kind="skipped", bytes=sz,
                           units=[], quality="skipped", sha1=None, notes=[">25MB"]))
            continue
        m = V.extract_material(p, str(p.relative_to(inp)), mid)
        m.update(id=mid, sha1=hashlib.sha1(p.read_bytes()).hexdigest()[:10])
        ms.append(m)
    return {"root": str(inp), "generated_at": now(), "materials": ms}


def rep_vals(case):
    """reported metric values from case.json; the JSON pointer is the locator"""
    out = {}

    def walk(n, path):
        if isinstance(n, dict):
            m, v = n.get("metric") or n.get("name"), n.get("value", n.get("reported"))
            if isinstance(m, str) and isinstance(v, (int, float)) and not isinstance(v, bool):
                out[m] = {"value": v, "ptr": "/".join(path), "source": "case.json#metric_value"}
            for k, x in n.items():
                walk(x, path + [str(k)])
        elif isinstance(n, list):
            for i, x in enumerate(n):
                walk(x, path + [str(i)])
        elif isinstance(n, (int, float)) and not isinstance(n, bool):
            j = "/".join(path).lower()
            if any(t in j for t in ("toler", "budget", "seed", "limit")) or not any(t in j for t in HINT):
                return
            leaf = str(path[-1]).lower()
            nm = str(path[-2]) if len(path) > 1 and (re.fullmatch(NUM, leaf) or
                                                     leaf in ("value", "val", "score")) else str(path[-1])
            out.setdefault(nm, {"value": n, "ptr": "/".join(path), "source": "case.json#/" + "/".join(path)})

    walk(case, [])
    return out


def tol_plan(case, rep):
    ent = {n: dict(V.prior_tolerance(n, r.get("value")), declared_at=now(), declared_step="init")
           for n, r in rep.items()}
    decl = []

    def walk(n):
        if isinstance(n, dict):
            k = n.get("metric") or n.get("name")
            a = next((n[x] for x in ("abs_tol", "abs", "atol") if isinstance(n.get(x), (int, float))), None)
            r = next((n[x] for x in ("rel_tol", "rel", "rtol") if isinstance(n.get(x), (int, float))), None)
            if isinstance(k, str) and (a is not None or r is not None):
                e = dict(ent.get(k) or V.prior_tolerance(k, None))
                if a is not None:
                    e["abs_tol"] = float(a)
                if r is not None:
                    e["rel_tol"] = float(r)
                ent[k] = dict(e, basis="case_declared", declared_at=now(), declared_step="init",
                              source="case_declared")
                decl.append(k)
            for x in n.values():
                walk(x)
        elif isinstance(n, list):
            for x in n:
                walk(x)

    walk(case)
    return {"declared_at": now(), "declared_step": "init", "before_any_run": True,
            "source": "case_declared+prior_default" if decl else "prior_default", "entries": ent}


def tol_for(m, plan, rv):
    for n, e in (plan.get("entries") or {}).items():
        if nk(n) == nk(m):
            return {k: e.get(k) for k in ("abs_tol", "rel_tol", "basis", "declared_step")}
    return dict(V.prior_tolerance(m, rv), declared_step="init")


def cands(inp, case):
    out = []
    for key in ("candidates", "implementations", "candidate_methods", "methods", "code_variants"):
        v = case.get(key)
        for i, e in enumerate(v if isinstance(v, list) else []):
            if isinstance(e, dict) and (e.get("command") or e.get("entry") or e.get("path")):
                out.append(dict(name=str(e.get("name") or "cand%d" % (i + 1)), command=e.get("command"),
                                path=str(e.get("entry") or e.get("path") or ""), declared=True, score=9))
    if out:
        return out[:4]
    for p in sorted(inp.rglob("*.py")):
        dn = [x.lower() for x in p.relative_to(inp).parts[:-1]]
        nm = p.stem.lower()
        s = 1 if any(h in nm for h in ("cand", "impl", "method", "baseline", "variant", "solution")) else 0
        s += 2 if any(h in dn for h in ("candidate", "candidates", "impl", "implementation", "code",
                                        "src", "repo", "method", "methods", "baseline")) else 0
        if not s and not re.match(r"(setup|conftest|test_|__)|_(test|setup)$", nm):
            s = 0.5
        if s:
            out.append(dict(name=nm, path=str(p), command=None, declared=False, score=s))
    out.sort(key=lambda x: (-x["score"], x["name"]))
    uniq = {}
    for c in out:
        uniq.setdefault(c["name"], c)
    return list(uniq.values())[:4]


def metrics(t):
    def fl(o, d, pre=""):
        if isinstance(o, dict):
            for k, v in o.items():
                fl(v, d, (pre + "." + str(k)) if pre else str(k))
        elif isinstance(o, list):
            for i, v in enumerate(o[:40]):
                fl(v, d, "%s[%d]" % (pre, i))
        elif isinstance(o, (int, float)) and not isinstance(o, bool):
            d[pre] = o

    t = (t or "").strip()
    blobs = [t] if t.startswith("{") else [x.strip() for x in t.splitlines()[-40:]
                                           if x.strip().startswith("{") and x.strip().endswith("}")][:1]
    for b in blobs:
        d = {}
        try:
            fl(json.loads(b), d)
        except Exception:
            d = {}
        if d:
            return d
    d = {}
    for line in t.splitlines():
        m = re.match(r"^\s*[-*]?\s*([A-Za-z_][\w .%/+\-]{0,40}?)\s*[=:,\t|]\s*(%s)\s*%%?\s*$" % NUM, line)
        if m:
            d.setdefault(re.sub(r"\s+", "_", m.group(1).strip().lower()), float(m.group(2)))
    return d


def run(it, w, extra, timeout):
    rd = w / "runs" / (re.sub(r"[^0-9A-Za-z_]+", "_", it["name"]).strip("_")[:40] or "cand")
    shutil.rmtree(rd, ignore_errors=True)
    rd.mkdir(parents=True, exist_ok=True)
    rec = dict(name=it["name"], declared=it.get("declared", False), workdir=str(rd), metrics={},
               exit_code=None)
    env = dict(os.environ, PYTHONHASHSEED="0", MPLBACKEND="Agg", PYTHONDONTWRITEBYTECODE="1",
               **(extra or {}))
    t = time.time()
    try:
        if it.get("command"):
            cmd = it["command"] if isinstance(it["command"], list) else shlex.split(str(it["command"]))
            rec["source"] = "declared_command"
        else:
            src = Path(it["path"])
            shutil.copytree(src.parent, rd, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc", ".venv"))
            if not (rd / src.name).exists():
                rec["error"] = "file_missing_after_copy"
                return rec
            cmd = [sys.executable, "-B", str(rd / src.name)]
            rec["source"] = str(src)
        rec["command"] = cmd
        before = {str(p.relative_to(rd)) for p in rd.rglob("*") if p.is_file()}
        r = subprocess.run(cmd, cwd=str(rd), capture_output=True, text=True, timeout=timeout,
                           env=env, errors="replace")
        rec.update(exit_code=r.returncode, stdout_tail=V.snip(r.stdout, 1400),
                   stderr_tail=V.snip(r.stderr, 500), metrics=metrics(r.stdout))
        rec["outputs"] = sorted({str(p.relative_to(rd)) for p in rd.rglob("*")
                                 if p.is_file() and str(p.relative_to(rd)) not in before})[:12]
    except subprocess.TimeoutExpired:
        rec["error"] = "timeout_%ss" % timeout
    except Exception as exc:
        rec["error"] = "%s:%s" % (type(exc).__name__, exc)
    rec["duration_s"] = round(time.time() - t, 2)
    return rec


def compare(runs, rep, plan):
    rows, ik = [], {nk(k): v for k, v in rep.items()}
    for mn in dict.fromkeys([k for r in runs for k in (r.get("metrics") or {})]):
        hit = ik.get(nk(mn)) or next((v for k, v in ik.items() if nk(mn) and (nk(mn) in k or k in nk(mn))),
                                    None)
        rv = hit.get("value") if hit else None
        t = tol_for(mn, plan, rv)
        for r in runs:
            ob = (r.get("metrics") or {}).get(mn)
            if ob is None:
                continue
            c = V.compare_values(ob, rv, t["abs_tol"], t["rel_tol"]) if rv is not None else {}
            wt = c.get("within_tolerance")
            rows.append(dict(metric=mn, run=r["name"], observed=ob, reported=rv, abs_tol=t["abs_tol"],
                             rel_tol=t["rel_tol"], tolerance_basis=t["basis"],
                             reported_source=hit.get("source") if hit else None,
                             abs_dev=c.get("abs_dev"), rel_dev=c.get("rel_dev"), within_tolerance=wt,
                             verdict={True: "in_tolerance", False: "out_of_tolerance"}.get(
                                 wt, "no_reported_value")))
    return rows


def attrib(rows):
    out, by = [], {}
    for r in rows:
        by.setdefault(r["metric"], []).append(r)
    for m, rs in by.items():
        rv = next((r["reported"] for r in rs if r["reported"] is not None), None)
        miss = [r for r in rs if r["within_tolerance"] is False]
        if rv is None:
            out.append(dict(metric=m, cause="paper_value_unavailable", confidence="determined",
                            detail="no reported value; consistency undecidable"))
        elif not miss:
            out.append(dict(metric=m, cause="none", confidence="determined",
                            detail="all observations inside pre-declared tolerance"))
        else:
            obs = [r["observed"] for r in rs]
            ref = max([r["rel_tol"] or 0 for r in rs] + [0.02])
            sp = (max(obs) - min(obs)) if len(obs) > 1 else 0.0
            if len(obs) > 1 and sp <= abs(rv) * ref:
                out.append(dict(metric=m, cause="shared_upstream_factor", confidence="inferred",
                                detail="candidates agree (spread %.6g) but miss %.6g: data/split, params, env"
                                       % (sp, rv)))
            elif len(obs) > 1:
                out.append(dict(metric=m, cause="implementation", confidence="inferred",
                                detail="candidates disagree (spread %.6g > tolerance)" % sp))
            else:
                out.append(dict(metric=m, cause="unverified_single_implementation", confidence="inferred",
                                detail="only one candidate produced numbers"))
    return out


def findings(d, units):
    """verify params/claims quotes against the index; return (params, claims, evidence)"""
    params, claims, evid = [], [], []
    for p in d.get("params") or []:
        ev = p.get("evidence") or {}
        ok, hits, why = V.check_evidence(units, ev)
        params.append(dict(name=p.get("name"), value=p.get("value"), klass=p.get("class"),
                           source=p.get("source"),
                           locator=hits[0]["locator"] if hits else ev.get("locator"),
                           quote=ev.get("quote"), verified=ok, check=why))
    for c in d.get("claims") or []:
        evs = []
        for ev in c.get("evidence") or []:
            ok, hits, why = V.check_evidence(units, ev)
            evs.append(dict(source_id=hits[0]["source_id"] if hits else ev.get("source_id"),
                            locator=hits[0]["locator"] if hits else ev.get("locator"),
                            quote=ev.get("quote"), verified=ok, check=why))
        claims.append(dict(id=c.get("id"), kind=c.get("kind"), text=c.get("text"),
                           confidence=c.get("confidence"), evidence=evs))
        evid += [dict(e, claim=c.get("id")) for e in evs if e["verified"]]
    return params, claims, evid


def envsnap(d, se):
    pk = {}
    for n in ("numpy", "pandas", "scipy", "sklearn", "matplotlib"):
        try:
            pk[n] = getattr(__import__(n), "__version__", "?")
        except Exception:
            pass
    return dict(python=d.get("python") or platform.python_version(),
                platform=d.get("platform") or platform.platform(),
                packages=d.get("packages") or pk, seed=d.get("seed") or se.get("SEED"),
                snapshot_source="draft+host" if d else "host")


def emit(out, res):
    for k in REQ:
        res.setdefault(k, None if k in ("case_id", "status", "runtime") else [])
    res["runtime"] = dict(started_at=time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(T0)),
                          finished_at=now(), elapsed_s=round(time.time() - T0, 2),
                          python=platform.python_version(), platform=platform.platform(),
                          budget_s=780, deadline_hit=time.time() > DL, **(res.get("runtime") or {}))
    V.dump_json(out / "result.json", res)


def shell(case, cid):
    res = dict(case_id=cid, status="partial", summary="", sources=[], uncertainty=[], pending_human=[],
               errors=[], degradations=[], changes=[], runtime={})
    con = case.get("output_contract") if isinstance(case, dict) else None
    if isinstance(con, dict):
        un = []
        res = {**V.fill_contract(con, res, un), **res}
        if un:
            res["degradations"].append("contract_field_unmapped:" + ",".join(sorted(set(un))))
    return res


DRAFT = {"_note": "skeleton, example only (not a formal case result); fill and save as draft.json",
         "case_id": None, "paper": {"title": None, "doi": None, "repo": None, "commit": None},
         "plan": [{"step": 1, "goal": "", "command": None, "expected": None, "status": "pending"}],
         "environment": {"python": None, "platform": None, "packages": {}, "seed": None},
         "params": [{"name": "", "value": None, "class": "paper|code_inferred|chosen", "source": "",
                     "evidence": {"source_id": "", "locator": "", "quote": ""}}],
         "paper_values": [{"metric": "", "value": None, "unit": None,
                           "evidence": {"source_id": "", "locator": "", "quote": ""}}],
         "tolerance": [{"metric": "", "abs_tol": None, "rel_tol": None, "basis": "",
                        "declared_step": "plan"}],
         "claims": [{"id": "c1", "kind": "paper_result|method|param|environment", "text": "",
                     "confidence": "direct|inferred|undetermined",
                     "evidence": [{"source_id": "", "locator": "", "quote": ""}]}],
         "attribution": [], "pending_human": [],
         "conclusion": {"verdict": "reproduced|partially_reproduced|not_reproduced|insufficient_evidence",
                        "reason": ""}}


def ctx():
    inp, out, w = paths()
    case, cp, cerr = load_case(inp)
    idx, _ = V.load_json(w / "index.json")
    if idx is None:
        idx = idx_build(inp)
        V.dump_json(w / "index.json", idx)
    return inp, out, w, case, cp, cerr, (case.get("case_id") or case.get("id")), idx


def do_init(a):
    inp, out, w = paths()
    case, cp, err = load_case(inp)
    cid = case.get("case_id") or case.get("id")
    r0 = shell(case, cid)
    r0["summary"] = "init placeholder"
    emit(out, r0)
    idx = idx_build(inp)
    plan = tol_plan(case, rep_vals(case))
    V.dump_json(w / "index.json", idx)
    V.dump_json(w / "tolerance_plan.json", plan)
    V.dump_json(w / "draft_skeleton.json", dict(DRAFT, case_id=cid))
    src = [{k: m.get(k) for k in ("id", "rel", "kind", "bytes", "quality", "sha1")} for m in idx["materials"]]
    res = shell(case, cid)
    res.update(summary="init: %d materials, %d units" % (len(idx["materials"]),
                                                         sum(len(m["units"]) for m in idx["materials"])),
               sources=src, pending_human=["run build for the reproduction record"],
               degradations=["partial_written_at_init"])
    if err:
        res.update(status="input_error", errors=[err])
    emit(out, res)
    log("== init ==\ninput=%s work=%s output=%s\ncase=%s parse=%s case_id=%s"
        % (inp, w, out, cp, "ok" if not err else err, cid))
    log("\n[materials] %d" % len(idx["materials"]))
    units = []
    for m in idx["materials"]:
        log("  %-16s %-6s %8dB units=%-4d %s" % (m["id"], m["kind"], m["bytes"], len(m["units"]), m["quality"]))
        units += m["units"]
    log("\n[units]")
    for loc, txt in units[:a.preview]:
        log("  %s | %s" % (loc, V.snip(txt, 110)))
    log("\n[workorder]")
    for k in ("task_instruction", "instruction", "task", "organizer_workorder", "requirements", "scope"):
        v = case.get(k)
        if v:
            log("  %s: %s" % (k, V.snip(json.dumps(v, ensure_ascii=False)
                                       if isinstance(v, (dict, list)) else str(v), 360)))
    log("\n[tolerance] %d entries, before_any_run=%s, source=%s"
        % (len(plan["entries"]), plan["before_any_run"], plan["source"]))
    for k, e in list(plan["entries"].items())[:8]:
        log("  %-18s abs=%s rel=%s [%s]" % (k, e.get("abs_tol"), e.get("rel_tol"), e["basis"]))
    log("\n[next] 1) show --id %s\n       2) write %s\n       3) check\n       4) build"
        % (idx["materials"][0]["id"] if idx["materials"] else "MAT", w / "draft.json"))


def do_show(a):
    inp, out, w = paths()
    idx, _ = V.load_json(w / "index.json")
    if idx is None:
        idx = idx_build(inp)
        V.dump_json(w / "index.json", idx)
    ms = [m for m in idx["materials"] if not a.id or a.id in (m["id"], m["rel"])]
    if not ms:
        log("no match --id=%s; ids: %s" % (a.id, ", ".join(m["id"] for m in idx["materials"])))
        return
    n = 0
    for m in ms:
        log("\n### %s (%s, %dB, %s)" % (m["id"], m["kind"], m["bytes"], m["quality"]))
        for loc, txt in m["units"]:
            if a.grep and a.grep.lower() not in txt.lower():
                continue
            n += 1
            if n > a.limit:
                log("... --limit=%d reached" % a.limit)
                return
            log("%s | %s" % (loc, txt[:a.chars]))
    log("\nprinted %d units" % n)


def do_check(a):
    inp, out, w, case, cp, cerr, cid, idx = ctx()
    units = V.flat_units(idx)
    plan, _ = V.load_json(w / "tolerance_plan.json")
    plan = plan or {"entries": {}}
    draft, _ = V.load_json(w / "draft.json")
    d = draft if isinstance(draft, dict) else {}
    errs, warns, okc, rej, wide = [], [], 0, 0, 0
    if not d:
        errs.append("draft_missing:%s" % (w / "draft.json"))
        if (w / "draft.md").exists():
            warns.append("draft_markdown_only: not structurally checkable")
    for k in ("paper", "plan", "params", "claims", "conclusion"):
        if not d.get(k):
            (errs if k in ("params", "claims", "conclusion") else warns).append("draft_section_empty:" + k)
    for c in d.get("claims") or []:
        i = str(c.get("id") or "?")
        if not str(c.get("text") or "").strip():
            errs.append("claim_text_empty:" + i)
        if c.get("confidence") not in ("direct", "inferred", "undetermined"):
            errs.append("claim_confidence_invalid:" + i)
        if not c.get("evidence"):
            errs.append("claim_without_evidence:" + i)
        for ev in c.get("evidence") or []:
            ok, hits, why = V.check_evidence(units, ev)
            if ok:
                okc += 1
                if why == "locator_differs_from_index":
                    warns.append("locator_mismatch:%s->%s" % (i, hits[0]["locator"]))
            else:
                rej += 1
                errs.append("evidence_rejected:%s:%s:%s" % (i, why, V.snip(str(ev.get("quote")), 60)))
    for p in d.get("params") or []:
        if p.get("class") not in PCL:
            errs.append("param_class_invalid:%s" % p.get("name"))
        if p.get("value") in (None, ""):
            warns.append("param_value_empty:%s" % p.get("name"))
        if p.get("class") == "paper" and not (p.get("evidence") or {}).get("quote"):
            errs.append("paper_param_without_quote:%s" % p.get("name"))
    pk = {nk(k): v for k, v in (plan.get("entries") or {}).items()}
    for t in d.get("tolerance") or []:
        base = pk.get(nk(t.get("metric")))
        if not base:
            warns.append("tolerance_not_predeclared:%s" % t.get("metric"))
            continue
        for f in ("abs_tol", "rel_tol"):
            dv, pv = t.get(f), base.get(f)
            if isinstance(dv, (int, float)) and isinstance(pv, (int, float)) and dv > pv * (1 + 1e-9):
                wide += 1
                errs.append("tolerance_widened_after_run:%s:%s>%s" % (t.get("metric"), dv, pv))
    if (d.get("conclusion") or {}).get("verdict") not in VER + (None,):
        errs.append("conclusion_verdict_invalid")
    if not (d.get("paper_values") or d.get("tolerance")):
        warns.append("no_reported_paper_values: build falls back to case.json")
    cnt = dict(claims=len(d.get("claims") or []), evidence_ok=okc, evidence_rejected=rej,
               params=len(d.get("params") or []), tolerance_entries=len(d.get("tolerance") or []),
               tolerance_widened=wide)
    V.dump_json(w / "check_report.json", {"draft": str(w / "draft.json"), "errors": errs,
                                          "warnings": warns, "counts": cnt, "pass": not errs})
    log("== check %s ==" % ("PASS" if not errs else "FAIL"))
    log("claims=%(claims)d ok=%(evidence_ok)d rejected=%(evidence_rejected)d params=%(params)d "
        "tol=%(tolerance_entries)d widened=%(tolerance_widened)d" % cnt)
    for e in errs[:25]:
        log("  ERROR " + e)
    for x in warns[:25]:
        log("  WARN  " + x)
    log("report: %s" % (w / "check_report.json"))


def do_build(a):
    inp, out, w, case, cp, cerr, cid, idx = ctx()
    pre = shell(case, cid)
    pre["summary"] = "build in progress"
    emit(out, pre)
    units = V.flat_units(idx)
    errs, deg, pend, unc = ([cerr] if cerr else []), [], [], []
    plan, _ = V.load_json(w / "tolerance_plan.json")
    rep = rep_vals(case)
    plan = plan or tol_plan(case, rep)
    raw, _ = V.load_json(w / "draft.json")
    d = raw if isinstance(raw, dict) else {}
    for pv in d.get("paper_values") or []:
        if pv.get("metric") and isinstance(pv.get("value"), (int, float)):
            ev = pv.get("evidence") or {}
            rep[str(pv["metric"])] = dict(value=pv["value"], ptr=ev.get("locator"),
                                          source="draft.paper_values:" + str(ev.get("locator") or ""))
    envc = case.get("environment") if isinstance(case.get("environment"), dict) else {}
    seed = next((case.get(k, envc.get(k)) for k in ("seed", "random_seed", "SEED")
                 if isinstance(case.get(k, envc.get(k)), (int, str))), None)
    se = {"PYTHONHASHSEED": str(seed), "SEED": str(seed)} if seed is not None else {}
    runs = []
    for it in cands(inp, case):
        left = DL - time.time()
        if left < 60:
            deg.append("run_skipped_deadline:" + it["name"])
            pend.append("candidate %s skipped: time budget" % it["name"])
            continue
        r = run(it, w, se, min(150, max(20, int(left - 30))))
        runs.append(r)
        if r.get("exit_code") != 0:
            deg.append("run_failed:" + r["name"])
            pend.append("candidate %s failed (exit=%s)" % (r["name"], r.get("exit_code")))
        elif not r.get("metrics"):
            unc.append("candidate %s produced no parseable metric" % r["name"])
    if not runs:
        deg.append("no_run_or_no_candidate")
        pend.append("no candidate finished; run manually and fill runs")
    rows = compare(runs, rep, plan)
    if not rows:
        deg.append("no_comparison_rows")
    params, claims, evid = findings(d, units)
    for p in params:
        if not p["verified"] and p["klass"] == "paper":
            unc.append("param %s claimed paper-stated but its quote is not in the materials" % p.get("name"))
    dens = d.get("environment") or {}
    env = envsnap(dens, se)
    if not dens:
        deg.append("environment_from_host_only")
        unc.append("environment snapshot from host, not matched against paper claims")
    attribs = attrib(rows) + [x for x in (d.get("attribution") or []) if isinstance(x, dict)]
    soft = [p.get("name") for p in params if p["klass"] in ("chosen", "code_inferred")]
    if soft:
        attribs.append(dict(metric="*", cause="parameter_restoration", confidence="inferred",
                            detail="%d params not paper-stated: %s" % (len(soft), ", ".join(map(str, soft[:5])))))
    evid += [dict(claim="comparison:" + r["metric"], locator=r["reported_source"], quote=None,
                  verified=True, check="source_pointer") for r in rows if r["reported_source"]]
    if not runs:
        verdict, reason = "insufficient_evidence", "no candidate ran successfully"
    else:
        j = [r for r in rows if r["within_tolerance"] is not None]
        g = [r for r in j if r["within_tolerance"]]
        if not j:
            verdict, reason = "insufficient_evidence", "runs produced no comparable reported value"
        elif len(g) == len(j):
            verdict, reason = "reproduced", "all %d observations inside pre-declared tolerance" % len(j)
        elif g:
            verdict, reason = "partially_reproduced", "%d/%d in tolerance; rest attributed" % (len(g), len(j))
        else:
            verdict, reason = "not_reproduced", "all %d observations outside tolerance" % len(j)
    dc = d.get("conclusion") or {}
    if dc.get("verdict") in VER:
        if dc["verdict"] != verdict:
            deg.append("verdict_conflict:agent=%s:computed=%s" % (dc["verdict"], verdict))
            unc.append("agent verdict %s vs computed %s; computed kept" % (dc["verdict"], verdict))
        if dc.get("reason"):
            reason = "%s (agent: %s)" % (reason, V.snip(str(dc["reason"]), 260))
    else:
        pend.append("draft has no verdict; computed verdict needs agent review")
    for m in idx["materials"]:
        if m.get("quality") != "ok":
            deg.append("material_quality:%s:%s" % (m["id"], m["quality"]))
        if m.get("kind") in ("image", "skipped", "zip", "pptx"):
            pend.append("material %s (%s) not content-parsed" % (m["id"], m["kind"]))
    if not d:
        deg.append("no_draft:deterministic_minimal_delivery")
        pend.append("draft missing: plan/params/claims are script-minimal; fill draft.json and rerun")
    tl = [dict(v, metric=k) for k, v in (plan.get("entries") or {}).items()]
    cnt = dict(materials=len(idx["materials"]), runs=len(runs),
               runs_ok=sum(1 for r in runs if r.get("exit_code") == 0), comparison_rows=len(rows),
               in_tolerance=sum(1 for r in rows if r["within_tolerance"] is True),
               out_of_tolerance=sum(1 for r in rows if r["within_tolerance"] is False),
               no_reported_value=sum(1 for r in rows if r["within_tolerance"] is None),
               claims_verified=sum(1 for c in claims for e in c["evidence"] if e["verified"]),
               claims_rejected=sum(1 for c in claims for e in c["evidence"] if not e["verified"]),
               params=len(params), tolerance_entries=len(tl))
    status = "ok"
    if cerr:
        status = "input_error"
    elif not runs or verdict == "insufficient_evidence":
        status = "insufficient_evidence"
    if pend or deg:
        status = "partial" if status == "ok" else status
    summ = ("verdict %s; %d runs, %d rows (in %d / out %d / n.a. %d)"
            % (verdict, len(runs), len(rows), cnt["in_tolerance"], cnt["out_of_tolerance"],
               cnt["no_reported_value"]))
    rec = dict(case_id=cid, status=status, summary=summ, generated_at=now(),
               scope=V.snip(str(case.get("task_instruction") or case.get("organizer_supplied_scope")
                                or "locate method -> env -> params -> run -> compare -> attribute"), 600),
               paper=d.get("paper") or {},
               materials=[dict(id=m["id"], rel=m["rel"], kind=m["kind"], bytes=m["bytes"],
                               sha1=m.get("sha1"), units=len(m["units"]), quality=m["quality"],
                               notes=m.get("notes") or []) for m in idx["materials"]],
               environment=env, tolerance_plan=plan, params=params,
               plan=d.get("plan") or [dict(step=i + 1, goal=g, status="done") for i, g in
                                      enumerate(("locate materials", "pre-declare tolerance",
                                                 "run candidates", "compare and attribute", "conclude"))],
               runs=runs, comparison=rows, attribution=attribs, tolerance=tl, claims=claims,
               evidence=evid, sources=[dict(id=m["id"], path=m["path"], kind=m["kind"], bytes=m["bytes"],
                                            sha1=m.get("sha1"), locator_style="p<i>|#h/p<i>|r<i>|#/ptr")
                                       for m in idx["materials"]],
               uncertainty=unc, pending_human=sorted(set(pend)), gaps=sorted(set(pend)),
               errors=errs, degradations=sorted(set(deg)), counts=cnt,
               artifacts=dict(reproduction_md=str(out / "reproduction.md"),
                              reproduction_json=str(out / "reproduction.json"),
                              runs_dir=str(w / "runs"), index=str(w / "index.json"),
                              tolerance_plan=str(w / "tolerance_plan.json")),
               changes=[dict(at=now(), change="build wrote reproduction record and filled contract"),
                        dict(at=plan.get("declared_at"),
                             change="init pre-declared %d tolerance entries" % len(tl))],
               conclusion=dict(verdict=verdict, reason=reason,
                               basis="all in tolerance=reproduced; some=partially_reproduced; "
                                     "none=not_reproduced; no run/value=insufficient_evidence"))
    V.dump_json(out / "reproduction.json", rec)
    V.write_text(out / "reproduction.md", render(rec))
    con = case.get("output_contract") if isinstance(case.get("output_contract"), dict) else {}
    un = []
    feed = dict(rec)  # semantic slot for contract keys such as reproduction_record
    feed["reproduction"] = {k: rec[k] for k in ("case_id", "generated_at", "scope", "paper",
                                                "materials", "environment", "tolerance_plan", "params",
                                                "plan", "runs", "comparison", "attribution", "claims",
                                                "conclusion", "counts", "gaps", "degradations")}
    res = V.fill_contract(con, feed, un) if con else {}
    res.update(rec)
    if un:
        res["degradations"] = sorted(set(res["degradations"]) | {"contract_field_unmapped:"
                                                                + ",".join(sorted(set(un)))})
    emit(out, res)
    log("== build ==\nruns %d (ok %d)" % (len(runs), cnt["runs_ok"]))
    for r in runs:
        log("  %-16s exit=%s %.2fs metrics=%d" % (r["name"], r.get("exit_code"),
                                                  r.get("duration_s") or 0, len(r.get("metrics") or {})))
    log("rows %d in=%d out=%d n.a.=%d" % (len(rows), cnt["in_tolerance"], cnt["out_of_tolerance"],
                                          cnt["no_reported_value"]))
    for r in rows[:20]:
        log("  %-14s %-16s obs=%s rep=%s dev=%s -> %s"
            % (r["run"], r["metric"], r["observed"], r["reported"], r["rel_dev"], r["verdict"]))
    log("verdict %s | status %s\nresult.json -> %s" % (verdict, status, out / "result.json"))


def render(r):
    L = ["# Reproduction and method-verification record\n",
         "- case_id: `%s` | generated: %s" % (r.get("case_id"), r.get("generated_at")),
         "- conclusion: **%s** - %s" % (r["conclusion"]["verdict"], r["conclusion"]["reason"]),
         "- scope: %s\n" % r.get("scope")]

    def T(head, rows):
        L.append("| " + " | ".join(head) + " |")
        L.append("|" + "---|" * len(head))
        L.extend("| " + " | ".join("" if c is None else str(c).replace("|", "/") for c in row) + " |"
                 for row in rows)
        L.append("")

    L.append("## 1. Materials and locators\n")
    T(["id", "file", "kind", "bytes", "units", "quality", "sha1"],
      [[m["id"], m["rel"], m["kind"], m["bytes"], m["units"], m["quality"], m["sha1"] or "-"]
       for m in r["materials"]])
    notes = [n for m in r["materials"] for n in (m.get("notes") or [])]
    if notes:
        L.append("Parse notes: " + "; ".join(notes) + "\n")
    L.append("## 2. Environment snapshot\n```json\n"
             + json.dumps(r["environment"], ensure_ascii=False, indent=2) + "\n```\n")
    L.append("## 3. Parameter restoration\n")
    if r["params"]:
        T(["param", "value", "class", "source", "locator", "quote check"],
          [[p.get("name"), p.get("value"), p.get("klass"), p.get("source"), p.get("locator"),
            "ok" if p.get("verified") else p.get("check")] for p in r["params"]])
    else:
        L.append("_No parameter table in draft; see section 8._\n")
    L.append("## 4. Pre-declared tolerance\n")
    L.append("step `%s`, time `%s`, before any run = `%s`, source `%s`.\n"
             % (r["tolerance_plan"].get("declared_step"), r["tolerance_plan"].get("declared_at"),
                r["tolerance_plan"].get("before_any_run"), r["tolerance_plan"].get("source")))
    T(["metric", "abs_tol", "rel_tol", "basis"],
      [[k, v.get("abs_tol"), v.get("rel_tol"), v.get("basis")]
       for k, v in (r["tolerance_plan"].get("entries") or {}).items()])
    L.append("## 5. Runs\n")
    for x in r["runs"]:
        L.append("### %s\n" % x["name"])
        L.append("- command: `%s`" % (" ".join(map(str, x.get("command") or [])) or "-"))
        L.append("- workdir: `%s` | exit: %s | %ss" % (x.get("workdir"), x.get("exit_code"),
                                                      x.get("duration_s")))
        if x.get("error"):
            L.append("- error: `%s`" % x["error"])
        L.append("- metrics: `%s`\n" % json.dumps(x.get("metrics") or {}, ensure_ascii=False))
        if x.get("stdout_tail"):
            L.append("```text\n" + x["stdout_tail"][:700] + "\n```\n")
    if not r["runs"]:
        L.append("_No candidate implementation started; see section 8._\n")
    L.append("## 6. Result comparison (pre-declared tolerance)\n")
    if r["comparison"]:
        T(["run", "metric", "observed", "reported", "rel_dev", "rel_tol", "verdict", "reported source"],
          [[x["run"], x["metric"], x["observed"], x["reported"], x["rel_dev"], x["rel_tol"],
            x["verdict"], x["reported_source"]] for x in r["comparison"]])
    else:
        L.append("_No comparable numeric pairs._\n")
    L.append("## 7. Difference attribution\n")
    T(["metric", "cause", "confidence", "detail"],
      [[x.get("metric"), x.get("cause"), x.get("confidence"), x.get("detail")] for x in r["attribution"]])
    L.append("## 8. Gaps, degradations, handover\n")
    L.extend("- gap: %s" % g for g in (r["gaps"] or ["(none)"]))
    L.append("")
    L.extend("- degraded: %s" % g for g in (r["degradations"] or ["(none)"]))
    L.append("\n## 9. Evidence\n")
    rows = [[c.get("id"), e.get("source_id"), e.get("locator"), V.snip(str(e.get("quote")), 90),
             "ok" if e.get("verified") else e.get("check")]
            for c in r["claims"] for e in c["evidence"]][:120]
    if rows:
        T(["claim", "source", "locator", "quote", "check"], rows)
    else:
        L.append("_No quoted evidence._\n")
    L.append("## 10. Conclusion\n")
    L.extend(["- graded verdict: **%s**" % r["conclusion"]["verdict"],
              "- basis: %s" % r["conclusion"]["reason"],
              "- rule: %s" % r["conclusion"]["basis"],
              "- counts: `%s`\n" % json.dumps(r["counts"], ensure_ascii=False)])
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(
        description="Reproduction & method verification: init | show | check | build. stdlib, exit 0.",
        epilog="flow: init -> (agent writes /app/work/draft.json) -> check -> build")
    sp = ap.add_subparsers(dest="cmd")
    p0 = sp.add_parser("init", help="index /input, pre-declare tolerance, write partial result")
    p0.add_argument("--preview", type=int, default=10)
    p1 = sp.add_parser("show", help="print material text with locators")
    p1.add_argument("--id")
    p1.add_argument("--grep")
    p1.add_argument("--limit", type=int, default=80)
    p1.add_argument("--chars", type=int, default=600)
    sp.add_parser("check", help="validate draft.json: quotes, fields, tolerance widening")
    sp.add_parser("build", help="run candidates, compare, attribute, finalize result.json")
    a = ap.parse_args()
    {"init": do_init, "show": do_show, "check": do_check, "build": do_build}.get(
        a.cmd, lambda x: ap.print_help())(a)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        pass
    except Exception:
        try:
            inp, out, w = paths()
            case, cp, err = load_case(inp)
            res = shell(case, case.get("case_id") or case.get("id"))
            res.update(status="partial", summary="unhandled exception",
                       errors=[V.snip(traceback.format_exc(), 1200)],
                       degradations=["unhandled_exception"])
            emit(out, res)
            sys.stderr.write("fatal: partial result.json written\n")
        except Exception:
            pass
    sys.exit(0)
