#!/usr/bin/env python3
"""reading-09: paper -> section-anchored notes with verbatim, page-anchored evidence (stdlib, offline)."""
import argparse
import csv
import json
import re
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
try:
  import doctext as dt
  ERR = ""
except Exception as exc:
  dt, ERR = None, f"{type(exc).__name__}: {exc}"
VERSION, SKILL, T0 = "1.0.0", "section-anchored-paper-notes", time.time()
R = {"cues": [["result", r"significant|\d+(?:\.\d+)?\s*%|p\s*<"]], "cond": r"n\s*=\s*\d+|p\s*[<=>]\s*0?\.\d+",
  "num": r"-?\d+(?:\.\d+)?", "purpose": {}, "card": ["research_question", "methods", "key_results"],
  "alias": {"key_results": ["result"], "conclusions": ["conclusion"], "limitations": ["limitation"]},
  "syn": {}, "limits": {}}
try:
  R = {**R, **json.loads((HERE.parent / "references" / "rules.json").read_text(encoding="utf-8"))}
except Exception:
  pass
CUES = [(k, re.compile(p, re.I)) for k, p in R["cues"]]
KIND, CARD, ALIAS, SYN, PURP = [k for k, _ in CUES], R["card"], R["alias"], R["syn"], R["purpose"]
COND, NUM = re.compile(R["cond"], re.I), re.compile(R["num"])
TEXT = {".pdf", ".docx", ".xlsx", ".csv", ".tsv", ".txt", ".md", ".json", ".html", ".htm", ".xml", ".tex"}
IMG = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif", ".webp"}


def NORM(s):
  return re.sub(r"\s+", " ", s or "").strip()


def SQ(s):
  return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def now():
  return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def wjson(p, o):
  t = p.with_suffix(p.suffix + ".tmp")
  t.write_text(json.dumps(o, ensure_ascii=False, indent=1), encoding="utf-8")
  t.replace(p)


def fill(n):  # echo a contract shape with null/[] leaves; key names never change
  return {k: fill(v) for k, v in n.items()} if isinstance(n, dict) else ([] if isinstance(n, list) else None)


def overlay(shape, pay):
  if not isinstance(shape, dict):
    return shape
  out = {}
  for k, v in shape.items():
    pv = pay.get(SYN.get(re.sub(r"[^a-z0-9]", "", k.lower())) or "")
    out[k] = overlay(v, pv) if isinstance(v, dict) and isinstance(pv, dict) else (pv if pv is not None else v)
  return out


def table(head, rows):
  return "\n".join(["| " + " | ".join(head) + " |", "|" + "---|" * len(head)] +
          ["| " + " | ".join(str(x).replace("|", "\\|") for x in r) + " |" for r in rows])


def load_case(inp, E, D):
  case = {}
  for c in sorted({inp / "case.json", *inp.glob("case*.json")}):
    if c.is_file():
      try:
        case = json.loads(c.read_text(encoding="utf-8", errors="ignore"))
        D.append(f"case json {c.name}: {len(case)} keys")
        break
      except Exception as exc:
        E.append(f"case json {c.name}: {type(exc).__name__}: {str(exc)[:90]} -> no contract echo")
  case = case if isinstance(case, dict) else {}
  contract = next((case[k] for k in ("output_contract", "outputContract", "contract", "result_contract")
          if isinstance(case.get(k), dict)), {})
  return case, contract


def find_materials(inp):
  out = []
  for p in (sorted(inp.rglob("*")) if inp.is_dir() else []):
    try:
      if p.is_file() and not p.name.startswith(".") and p.name not in ("case.json", "task.md") and p.stat().st_size:
        out.append({"path": p, "ext": p.suffix.lower(), "size": p.stat().st_size})
    except OSError:
      continue
  out.sort(key=lambda d: ({".pdf": 0, ".docx": 1, ".xlsx": 2, ".csv": 3}.get(d["ext"], 4), -d["size"]))
  return out


