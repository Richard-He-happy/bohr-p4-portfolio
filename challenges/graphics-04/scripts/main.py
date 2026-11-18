#!/usr/bin/env python3
"""main.py - 实验装置 / 技术路线图 Skill：init → (Agent 写 plan.json) → check → build。
产物 figure.svg / figure.pdf / figure.png / content_map.json / result.json；退出码恒 0。"""
import json, re, sys, time, shutil, hashlib, traceback, subprocess, zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import render
from extract import auto, deep, ingest, jload, sq

NAME, VER = "apparatus-technical-route-figure", "3.0.0"
U = """用法: python3 scripts/main.py <init|check|build> [--input DIR] [--work DIR] [--out DIR]
 init  索引材料并先写 partial result.json；check 校验 work/plan.json；build 出图并 finalize
示例（示例，非正式案例结果）: main.py init --input /input --work /app/work --out /app/output"""
def cli(a):
  o = {"cmd": "build", "input": "/input", "work": "/app/work", "out": "/app/output"}
  for x in a:
    o["cmd"] = "help" if x in ("-h", "--help") else x if x in ("init", "check", "build") else o["cmd"]
  for k in ("input", "work", "out"):
    for i, x in enumerate(a):
      if x == "--" + k and i + 1 < len(a):
        o[k] = a[i + 1]
      elif x.startswith("--" + k + "="):
        o[k] = x.split("=", 1)[1]
  o["input"] = Path(o["input"])
  for k, d in (("work", "work"), ("out", "output")):
    o[k] = Path(o[k])
    try:
      o[k].mkdir(parents=True, exist_ok=True)
    except Exception:
      o[k] = HERE.parent / d
      o[k].mkdir(parents=True, exist_ok=True)
  return o


def merge(m, plan, allsq, probs):
  out = dict(m, source="agent_plan")
  for k in ("title", "subtitle", "caption", "figure_kind", "lang", "global_params"):
    out[k] = plan.get(k) or out.get(k)
  for k in ("nodes", "edges", "steps", "stages"):
    if isinstance(plan.get(k), list) and plan[k]:
      out[k] = plan[k]
  for k, pre in (("nodes", "N"), ("edges", "E"), ("steps", "P"), ("stages", "G")):
    for i, it in enumerate(out[k]):
      it.setdefault("id", "%s%d" % (pre, i + 1))
      it.setdefault("params", []) if k == "nodes" else None
      it.setdefault("role", "device") if k == "nodes" else None
      if k == "stages":
        continue
      q = it.get("quote") or ""
      it["resolution"] = "exact" if q and sq(q) in allsq else (
          "missing" if q else ("inferred" if k == "edges" else "unverified"))
      if it["resolution"] in ("missing", "unverified"):
        it["pending"] = True
        probs.append({"code": "quote_" + it["resolution"], "kind": k, "id": it["id"],
                      "hint": "quote 需逐字命中材料"})
      it["source"] = it.get("source") or (it.get("locator") or "").split(" ")[0]
      if k == "nodes":
        probs += [{"code": "param_not_in_quote", "id": it["id"], "param": pr} for pr in it["params"]
                  if sq(pr) not in sq(q)]
  ids = {n["id"] for n in out["nodes"]}
  probs += [{"code": "edge_endpoint_unknown", "id": e["id"], "detail": "%s->%s" % (e["from"], e["to"])}
            for e in out["edges"] if e["from"] not in ids or e["to"] not in ids]
  for i, s in enumerate(out["steps"]):
    s["no"] = i + 1
  return out


def base(cid, contract, status="partial"):
  r = {"case_id": cid, "status": status, "skill": {"name": NAME, "version": VER},
       "editable_source": None, "export_artifact": None, "content_map": None,
       "compliance_checks": None, "exceptions": [], "sources": [], "uncertainty": [],
       "pending_human": [], "errors": [], "degradations": [], "changes": [], "runtime": {},
       "counts": {}, "output_contract": contract}
  for k, v in (contract or {}).items():
    if k not in r:
      r[k] = json.loads(json.dumps(v)) if isinstance(v, (dict, list)) else None
    elif isinstance(r[k], dict) and isinstance(v, dict):
      for kk in v:
        r[k].setdefault(kk, None)
  return r


