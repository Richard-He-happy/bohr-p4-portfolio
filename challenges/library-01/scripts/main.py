#!/usr/bin/env python3
"""research-library-curator CLI: contract handling, artifacts, self-check.

  python3 -B main.py --input /input --output /app/output     # ingest + verify
  python3 -B main.py --check --input /input --output /app/output   # re-verify only
Exit code is always 0; every problem is written into result.json
(errors / degradations / pending_human) and verify_report.json."""
import argparse, csv, hashlib, json, os, re, sys, time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import curator as C

SK, VER = C.SK, C.VER
CK = [("failures", r"fail|skip|error|conflict|exclud|missing|失败|跳过|异常|冲突|排除|缺失"),
      ("queries", r"quer|search|question|ask|answer|检索|查询|问题|回答"),
      ("versions", r"version|chain|supersed|谱系|版本"), ("duplicates", r"dup|重复|alias|别名|rename|重名"),
      ("operations", r"operat|log|journal|日志|操作|变更|审计"), ("metadata", r"meta|field|属性|元数据|字段"),
      ("directory", r"director|tree|folder|目录|结构|层级"), ("inventory", r"inventor|file.?list|清单|文件|列表"),
      ("report", r"report|summary|handoff|报告|摘要|交接|说明"),
      ("metrics", r"count|stat|metric|rate|cover|统计|数量|率|覆盖"), ("sources", r"source|provenance|evidence|来源|证据"),
      ("uncertainty", r"uncertain|limitation|risk|gap|不确定|限制|风险|缺口"), ("status", r"status|state|状态")]


def js(p, o):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(o, ensure_ascii=False, indent=2), encoding="utf-8")


def loadcase(inp):
    for c in sorted({Path(inp) / "case.json", *Path(inp).rglob("case*.json")}):
        try:
            o = json.loads(c.read_text(encoding="utf-8-sig", errors="replace"))
            if isinstance(o, dict):
                return o, c
        except Exception as e:
            if c.is_file():
                C.err("case_json_unreadable", e, c)
    C.err("case_missing", "no readable case.json", inp)
    return {}, None


def ncontract(v):
    if isinstance(v, dict):
        return {str(k): v[k] for k in v}
    out = {}
    for i, it in enumerate(v if isinstance(v, list) else [], 1):
        if isinstance(it, dict):
            out[str(it.get("field") or it.get("name") or it.get("key") or "field_%d" % i)] = (
                it.get("description") or it.get("desc") or it.get("type") or it)
        elif isinstance(it, str):
            out[it] = ""
    return out

def contract_of(case):
    for p, v in C.wk(case):
        if p.count(".") <= 9 and re.match(r"(?i).*(output_contract|contract|output_spec|契约)$", p.rsplit(".", 1)[-1]):
            c = ncontract(v)
            if c:
                return c
    return {}


def ret(q, its):
    s = str(q).lower()
    tm = [t for t in re.split(r"[^\w\u4e00-\u9fff]+", s) if len(t) > 1 or t.isdigit()]
    cj = "".join(re.findall(r"[\u4e00-\u9fff]+", s))
    tm += [cj[i:i + 2] for i in range(len(cj) - 1)]
    out = []
    for it in its:
        fn = it["filename"].lower()
        b = (it["filename"] + " " + it["path_source"] + " " + str(it["metadata"])).lower()
        t = (it.get("text") or "").lower()
        hit = [x for x in set(tm) if x in fn or x in b or x in t]
        sc = sum(3 if x in fn else (2 if x in b else 1) for x in hit)
        if sc:
            out.append({"item_id": it["item_id"], "path_source": it["path_source"], "path_library": it["path_library"],
                        "score": sc, "matched_terms": sorted(hit)[:8], "locator": "inventory.csv#item_id=" + it["item_id"]})
    out.sort(key=lambda x: (-x["score"], x["item_id"]))
    top = out[:5]
    return {"query": q, "method": "lexical(file/path/meta/text)", "status": "answered" if top else "no_match",
            "confidence": "high" if top and top[0]["score"] >= 6 else ("medium" if top else "none"),
            "matches": top, "evidence_locator": [x["locator"] for x in top],
            "answer": "; ".join(x["path_library"] or x["path_source"] for x in top) or None}