def claims_of(idx, sid, starts, cap):
  C, per = [], {}
  for sec in idx["sections"]:
    if sec["kind"] == "references":
      continue
    ss = dt.split_sentences(sec["text"])
    cand = []
    for i, s in enumerate(ss):
      ks = [k for k, rx in CUES if rx.search(s)]
      if ks:
        sc = (0.9 * len(ks) + min(2.5, len(re.findall(r"\d", s)) / 7.0)
           + (0.4 if i < max(2, len(ss) // 6) else 0) - (0.6 if len(s) < 45 else 0.4 if len(s) > 420 else 0))
        cand.append((sc, i, s, ks))
    cand.sort(key=lambda y: -y[0])
    seen = []
    for sc, i, s, ks in cand:
      if len(seen) >= R["limits"].get("max_claims_per_section", 8) or len(C) >= cap:
        break
      sig = SQ(s)[:120]
      if any(len(sig) > 40 and (sig in t or t in sig) for t in seen):
        continue
      seen.append(sig)
      a0 = sec.get("body", sec["start"]) + max(0, sec["text"].find(s))
      a1, pg = a0 + len(s), dt._page_of(starts, a0)
      C.append({"claim_id": f"c{len(C) + 1:03d}", "kind": ks[0], "also_matches": ks[1:],
           "statement": NORM(s), "statement_mode": "verbatim_quote", "quote": NORM(s), "source_id": sid,
           "location": {"page": pg, "page_end": dt._page_of(starts, max(a0, a1 - 1)),
                 "section_id": sec["section_id"], "section_title": sec["title"],
                 "section_kind": sec["kind"], "sentence_index": i + 1, "char_start": a0,
                 "char_end": a1, "anchor": f"{sid}:p{pg}/{sec['section_id']}/s{i + 1}",
                 "pointer": f"/claims/{len(C)}"},
           "conditions": [m.group(0) for m in list(COND.finditer(s))[:8]], "numbers": [],
           "readability": "directly_read", "confidence": round(min(0.96, 0.5 + 0.1 * sc), 2),
           "verified_quote_hit": False})
      for m in NUM.finditer(s):
        if m.group(0) not in [y["raw"] for y in C[-1]["numbers"]]:
          C[-1]["numbers"].append({"raw": m.group(0), "unit": (m.group(2) or None) if m.lastindex else None})
      per.setdefault(sec["section_id"], []).append(C[-1]["claim_id"])
  return C, per


def build_card(C):
  card = {}
  for f in CARD:
    h = [c for c in C if c["kind"] in ALIAS.get(f, [f])]
    h.sort(key=lambda c: (-c["confidence"], c["location"]["page"]))
    card[f] = {"value": h[0]["quote"] if h else None, "claim_ids": [c["claim_id"] for c in h[:4]],
         "status": "reported" if h else "not_found_in_extracted_text",
         "readability": "directly_read" if h else "undetermined",
         "pages": sorted({c["location"]["page"] for c in h[:4]})}
  return card


def render(r):
  try:
    t = (HERE.parent / "references" / "notes_template.md").read_text(encoding="utf-8")
  except Exception:
    t = "# 结构化阅读笔记\n\n> {{title}} · `{{case_id}}` · `{{status}}`\n\n{{section_notes}}\n\n{{gaps}}\n"
  t = re.sub(r"<!--.*?-->", "", t, flags=re.S)
  bid, per = {c["claim_id"]: c for c in r["claims"]}, {s["section_id"]: s["claim_ids"] for s in r["section_notes"]}
  pri, cov = next((s for s in r["sources"] if s["role"] == "primary"), {}), r["coverage"]
  run = table(["项目", "值"], [["主来源", f"`{pri.get('name', '-')}` ({pri.get('kind')}, {pri.get('pages')} 页, "
                      f"{pri.get('chars')} 字符, 质量 {cov.get('text_quality')})"],
                ["章节 / 证据", f"{len(r['section_notes'])} / {len(r['claims'])}"
                        f"（quote 命中 {cov.get('quote_verified')}）"]])
  card = table(["字段", "值（原文逐字）", "状态", "页", "证据"],
        [[f"`{f}`", (r["paper_card"][f]["value"] or "—")[:220], r["paper_card"][f]["status"],
         ",".join(map(str, r["paper_card"][f]["pages"])) or "—",
         " ".join(r["paper_card"][f]["claim_ids"]) or "—"] for f in CARD])
  smap = "\n".join(f"- `{s['section_id']}` {s['title']} ({s['kind']}, pp.{s['pages'][0]}–{s['pages'][1]}, "
          f"{len(per[s['section_id']])} 证据) · {PURP.get(s['kind'], '')}" for s in r["section_notes"])
  body = []
  for s in r["section_notes"]:
    body += [f"### {s['section_id']} {s['title']} — pp.{s['pages'][0]}–{s['pages'][1]} · "
        f"{PURP.get(s['kind'], '')}", ""]
    if not per[s["section_id"]]:
      body += ["- 本节未提取到带线索句的条目；缺口登记于 §6。", ""]
    for k in KIND:
      grp = [i for i in per[s["section_id"]] if bid[i]["kind"] == k]
      if not grp:
        continue
      body += [f"**{k}**", ""]
      for cid in grp:
        c = bid[cid]
        body += [f"- {c['quote']}", f"  <sub>`{cid}` · p{c['location']['page']} · "
            f"{c['location']['section_id']} · s{c['location']['sentence_index']} · "
            f"{c['readability']} · {'quote-hit' if c['verified_quote_hit'] else 'quote-MISS'}"
            f"{('；条件: ' + '; '.join(c['conditions'])) if c['conditions'] else ''}</sub>"]
      body.append("")
  gaps = ["- 无证据字段: " + ("、".join(f for f in CARD if r["paper_card"][f]["status"] != "reported") or "无")]
  gaps += [f"- [uncertainty:{u.get('severity', '?')}] {u['item']} — {u['basis']}" for u in r["uncertainty"]]
  gaps += [f"- [pending_human] {p['item']} → {p['suggested_action']}" for p in r["pending_human"]]
  rep = {"title": r["title"] or "(untitled)", "case_id": r["case_id"], "status": r["status"], "skill": SKILL,
     "version": VERSION, "ts": now(), "run_table": run, "card_table": card, "section_map": smap,
     "section_notes": "\n".join(body), "gaps": "\n".join(gaps),
     "media": "见图表题注条目 / see figure_caption claims"}
  for k, val in rep.items():
    t = t.replace("{{%s}}" % k, str(val))
  return re.sub(r"\{\{[a-z_]+\}\}", "—", t)


def write_csv(path, C):
  cols = ["claim_id", "kind", "readability", "source_id", "page", "page_end", "section_id", "sentence_index",
      "char_start", "char_end", "anchor", "verified_quote_hit", "conditions", "numbers", "quote"]
  with path.open("w", encoding="utf-8", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(cols)
    for c in C:
      l = c["location"]
      w.writerow([c["claim_id"], c["kind"], c["readability"], c["source_id"], l["page"], l["page_end"],
            l["section_id"], l["sentence_index"], l["char_start"], l["char_end"], l["anchor"],
            c["verified_quote_hit"], "; ".join(c["conditions"]),
            "; ".join(n["raw"] for n in c["numbers"]), c["quote"]])


def run(a):
  inp, out = Path(a.input), Path(a.output)
  E, D, G, PD, U, RS = [], [], [], [], [], []
  try:
    out.mkdir(parents=True, exist_ok=True)
  except Exception as exc:
    out = Path.cwd() / "output"
    out.mkdir(parents=True, exist_ok=True)
    E.append(f"output dir unusable ({str(exc)[:70]}) -> {out}")

  def P(item, act, why="", ptr=""):
    PD.append({"item": item, "reason": why, "suggested_action": act, "pointer": ptr})

  case, contract = load_case(inp, E, D)
  res = {"case_id": case.get("case_id") or case.get("id") or case.get("caseId") or "unknown_case",
     "skill": {"name": SKILL, "version": VERSION}, "status": "partial", "title": None, "summary": "",
     "notes_path": None, "sources": [], "claims": [], "paper_card": {},
     "section_notes": [], "figures": [], "tables": [], "gaps": [], "artifacts": {}, "coverage": {},
     "uncertainty": U, "pending_human": PD, "errors": E, "degradations": D, "changes": G,
     "output_contract_echo": {},
     "runtime": {"skill_version": VERSION, "python": sys.version.split()[0], "started_utc": now(),
           "model_requests": 0, "network": False, "elapsed_s": 0.0,
           "note": "deterministic local run; no model or network calls"}}
  if contract:
    res.update({k: val for k, val in fill(contract).items() if k not in res})
    D.append(f"contract: {len(contract)} fields echoed")
  try:
    wjson(out / "result.json", res)
    G.append("partial result.json written before extraction")
  except Exception as exc:
    E.append(f"partial write: {str(exc)[:70]}")
  try:
    if dt is None:
      raise RuntimeError(f"doctext import failed: {ERR}")
    mats = find_materials(inp)
    imgs = [m for m in mats if m["ext"] in IMG]
    docs = []
    for i, m in enumerate([x for x in mats if x["ext"] in TEXT][:R["limits"].get("max_documents", 6)]):
      try:
        d = dt.read_document(m["path"])
      except Exception as exc:
        E.append(f"extract {m['path'].name}: {type(exc).__name__}: {str(exc)[:70]} -> skipped")
        continue
      d["source_id"] = f"src{i + 1:02d}"
      docs.append(d)
      D += [f"{d['source_id']}: {w}" for w in d["warnings"]]
    G.append(f"discovered {len(mats)} materials ({len(imgs)} image), parsed {len(docs)} documents")
    if not docs:
      res["status"] = "input_error"
      res["summary"] = f"未找到可解析文本材料（附件 {len(mats)}，图片 {len(imgs)}）。"
      E.append(f"discover: no parsable text material; saw {[m['path'].name for m in mats][:20]}")
    else:
      docs.sort(key=lambda d: -len(d["text"]))
      pri, q = docs[0], docs[0]["quality"]
      idx = dt.build_index(pri)
      C, per = claims_of(idx, pri["source_id"], idx["page_starts"], a.max_claims)
      blob = SQ(pri["text"])
      for c in C:
        c["verified_quote_hit"] = len(SQ(c["quote"])) >= 12 and SQ(c["quote"]) in blob
        if not c["verified_quote_hit"]:
          P(f"quote 未命中: {c['claim_id']}", "对照原页面核实", "抽取文本与引文不一致", "/claims")
      hit, card = sum(1 for c in C if c["verified_quote_hit"]), build_card(C)
      caps = [c for c in C if c["kind"] == "figure_caption"]
      figs = [{"label": c["quote"][:48], "caption": c["quote"], "page": c["location"]["page"],
          "anchor": c["location"]["anchor"], "elements": "not_parsed"}
          for c in caps]
      if caps:
        P(f"{len(caps)} 条图表题注已按原文锚定", "坐标轴/图例/误差线/像素读数需人工或视觉工具确认",
         "离线脚本不做图形像素读数", "/figures")
      if idx["headings_found"] < 2:
        RS.append("headings_not_detected")
        P(f"章节标题未检出({idx['headings_found']})", "人工标注标题行，或提供出版社 XML/HTML 全文",
         "版式/字体导致标题行不可识别", "/section_notes")
      if q.get("class") != "good":
        RS.append(f"text_quality_{q.get('class')}")
        U.append({"item": f"主来源文本质量 {q.get('class')} (score {q.get('score')})", "readability":
             "undetermined", "severity": "high" if q.get("class") == "garbled" else "medium",
             "basis": "字母占比/停用词密度/替换字符统计；低质量会漏句或错字"})
        P("抽取质量不足，笔记可能缺章", "对原页面 OCR 或提供原生全文后重跑", "扫描件/双栏/自定义编码字体",
         "/uncertainty")
      low = [p["page"] for p in pri["pages"] if len(p["text"]) < 120]
      if low:
        U.append({"item": f"低文本页 {', '.join('p%d' % p for p in low[:12])}", "severity": "medium",
             "basis": "可用字符过少，可能为图表或扫描页"})
      if imgs:
        P(f"{len(imgs)} 张图片未做像素读数", "用图像阅读工具读取坐标轴/图例/数值，或提供原始数据表",
         "本 Skill 离线运行，不调用视觉/OCR", "/pending_human")
      miss = [f for f in CARD if card[f]["status"] != "reported"]
      ratio = (hit / len(C)) if C else 0.0
      weak = (not C) or ratio < 0.8 or len(per) < max(1, len(idx["sections"]) // 3)
      res["status"] = ("insufficient_evidence"
              if q.get("class") == "garbled" or (not C and q.get("class") != "good")
              else ("partial" if (weak or RS) else "ok"))
      if res["status"] == "insufficient_evidence":
        RS.append("no_reliable_text")
      res["status_reasons"] = RS
      srcs = [{"source_id": d["source_id"], "name": Path(d["path"]).name, "path": d["path"], "kind": d["kind"],
          "pages": len(d["pages"]), "chars": len(d["text"]), "quality": d["quality"].get("class"),
          "role": "primary" if d is pri else "secondary"} for d in docs]
      res.update({
        "title": pri["title"], "status": res["status"], "paper_card": card, "claims": C, "figures": figs,
        "sources": srcs, "notes_path": str(out / "notes.md"),
        "artifacts": {"notes_md": str(out / "notes.md"), "claims_csv": str(out / "claims.csv"),
               "verify_report": str(out / "verify_report.json")},
        "gaps": [{"field": f, "status": "not_found_in_extracted_text", "readability": "undetermined",
             "note": "无匹配线索句；视为提取缺口而非原文未报告"} for f in miss],
        "section_notes": [{"section_id": s["section_id"], "title": s["title"], "kind": s["kind"],
                 "pages": [s["page_start"], s["page_end"]], "sentences": s["n_sent"],
                 "claim_ids": per.get(s["section_id"], []), "readability": "inferred"}
                 for s in idx["sections"]],
        "coverage": {"anchor_format": "source_id:p<page>/<section_id>/s<sentence>; char offsets index the "
                      "extracted text; page_map lists each page's char_start",
              "text_quality": q.get("class"), "text_quality_score": q.get("score"),
              "page_map": [{"page": p["page"], "char_start": idx["page_starts"][i],
                     "chars": len(p["text"])} for i, p in enumerate(pri["pages"])],
              "sections_total": len(idx["sections"]), "sections_with_claims": len(per),
              "section_kinds": sorted({s["kind"] for s in idx["sections"]}), "claims_total": len(C),
              "quote_verified": hit, "quote_hit_ratio": round(ratio, 3), "figure_captions": len(caps),
              "card_fields_reported": len(CARD) - len(miss), "card_fields_total": len(CARD),
              "gaps": len(miss), "documents_read": len(docs), "images_not_read": len(imgs),
              "errors": len(E), "degradations": len(D),
              "recheck": "python3 scripts/main.py --check --output <dir>"},
        "summary": f"将 `{Path(pri['path']).name}` 切分为 {len(idx['sections'])} 个原生章节，产出 {len(C)} 条"
             f"逐字证据笔记（quote 命中 {round(ratio * 100)}%），覆盖 {len(CARD) - len(miss)}/"
             f"{len(CARD)} 卡片字段。"})
      write_csv(out / "claims.csv", C)
      (out / "notes.md").write_text(render(res), encoding="utf-8")
      G.append("artifacts: notes.md, claims.csv")
  except Exception as exc:
    E.append(f"{type(exc).__name__}: {str(exc)[:200]} | "
        f"{traceback.format_exc(limit=2).replace(chr(10), ' ')[-200:]}")
  finally:
    res["changes"] = G + [f"finalize: status={res['status']} at {now()}"]
    res["runtime"]["elapsed_s"] = round(time.time() - T0, 2)
    if contract:
      res["output_contract_echo"] = overlay(fill(contract), res)
    C = res.get("claims") or []
    try:
      wjson(out / "result.json", res)
    except Exception:
      pass
    art = res.get("artifacts") or {}
    try:
      wjson(out / "verify_report.json", {
        "checked_at": now(), "status": res["status"], "claims": len(C),
        "quote_hit": res.get("coverage", {}).get("quote_verified"),
        "contract_keys": len(res.get("output_contract_echo") or {}),
        "missing_claim_fields": [k for k in ("claim_id", "kind", "quote", "source_id",
                                               "location", "readability", "conditions")
                                             if any(k not in c for c in C)],
        "artifacts_exist": {k: Path(x).is_file() for k, x in art.items() if k != "verify_report"},
        "pass": bool(C) and res.get("coverage", {}).get("quote_hit_ratio") == 1.0
            and all(Path(x).is_file() for k, x in art.items() if k != "verify_report")})
    except Exception:
      pass
  return res


def main(argv=None):
  ap = argparse.ArgumentParser(prog="main.py", description="reading-09: paper -> section-anchored notes with "
                              "verbatim, page-anchored evidence. Writes result.json (output_contract echoed), "
                              "notes.md, claims.csv, verify_report.json.")
  ap.add_argument("--input", default="/input", help="input dir")
  ap.add_argument("--output", default="/app/output", help="output dir")
  ap.add_argument("--max-claims", type=int, default=80, help="max claims")
  ap.add_argument("--check", action="store_true", help="re-run, report reproducibility")
  ap.add_argument("--version", action="version", version=f"{SKILL} v{VERSION}")
  a = ap.parse_args(argv)
  try:
    res = run(a)
    ids = [c["claim_id"] for c in res.get("claims") or []]
    print(f"{'check ' if a.check else ''}status={res['status']} claims={len(ids)} "
          f"sections={len(res.get('section_notes') or [])} notes={res.get('notes_path')}")
  except Exception as exc:
    print(f"error={type(exc).__name__}: {exc}")
  return 0


if __name__ == "__main__":
  sys.exit(main())