def save(out, r):
  try:
    (out / "result.json").write_text(json.dumps(r, ensure_ascii=False, indent=1), "utf-8")
  except Exception:
    pass


def pngof(out):
  p, stem = out / "figure.png", str(out / "figure.png")[:-4]
  for c in (["pdftoppm", "-png", "-r", "150", "-singlefile", str(out / "figure.pdf"), stem],
            ["mutool", "draw", "-o", str(p), "-r", "150", str(out / "figure.pdf")]):  # 逐级降级
    if not shutil.which(c[0]):
      continue
    try:
      subprocess.run(c, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180)
    except Exception:
      continue
    if p.is_file() and p.read_bytes()[:4] == b"\x89PNG" and p.stat().st_size > 2000:
      return {"ok": True, "bytes": p.stat().st_size, "engine": Path(c[0]).name}
  return {"ok": False, "bytes": 0, "engine": None}


def _ov(fb):
  """节点框两两重叠计数（版面自检）。"""
  bs = []
  for gr in fb["grid"]["groups"]:
    r = [i for i in (gr.get("items") or []) if i["k"] == "rect"]
    if r and gr["id"].startswith("node-"):
      bs.append((r[0]["x"], r[0]["y"], r[0]["w"], r[0]["h"]))
  return sum(1 for i in range(len(bs)) for j in range(i + 1, len(bs))
             if bs[i][0] < bs[j][0] + bs[j][2] and bs[j][0] < bs[i][0] + bs[i][2]
             and bs[i][1] < bs[j][1] + bs[j][3] and bs[j][1] < bs[i][1] + bs[i][3])


def checks(fb, m, out):
  g, els = fb["grid"], fb["grid"]["groups"]
  svg, pdf = (out / "figure.svg").read_text("utf-8"), (out / "figure.pdf").read_bytes()
  t = ""
  if shutil.which("pdftotext"):
    try:
      t = subprocess.run(["pdftotext", str(out / "figure.pdf"), "-"], stdout=subprocess.PIPE,
                         timeout=90).stdout.decode("utf-8", "replace")
    except Exception:
      pass
  cj, ids = len([c for c in t if "\u4e00" <= c <= "\u9fff"]), [x["id"] for x in els]
  q, png = sum(1 for x in els if sq((x.get("src") or {}).get("quote"))), pngof(out)
  nid, rate = {n["id"] for n in m["nodes"]}, q / max(1, len(els))
  c = {"canvas": {"w": g["W"], "h": g["H"], "layers": len(fb["layers"]),
                  "ok": g["W"] >= 1000 and g["H"] >= 700 and len(fb["layers"]) >= 6},
       "text_editable": {"text_nodes": svg.count("<text "), "image_nodes": svg.count("<image"),
                         "ok": svg.count("<text ") > 20 and "<image" not in svg},
       "element_ids": {"n": len(ids), "unique": len(set(ids)) == len(ids),
                       "data_quote": svg.count("data-quote="),
                       "ok": len(set(ids)) == len(ids) and svg.count("data-quote=") >= 3},
       "evidence": {"elements": len(els), "with_quote": q, "rate": round(rate, 3), "ok": rate >= 0.6},
       "connections": {"n": len(m["edges"]), "arrowheads": svg.count("<polygon"),
                       "dangling": sum(1 for e in m["edges"] if e["from"] not in nid or e["to"] not in nid),
                       "ok": svg.count("<polygon") >= 2},
       "pdf": {"magic": pdf[:5].decode("latin1"), "ok": pdf[:5] == b"%PDF-", "bytes": len(pdf),
               "pages": 1, "vector": True, "text_layer": cj > 20, "cjk_extractable": cj,
               "font_embedded": b"FontFile2" in pdf},
       "png": {"ok": png["ok"], "bytes": png["bytes"], "engine": png["engine"], "dpi": 150},
       "geometry": {"node_overlaps": _ov(fb), "ok": _ov(fb) == 0},
       "determinism": {"ok": fb["deterministic"]}}
  c["pass"] = all(v.get("ok", True) for v in c.values() if isinstance(v, dict))
  c["failures"] = [k for k, v in c.items() if isinstance(v, dict) and not v.get("ok", True)]
  return c