def fill(ct, A):
    out, un = {}, []
    for k, sp in ct.items():
        pr = (str(k) + " " + (sp if isinstance(sp, str) else json.dumps(sp, ensure_ascii=False))).lower()
        v = None
        if not re.search(r"unknown|other|extra|misc|additional|其它|其他", str(k), re.I):
            for n, pat in CK:
                if re.search(pat, pr):
                    v = A.get(n)
                    break
        if v is None:
            v = [] if re.search(r"array|list|列表|数组|\[\]", pr) else (
                {} if re.search(r"object|dict|mapping|对象|字典", pr) else None)
            un.append({"field": k, "fill": type(v).__name__, "spec": sp})
        out[str(k)] = v
    return out, un


def checks(inp, out):
    """Independent re-verification straight from disk; trusts no in-memory state."""
    ck = []

    def add(n, ok, d):
        ck.append({"check": n, "ok": bool(ok), "detail": d})

    try:
        res = json.loads((Path(out) / "result.json").read_text(encoding="utf-8"))
    except Exception as e:
        return {"passed": False, "checks": [{"check": "result_json_parsable", "ok": False,
                                               "detail": str(e)[:200]}], "note": "result.json unreadable"}
    add("result_json_parsable", True, "keys=%d" % len(res))
    add("status_enum", res.get("status") in ("ok", "partial", "insufficient_evidence", "input_error"),
        str(res.get("status")))
    ct = res.get("contract_echo") or {}
    miss = [k for k in ct if k not in res]
    add("contract_complete", not miss, "declared=%d missing=%s" % (len(ct), miss[:10]))
    its, bad, bad2, miss2 = res.get("inventory") or [], 0, 0, 0
    for it in its:
        try:
            if it.get("sha256") and C.sha(Path(inp) / str(it["path_source"])) != it["sha256"]:
                bad += 1
        except OSError:
            bad += 1
    add("source_sha256_recompute", bad == 0, "%d/%d mismatched" % (bad, len(its)))
    for it in its:
        if not it.get("path_library"):
            continue
        f2 = Path(out) / it["path_library"]
        if not f2.is_file():
            miss2 += 1
        elif C.sha(f2) != (it.get("sha256_library") or it.get("sha256")):
            bad2 += 1
    add("library_copies_verified", not (bad2 or miss2), "missing=%d hash_mismatch=%d" % (miss2, bad2))
    f = res.get("failures") or {}
    m = res.get("metrics") or {}
    cov = len(its) + len(f.get("excluded") or []) + len(f.get("denied_paths") or [])
    add("no_silent_skip", cov == m.get("files_seen", cov), "materials+excluded+denied=%d files_seen=%s"
        % (cov, m.get("files_seen")))
    seen, dup_ok = set(), True
    for g in (res.get("duplicates") or {}).get("exact_groups") or []:
        if len(g.get("members") or []) < 2 or g.get("sha256") in seen:
            dup_ok = False
        seen.add(g.get("sha256"))
    add("duplicate_groups_sane", dup_ok, "%d groups" % len(seen))
    chs = (res.get("versions") or {}).get("chains") or []
    ch_ok = all(len(c.get("members") or []) > 1 and len({x.get("sha256") for x in c["members"]}) > 1
                and [x.get("order") for x in c["members"]] == list(range(1, len(c["members"]) + 1)) for c in chs)
    add("version_chains_sane", ch_ok, "%d chains" % len(chs))
    log = Path(out) / "operations.log"
    lines = [x for x in (log.read_text(encoding="utf-8").splitlines() if log.is_file() else []) if x.strip()]
    badj = 0
    for line in lines:
        try:
            json.loads(line)
        except Exception:
            badj += 1
    add("operations_log_jsonl", badj == 0 and (lines != [] or not its), "lines=%d bad=%d" % (len(lines), badj))
    passed = all(x["ok"] for x in ck)
    rep = {"passed": passed, "checked_at": C.now(), "checks": ck,
           "counts": {"checks": len(ck), "failed": sum(1 for x in ck if not x["ok"])}}
    js(Path(out) / "verify_report.json", rep)
    return rep