def cmap(fb, m, path):
  els = []
  for gr in fb["grid"]["groups"]:
    s, mt = gr.get("src") or {}, gr.get("meta") or {}
    b = [i for i in (gr.get("items") or []) if i["k"] == "rect"]
    e = {"id": gr["id"], "kind": mt.get("kind", "shape"), "layer": gr["layer"],
         "label": mt.get("label") or s.get("label", ""), "quote": s.get("quote", ""),
         "locator": s.get("locator", ""), "source": s.get("source", ""),
         "resolution": s.get("resolution", "exact" if s.get("quote") else "inferred"),
         "bbox": {"x": round(b[0]["x"], 1), "y": round(b[0]["y"], 1), "w": round(b[0]["w"], 1),
                  "h": round(b[0]["h"], 1)} if b else None}
    e.update({k: mt.get(k, s.get(k)) for k in ("from", "to", "flow", "role", "params", "no", "pending")
              if k in mt or k in s})
    els.append(e)
  q = sum(1 for e in els if e["quote"])
  cm = {"figure": {"title": m.get("title"), "canvas": "%dx%d" % fb["canvas"]}, "elements": els,
        "coverage": {"parts": sum(1 for e in els if e["kind"] == "part"),
                     "connections": sum(1 for e in els if e["kind"] == "connection"),
                     "steps": sum(1 for e in els if e["kind"] == "step"), "with_quote": q,
                     "pending": sum(1 for e in els if e.get("pending")),
                     "quote_rate": round(q / max(1, len(els)), 3),
                     "parts_with_locator": sum(1 for e in els if e["kind"] == "part" and e["locator"])}}
  Path(path).write_text(json.dumps(cm, ensure_ascii=False, indent=1), "utf-8")
  return cm


def do_build(o, case, srcs, pars, r, probs, t0):
  out, m = o["out"], auto(pars, case)
  pp = o["work"] / "plan.json"
  if pp.is_file():
    pl = jload(pp)
    if "__err__" in pl:
      probs.append({"code": "plan_json_invalid", "detail": pl["__err__"][:150]})
    else:
      m = merge(m, pl, sq("".join(p["text"] for p in pars)), probs)
      r["changes"].append({"what": "Agent plan.json 覆盖确定性抽取", "file": str(pp)})
  if not m["nodes"]:
    r["status"] = "insufficient_evidence"
    probs.append({"code": "no_entities", "detail": "材料未给出可识别装置/步骤"})
  fb = render.build(m, out, 1200, None)
  cm, c = cmap(fb, m, out / "content_map.json"), None
  c = checks(fb, m, out)
  sp, qp = out / "figure.svg", out / "figure.pdf"
  pend = ([{"id": n["id"], "label": n["label"], "need": "补 quote/locator"} for n in m["nodes"]
           if n.get("pending")] + [{"id": e["id"], "need": "确认两端与流向"} for e in m["edges"]
                                   if e.get("pending")])
  r["sources"] = [{k: s[k] for k in ("id", "file", "kind", "chars")} for s in srcs]
  r["editable_source"] = {"path": str(sp), "format": "svg", "editable": True, "text_editable": True,
                          "layers": fb["layers"], "bytes": sp.stat().st_size,
                          "sha256": hashlib.sha256(sp.read_bytes()).hexdigest(),
                          "viewBox": "0 0 %d %d" % fb["canvas"]}
  r["export_artifact"] = {"pdf": dict(c["pdf"], path=str(qp), engine="stdlib-pdf1.4"),
                          "png": dict(c["png"], path=str(out / "figure.png") if c["png"]["ok"] else None)}
  r["content_map"] = {"path": str(out / "content_map.json"), "elements": len(cm["elements"]),
                      "coverage": cm["coverage"]}
  r["compliance_checks"] = c
  r["counts"] = dict(cm["coverage"], sources=len(srcs), paragraphs=len(pars), nodes=len(m["nodes"]),
                     edges=len(m["edges"]), steps=len(m["steps"]), stages=len(m["stages"]),
                     checks_fail=len(c["failures"]), plan_source=m.get("source"))
  r["pending_human"] = pend[:12]
  if not c["png"]["ok"]:
    r["degradations"].append({"code": "png_preview_unavailable", "detail": "无 pdftoppm/mutool；SVG+PDF 仍有效"})
  if m.get("source") == "auto":
    r["uncertainty"].append({"kind": "extraction", "detail": "未使用 Agent plan：图元来自确定性规则，pending 为虚线框"})
  if any(e.get("inferred") for e in m["edges"]):
    r["uncertainty"].append({"kind": "connection", "detail": "部分连接为句序推断（灰虚线标“顺序”）"})
  if r["status"] != "insufficient_evidence":
    r["status"] = "ok" if not (c["failures"] or pend or probs or r["uncertainty"]) else "partial"
  r["exceptions"] = probs[:20]
  r["runtime"] = {"seconds": round(time.time() - t0, 2), "command": o["cmd"],
                  "canvas": "%dx%d" % fb["canvas"]}
  save(out, r)
  print("build: 图元 %d 有证据 %d 覆盖率 %.2f 状态 %s 检查 %s" % (
      len(cm["elements"]), cm["coverage"]["with_quote"], cm["coverage"]["quote_rate"], r["status"],
      "全部通过" if not c["failures"] else ",".join(c["failures"])))
  return r


def run(o, t0):
  probs = []
  if not o["input"].is_dir():
    r = base("unknown-case", {}, "input_error")
    r["errors"] = [{"code": "input_dir_missing", "detail": str(o["input"])}]
    save(o["out"], r)
    print("input_error: %s" % o["input"])
    return r
  case, srcs, pars, cj = ingest(o["input"], probs)
  ct = deep(case, "output_contract", "contract")
  r = base(str(deep(case, "case_id") or (cj.stem if cj else "unknown-case"))[:80],
           ct if isinstance(ct, dict) else {})
  r["errors"] = probs[:10]
  save(o["out"], r)  # 先落盘 partial
  if o["cmd"] == "init":
    print("init: 材料 %d | 段落 %d | work=%s" % (len(srcs), len(pars), o["work"]))
    for s in srcs:
      print("  %-3s %-28s %-13s %6d字符 %3d段" % (s["id"], s["file"][:28], s["kind"], s["chars"],
                                                 s.get("paragraphs", 0)))
    print("  workorder: " + json.dumps(deep(case, "organizer_workorder", "workorder") or {},
                                       ensure_ascii=False)[:200])
    print("  下一步: 读材料 → 写 %s → check → build" % (o["work"] / "plan.json"))
    (o["work"] / "index.json").write_text(json.dumps(
        {"case_id": r["case_id"], "sources": srcs, "paragraphs": len(pars), "preview": pars[:40]},
        ensure_ascii=False, indent=1), "utf-8")
    r.update(sources=srcs, runtime={"seconds": round(time.time() - t0, 2), "command": "init"})
    save(o["out"], r)
    return r
  if o["cmd"] == "check":
    m = auto(pars, case)
    pp = o["work"] / "plan.json"
    if pp.is_file():
      pl = jload(pp)
      if "__err__" in pl:
        probs.append({"code": "plan_json_invalid", "detail": pl["__err__"][:150]})
      else:
        m = merge(m, pl, sq("".join(p["text"] for p in pars)), probs)
    rep = {"ok": not probs, "problems": probs[:20],
           "counts": {k: len(m.get(k) or []) for k in ("nodes", "edges", "steps", "stages")}}
    (o["work"] / "check_report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), "utf-8")
    print("check: %s | 问题 %d | %s" % ("通过" if rep["ok"] else "需修", len(probs),
                                        json.dumps(rep["counts"], ensure_ascii=False)))
    for x in probs[:10]:
      print("  - %s %s %s" % (x.get("code"), x.get("id") or x.get("file") or "", x.get("hint", "")))
    r.update(exceptions=probs[:20], counts=rep["counts"],
             runtime={"seconds": round(time.time() - t0, 2), "command": "check"})
    save(o["out"], r)
    return r
  return do_build(o, case, srcs, pars, r, probs, t0)


def main(a):
  t0 = time.time()
  try:
    o = cli(a)
    if o["cmd"] == "help":
      print(U)
      return 0
    run(o, t0)
  except BaseException as e:
    try:
      o = cli(a)
      r = base("unknown-case", {})
      r["errors"] = [{"code": "uncaught", "detail": "%s: %s" % (type(e).__name__, e),
                      "trace_tail": traceback.format_exc()[-600:]}]
      save(o["out"], r)
    except Exception:
      pass
    print("ERROR %s: %s" % (type(e).__name__, e))
  return 0


if __name__ == "__main__":
  sys.exit(main(sys.argv[1:]))