def run(inp, out, case=None, cp=None):
    inp, out = Path(inp), Path(out)
    if case is None:
        case, cp = loadcase(inp)
    ct = contract_of(case) if case else {}
    if not ct:
        C.ph("contract_missing", "case.json has no output_contract; canonical keys only")
    cid = next((case[k] for k in ("case_id", "caseId", "id") if isinstance(case.get(k), (str, int))), None)
    cid = cid if cid is not None else (cp.parent.name if cp else None)
    js(out / "result.json", {"skill": {"name": SK, "version": VER}, "case_id": cid, "status": "partial",
                             "note": "partial placeholder before scan", "at": C.now(), "contract_echo": ct})
    ok = True
    try:
        if C.shutil.disk_usage(out).free < 50 << 20:
            ok = False
            C.deg("disk_space", "free space below 50MB", out)
    except OSError as e:
        C.deg("disk_space", str(e), out)
    r = C.ingest(inp, out, case, ok)
    its = r["items"]
    ex, dn, chs, dg = r["excluded"], r["denied"], r["chains"], r["dupgroups"]
    qs = []
    if case:
        for p, v in C.pk(case, r"\bquer|\bsearch|\bquestion|\bask|检索|查询|问题"):
            if re.search(r"\.(output_contract|contract|output_spec)\b", p):
                continue
            if isinstance(v, str) and v:
                qs = [v]
                break
            if isinstance(v, list) and v:
                qs = [x if isinstance(x, str) else (x.get("query") or x.get("q") or x.get("text")
                                                    or json.dumps(x, ensure_ascii=False))
                      for x in v if isinstance(x, (str, dict))]
                if qs:
                    break
    qy = [ret(q, its) for q in qs[:30]]
    fl = sorted({k for it in its for k in it["metadata"]})
    fr = {f: {"filled": sum(1 for it in its if f in it["metadata"]), "total": len(its),
              "rate": round(sum(1 for it in its if f in it["metadata"]) / len(its), 4) if its else 0.0} for f in fl}
    tr = r["paths"]
    ln, seen = ["library/"], set()
    for k in tr:
        parts = k.split("/")[1:]
        for i in range(len(parts)):
            key = "/".join(parts[:i + 1])
            if key not in seen:
                seen.add(key)
                ln.append("  " * i + "|-- " + parts[i])
    tree = "\n".join(ln)
    (out / "directory_tree.txt").write_text(tree + "\n", encoding="utf-8")
    cols = ["item_id", "path_source", "path_library", "filename", "size_bytes", "sha256", "ext", "mime_guess",
            "mtime", "category", "project", "year", "version_label", "base_key", "chain_id", "action", "dup_of",
            "read_status", "integrity_flag", "metadata_fields", "metadata_sources"]
    with open(out / "inventory.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for it in its:
            row = dict(it)
            row["version_label"] = it["metadata"].get("version_label", {}).get("value")
            row["metadata_fields"] = ";".join(sorted(it["metadata"]))
            row["metadata_sources"] = ";".join(sorted({v["source"] for v in it["metadata"].values()}))
            w.writerow(row)
    with open(out / "metadata.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["item_id", "field", "value", "source", "locator", "confidence"])
        for it in its:
            for f in sorted(it["metadata"]):
                v = it["metadata"][f]
                w.writerow([it["item_id"], f, v["value"], v["source"], v["locator"], v["confidence"]])
    (out / "operations.log").write_text("".join(json.dumps(o, ensure_ascii=False) + "\n" for o in C.OPS),
                                        encoding="utf-8")
    js(out / "version_chain.json", {"basis": "sha256 + mtime + version label; never name alone",
                                    "chains": chs})
    me = {"files_seen": r["files_seen"], "materials_indexed": len(its), "excluded_control": len(ex),
          "denied_paths": len(dn), "copied": sum(1 for o in C.OPS if o["op"] == "copy"),
          "reused": sum(1 for o in C.OPS if o["op"] == "reuse"),
          "exact_duplicates": sum(len(g["members"]) - 1 for g in dg), "dup_groups": len(dg),
          "version_chains": len(chs),
          "unreadable": sum(1 for it in its if it["read_status"] == "permission_denied"),
          "integrity_suspect": sum(1 for it in its if it["integrity_flag"]),
          "metadata_fill_rate": {k: v["rate"] for k, v in fr.items()},
          "queries_answered": sum(1 for q in qy if q["status"] == "answered")}
    st = "ok"
    if C.ERR or C.DEG or C.PH or any(it["action"] in ("failed_copy", "failed_hash_mismatch", "skipped_no_space")
                                      for it in its):
        st = "partial"
    if not case:
        st = "input_error"
    elif not its:
        st = "insufficient_evidence"
    un = [x for x in [
        "year not found for some files -> _undated (mtime year never used as content year)"
        if fr.get("year", {}).get("rate", 0) < 1 else None,
        "title low-confidence (first content line) for some files" if any(
            it["metadata"].get("title", {}).get("confidence") == "low" for it in its) else None,
        "queries empty: no search questions in case" if not qy else "lexical retrieval only" if qy else None,
        "chain order keyed on mtime; copied mtimes can invert order" if chs else None] if x]
    res = {"skill": {"name": SK, "version": VER}, "case_id": cid, "status": st, "generated_at": C.now(),
           "inventory": its[:5000],
           "directory": {"root": "library", "template": "project/year/category/filename", "tree_text": tree,
                         "path": "directory_tree.txt", "dirs": sorted({k.rsplit("/", 1)[0] for k in tr})},
           "metadata": {"field_dictionary": C.FA, "fill_rate": fr, "path": "metadata.csv",
                        "per_file": {it["item_id"]: {"filename": it["filename"], "fields": it["metadata"]}
                                     for it in its},
                        "provenance_rule": "each field carries source+locator; no source -> no value"},
           "versions": {"chains": chs, "path": "version_chain.json", "basis": "sha256+mtime+version_label"},
           "duplicates": {"exact_groups": dg, "aliases": r["aliases"], "basis": "sha256"},
           "operations": {"path": "operations.log", "count": len(C.OPS), "records": C.OPS[:1000]},
           "failures": {"unreadable": [it["path_source"] for it in its if it["read_status"] == "permission_denied"],
                        "integrity_suspect": [{"path": it["path_source"], "flag": it["integrity_flag"]}
                                              for it in its if it["integrity_flag"]],
                        "failed_actions": [o for o in C.OPS if "failed" in o["op"] or o["op"] == "copy_rollback"],
                        "denied_paths": dn, "excluded": ex},           "queries": qy, "metrics": me,
           "sources": [{"id": "input:" + it["path_source"], "kind": "material", "sha256": it.get("sha256"),
                        "item_id": it["item_id"]} for it in its] + [
               {"id": "case:" + (cp.name if cp else "none"), "kind": "case", "path": str(cp) or None,
                "sha256": C.sha(cp) if cp else None}],
           "uncertainty": un, "report": {"path": "report.md"}, "pending_human": C.PH, "errors": C.ERR,
           "degradations": C.DEG,
           "changes": [{"ts": o["ts"], "op": o["op"], "item_id": o.get("item_id"), "dst": o.get("dst")} for o in C.OPS],
           "runtime": {"python": sys.version.split()[0], "elapsed_s": round(time.time() - C.T0, 2),
                       "input": str(inp), "output": str(out)},
           "contract_echo": ct}
    rep = ["# Library ingest report (%s)" % C.now(), "",
           "status **%s** | materials %d | copied %d | duplicate copies %d | version chains %d" % (
               st, len(its), me["copied"], me["exact_duplicates"], len(chs)),
           "dedup on sha256; chains by (mtime, version label); no file is ever overwritten", "",
           "## Tree", "```", tree[:3500], "```", "", "## Failures / human review"]
    rep += ["- " + e["kind"] + ": " + e["message"] for e in (C.ERR + C.PH)[:25]] or ["- none blocking"]
    rep += ["", "re-run: python3 -B scripts/main.py --input <in> --output <out> ; verify: --check"]
    rep = "\n".join(rep) + "\n"
    (out / "report.md").write_text(rep, encoding="utf-8")
    res["report"]["text"] = rep
    cfd, urs = fill(ct, res)
    res.update({k: v for k, v in cfd.items() if res.get(k) is None})
    res["contract_unresolved"] = urs
    js(out / "result.json", res)
    v = checks(inp, out)
    res["verification"] = v
    if not v.get("passed"):
        res["status"] = "partial" if res["status"] == "ok" else res["status"]
        C.err("verification_failed", "self-check failed; see verify_report.json")
    js(out / "result.json", res)
    man = {"run_id": hashlib.sha256(("%s|%s|%s" % (VER, cid, sorted((it["path_source"], it["sha256"])
                                                                     for it in its))).encode()).hexdigest()[:24],
           "generated_at": C.now(), "skill_version": VER, "files": {}}
    for f in sorted(out.rglob("*")):
        if f.is_file() and f.name != "run_manifest.json":
            try:
                man["files"][str(f.relative_to(out)).replace(os.sep, "/")] = {"bytes": f.stat().st_size,
                                                                             "sha256": C.sha(f)}
            except OSError as e:
                C.err("manifest_hash_failed", e, f)
    js(out / "run_manifest.json", man)
    print("status=%s materials=%d copied=%d dup=%d chains=%d queries=%d errors=%d verify=%s -> %s"
          % (res["status"], len(its), me["copied"], len(dg), len(chs), len(qy), len(C.ERR), v.get("passed"), out))


def main():
    ap = argparse.ArgumentParser(
        description="Ingest a research file batch into a curated hash-verified library: inventory, metadata "
                    "provenance, hash dedup, version chains, logs.",
        epilog="Exit code is always 0. Example: python3 -B main.py --input /input --output /app/output")
    ap.add_argument("--input", default=None, help="input dir (default /input, /app/input, ./input)")
    ap.add_argument("--output", default=None, help="output dir (default /app/output, ./output)")
    ap.add_argument("--check", action="store_true", help="re-verify existing output")
    a = ap.parse_args()
    inp = Path(a.input) if a.input else next((p for p in (Path("/input"), Path("/app/input"), Path("./input"))
                                              if p.is_dir()), Path("/input"))
    out = Path(a.output) if a.output else next((p for p in (Path("/app/output"), Path("./output"))
                                                if p.is_dir() or p.parent.is_dir()), Path("./output"))
    try:
        out.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        C.err("output_unwritable", e, out)
        out = Path("./output")
        out.mkdir(parents=True, exist_ok=True)
    if a.check:
        v = checks(inp, out)
        print("verify passed=%s failed=%d -> %s" % (v["passed"], v["counts"]["failed"], out / "verify_report.json"))
        return
    run(inp, out)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        C.err("fatal", e)
        try:
            o = Path(os.environ.get("LIB_CURATOR_OUT", "./output"))
            o.mkdir(parents=True, exist_ok=True)
            js(o / "result.json", {"skill": {"name": SK, "version": VER}, "case_id": None, "status": "input_error",
                                   "errors": C.ERR, "degradations": C.DEG, "pending_human": C.PH,
                                   "generated_at": C.now()})
        except Exception:
            pass
    sys.exit(0)
