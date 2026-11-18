#!/usr/bin/env python3
"""Shared parsing / evidence / analysis layer + self-check (experiment-03). Import or run standalone."""
import argparse, csv, io, json, math, re, shutil, subprocess, time, zipfile, zlib
from pathlib import Path

V = "1.0.0"
TXT = {".md", ".txt", ".csv", ".tsv", ".json", ".yaml", ".yml", ".log", ".xml", ".tex", ".html", ".rst", ".ini"}
U = {"c": "C", "℃": "C", "°c": "C", "degc": "C", "k": "K", "h": "h", "hr": "h", "hours": "h", "小时": "h",
     "min": "min", "分钟": "min", "s": "s", "sec": "s", "d": "d", "g": "g", "mg": "mg", "ug": "ug",
     "kg": "kg", "l": "L", "ml": "mL", "ul": "uL", "bar": "bar", "mpa": "MPa", "kpa": "kPa",
     "atm": "atm", "rpm": "rpm", "m": "M", "mm": "mM", "um": "uM", "%": "%", "wt%": "wt%", "pct": "%"}
B = {"C": ("t", 1), "K": ("t", 1), "h": ("T", 3600), "min": ("T", 60), "s": ("T", 1), "d": ("T", 86400),
     "g": ("m", 1), "mg": ("m", 1e-3), "ug": ("m", 1e-6), "kg": ("m", 1000), "L": ("v", 1),
     "mL": ("v", 1e-3), "uL": ("v", 1e-6), "bar": ("p", 1), "kPa": ("p", .01), "MPa": ("p", 10), "atm": ("p", 1.01325)}
CN = [("temperature", r"temp|温度|°c|℃|thermal"), ("time", r"\btime\b|duration|时间|时长|residence"),
      ("pressure", r"press|压力|mpa|\bbar\b"), ("concentration", r"concen|浓度|molar|mol/l"),
      ("ph", r"\bph\b|酸碱"), ("agitation", r"stir|rpm|搅拌|转速"),
      ("catalyst", r"catalyst|催化|loading|载量|负载"), ("ratio", r"ratio|比例|当量|equiv"),
      ("flow", r"flow|流速|流量"), ("volume", r"volume|体积"), ("mass", r"\bmass\b|质量|weight|投料")]
MET = (r"yield|conversion|selectivity|purity|收率|转化率|选择性|纯度|产率|efficiency|rate|活性|activity|"
       r"impurity|杂质|titer|滴度|recovery|回收|强度|strength|电导|conductivity|粒径|size|含量|score|偏差")
MINL = r"impurity|杂质|cost|成本|\btime\b|时间|defect|缺陷|能耗|energy|偏差|loss|损失"
SL = [("case_id", r"case_?id|案例编号"), ("summary", r"summary|摘要|概述|结论"), ("status", r"status|状态"), ("steps", r"steps?|步骤|流程"),
      ("plan", r"^plan$|^protocol$|方案|protocol|procedure"), ("comparison", r"compar|candidate|候选|备选"),
      ("parameters", r"param|参数|因子|factor|setting"), ("metrics", r"metric|响应|指标|indicator|测量"),
      ("search", r"search|搜索|策略|strategy|design"), ("cost", r"cost|budget|费用|成本|预算"),
      ("schedule", r"sched|timeline|排期|耗时"), ("materials", r"material|reagent|材料|试剂|耗材"),
      ("equipment", r"equip|instrument|仪器|设备|device"), ("variables", r"variable|变量"),
      ("groups", r"group|arm|control|对照|分组"), ("hypotheses", r"hypoth|假设"),
      ("validation", r"valid|acceptance|判读|验收|criteri|标准|验证"), ("risks", r"risk|风险"),
      ("feasibility", r"feasib|可行|constraint|约束"), ("anomaly", r"anomal|异常|outlier"),
      ("assumptions", r"assumption|前提|假定"), ("sources", r"source|evidence|依据|来源|citation"),
      ("uncertainty", r"uncertain|不确定|limitation|限制"), ("pending", r"pending|confirm|确认|待定"),
      ("stop", r"stop|停止|终止"), ("artifacts", r"artifact|deliverable|产物"),
      ("recommended", r"recommend|建议值|推荐|optimum|最优")]


def iso():
  return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def rnd(v, n=6):
  return (None if (math.isnan(v) or math.isinf(v)) else round(v, n)) if isinstance(v, float) else v


def cl(o):
  if isinstance(o, dict):
    return {str(k): cl(v) for k, v in o.items()}
  return [cl(v) for v in o] if isinstance(o, (list, tuple)) else rnd(o)


def ft(v):
  return "-" if v is None else (("%.4g" % v) if isinstance(v, float) else str(v))


def num(x):
  if isinstance(x, bool):
    return None
  if isinstance(x, (int, float)):
    return float(x)
  if isinstance(x, str):
    m = re.search(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", x.replace(",", ""))
    return float(m.group()) if m else None
  return None


def un(u):
  if u is None:
    return ""
  s = str(u).strip().lower().replace("μ", "u").replace("µ", "u")
  return U.get(s, U.get(s.rstrip("."), s))


def ut(s):
  m = re.findall(r"(°C|℃|MPa|kPa|bar|atm|rpm|mL|uL|μg|ug|mg|kg|min|hrs|hr|h|sec|s|L|g|mM|uM|M|%|wt%)", str(s))
  return un(m[-1]) if m else ""


def cv(v, a, b):
  """convert v from unit a to unit b inside one dimension; None if incompatible."""
  if v is None or not a or not b or a == b:
    return v
  x, y = B.get(a), B.get(b)
  if not x or not y or x[0] != y[0]:
    return None
  if x[0] == "t":
    c = v - 273.15 if a == "K" else v
    return c + 273.15 if b == "K" else c
  return v * x[1] / y[1]


def prange(v):
  """-> (lo, hi, unit); a missing side is None."""
  if v is None:
    return None, None, ""
  if isinstance(v, dict):
    d = {str(k).lower(): x for k, x in v.items()}
    u = un(d.get("unit") or d.get("units"))
    g = lambda ks: next((num(d[k]) for k in ks if k in d and num(d[k]) is not None), None)
    lo = g(("min", "low", "lower", "from", "start", "lo", "minimum", "lsl"))
    hi = g(("max", "high", "upper", "to", "end", "hi", "maximum", "usl"))
    if lo is None and hi is None:
      for k in ("values", "domain", "levels", "allowed"):
        if isinstance(d.get(k), list) and d[k]:
          ns = [n for n in map(num, d[k]) if n is not None]
          if ns:
            return min(ns), max(ns), u
    return lo, hi, u
  if isinstance(v, (list, tuple)):
    ns = [n for n in map(num, v) if n is not None]
    return (min(ns), max(ns), "") if len(ns) >= 2 else ((ns[0], ns[0], "") if ns else (None, None, ""))
  s = str(v)
  ns = [float(m) for m in re.findall(r"(?<![\d.])[-+]?\d+(?:\.\d+)?", s.replace(",", ""))]
  if not ns:
    return None, None, ut(s)
  up = bool(re.search(r"≤|<=|<(?!=)|不超过|至多|最大|at most|up to|\bmax", s, re.I))
  dn = bool(re.search(r"≥|>=|>(?!=)|不少于|至少|最小|at least|\bmin", s, re.I))
  if re.search(r"[-–~—]|\bto\b|至", s) and len(ns) >= 2:
    return min(ns[0], ns[1]), max(ns[0], ns[1]), ut(s)
  if up and not dn:
    return None, ns[0], ut(s)
  if dn and not up:
    return ns[0], None, ut(s)
  return ns[0], ns[0], ut(s)


def pick(d, names):
  if not isinstance(d, dict):
    return None
  low = {str(k).lower().strip(): v for k, v in d.items()}
  for n in names:
    for k, v in low.items():
      if (k == n or k.startswith(n) or n in k) and v not in (None, "", [], {}):
        return v
  return None


def walk(o, p=""):
  yield p, o
  if isinstance(o, dict):
    for k, v in o.items():
      for x in walk(v, p + "/" + str(k)):
        yield x
  elif isinstance(o, list):
    for i, v in enumerate(o):
      for x in walk(v, p + "/%d" % i):
        yield x


def kind(p):
  e = p.suffix.lower()
  try:
    h = p.open("rb").read(8)
  except Exception:
    h = b""
  if h.startswith(b"%PDF"):
    return "pdf"
  if h.startswith(b"PK\x03\x04"):
    return {".docx": "docx", ".xlsx": "xlsx", ".pptx": "pptx"}.get(e, "zip")
  if h.startswith(b"\x89PNG"):
    return "png"
  return "jpeg" if h[:3] == b"\xff\xd8\xff" else ("text" if e in TXT else (e.lstrip(".") or "unknown"))


def sx(s):
  return re.sub(r"<[^>]+>", "", re.sub(r"</w:p>|</a:p>", "\n", s)).replace("&amp;", "&").replace("&lt;", "<")


def ztext(p):
  """docx/xlsx/pptx: sheet rows rebuilt when sharedStrings exist, else joined XML text."""
  with zipfile.ZipFile(p) as z:
    nm = z.namelist()
    sh = [sx(m) for m in re.findall(r"<si>(.*?)</si>", z.read("xl/sharedStrings.xml").decode("utf-8", "ignore"), re.S)] \
      if "xl/sharedStrings.xml" in nm else []
    out = []
    for n in [x for x in nm if x.startswith("xl/worksheets/sheet")]:
      for r in re.findall(r"<row[^>]*>(.*?)</row>", z.read(n).decode("utf-8", "ignore"), re.S):
        vs = []
        for at, b in re.findall(r"<c\b([^>]*)>(.*?)</c>", r, re.S):
          v = re.search(r"<v>(.*?)</v>", b, re.S)
          vs.append((sh[int(v.group(1))] if 't="s"' in at and int(v.group(1)) < len(sh) else v.group(1)) if v else "")
        out.append("\t".join(vs))
    return "\n".join(out) if out else "\n".join(sx(z.read(n).decode("utf-8", "ignore")) for n in nm if n.endswith(".xml"))


def ptext(p):
  exe = shutil.which("pdftotext")
  if exe:
    try:
      r = subprocess.run([exe, "-layout", str(p), "-"], capture_output=True, timeout=90)
      if r.returncode == 0 and r.stdout.strip():
        return r.stdout.decode("utf-8", "ignore"), True, "pdftotext"
    except Exception:
      pass
  try:
    out = []
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", p.read_bytes(), re.S):
      try:
        d = zlib.decompress(m.group(1))
      except Exception:
        continue
      out += re.findall(rb"\(((?:[^()\\]|\\.)*)\)\s*Tj", d)
      for t in re.finditer(rb"\[(.*?)\]\s*TJ", d, re.S):
        out += re.findall(rb"\(((?:[^()\\]|\\.)*)\)", t.group(1))
    t = b" ".join(out).decode("latin-1", "ignore").replace("\\(", "(").replace("\\)", ")")
    return t, len(t.strip()) > 40, "stdlib-zlib"
  except Exception as e:
    return "", False, "pdf failed: %s" % e


def xfile(p, k):
  try:
    if k == "text":
      raw = p.read_bytes()
      for e in ("utf-8", "utf-8-sig", "gb18030"):
        try:
          return raw.decode(e), True, e
        except Exception:
          pass
      return raw.decode("latin-1", "ignore"), True, "latin-1"
    if k == "pdf":
      return ptext(p)
    if k in ("docx", "xlsx", "pptx"):
      return ztext(p), True, "zipfile"
  except Exception as e:
    return "", False, "%s: %s" % (type(e).__name__, e)
  return "", False, "unparsed (%s)" % k


def disc(d, ctx, mb=12000000):
  out = []
  if not d.is_dir():
    ctx["errors"].append("输入目录不存在: %s" % d)
    return out
  for p in sorted(d.rglob("*")):
    if not p.is_file():
      continue
    rel = str(p.relative_to(d)).replace("\\", "/")
    try:
      sz = p.stat().st_size
    except Exception:
      sz = 0
    k = kind(p)
    r = {"path": rel, "kind": k, "bytes": sz, "parsed": False, "note": ""}
    if sz <= mb:
      t, ok, n = xfile(p, k)
      if ok:
        ctx["texts"][rel] = t
        r["parsed"] = bool(t.strip())
      r["note"] = n
    else:
      r["note"] = "skipped: too large"
    if k in ("png", "jpeg", "zip"):
      r["note"] = (r["note"] + "; 无 OCR，图像内容未读取").strip("; ")
    out.append(r)
  return out


def unwrap(o):
  if isinstance(o, list):
    return next((x for x in o if isinstance(x, dict)), {})
  if isinstance(o, dict):
    for k in ("cases", "items", "data"):
      if isinstance(o.get(k), list) and o[k] and isinstance(o[k][0], dict):
        m = dict(o)
        m.pop(k, None)
        m.update(o[k][0])
        return m
  return o if isinstance(o, dict) else {}


def lcase(d, ctx):
  cands = []
  if d.is_dir():
    cands = [d / "case.json"] if (d / "case.json").is_file() else \
      sorted([q for q in d.rglob("*case*.json") if q.is_file()], key=lambda q: (len(q.parts), str(q)))
  for q in cands:
    try:
      return unwrap(json.loads(q.read_text(encoding="utf-8", errors="ignore"))), str(q.relative_to(d))
    except Exception as e:
      ctx["errors"].append("case JSON 解析失败 %s: %s" % (q.name, e))
  if cands:
    ctx["errors"].append("case 文件存在但无法解析")
  return {}, ""


def fcon(case, d, ctx):
  for k, v in (case or {}).items():
    if re.search(r"output_?contract|输出契约|output_?schema", str(k), re.I):
      return v, "case.json:/" + str(k)
  for p in sorted(d.rglob("*")) if d.is_dir() else []:
    if p.is_file() and re.search(r"output[_-]?contract|契约", p.name, re.I):
      try:
        raw = p.read_text(encoding="utf-8", errors="ignore")
        return (json.loads(raw) if p.suffix.lower() == ".json" else raw), p.name
      except Exception as e:
        ctx["degradations"].append("契约解析失败 %s: %s" % (p.name, e))
  return None, ""


def clist(c):
  """output_contract -> ordered [(key, declared type)]; keys kept verbatim."""
  out = []

  def add(k, t=""):
    k = str(k or "").strip().strip("`* ")
    if k and k not in [x[0] for x in out]:
      out.append((k, str(t or "")))

  if isinstance(c, dict):
    for k, v in c.items():
      add(k, str(v.get("type") or ("object" if v.get("properties") else "")) if isinstance(v, dict)
        else ("array" if isinstance(v, list) else ("string" if isinstance(v, str) else "")))
  elif isinstance(c, list):
    for i in c:
      if isinstance(i, str):
        add(i)
      elif isinstance(i, dict):
        add(i.get("name") or i.get("field") or i.get("key") or i.get("id"), i.get("type") or "")
  elif isinstance(c, str):
    for ln in c.splitlines():
      if "|" not in ln:
        continue
      cs = [x.strip().strip("`* ") for x in ln.strip().strip("|").split("|")]
      if cs and cs[0] and not re.match(r"^[-: ]+$", cs[0]) and cs[0].lower() not in ("field", "字段", "key"):
        add(cs[0], cs[1] if len(cs) > 1 else "")
  return out


def backfill(cf, pool):
  """fill every contract key from the slot pool; missing -> null / [] / {} by declared type."""
  fill, used = {}, {}
  for k, t in cf:
    v = next((pool[s] for s, p in SL if re.search(p, str(k), re.I) and pool.get(s) not in (None, "", [], {})), None)
    used[k] = "slot" if v is not None else "default"
    tl = (t or "").lower()
    fill[k] = v if v is not None else ([] if ("array" in tl or "list" in tl) else ({} if ("object" in tl or "dict" in tl) else None))
  for k, _ in cf:
    if fill[k] in (None, {}, []) and re.search(r"plan|方案", str(k), re.I):
      fill[k] = {"protocol": "protocol.md", "steps": pool.get("steps") or []}
  return fill, used


def asrc(ctx, rel, loc, q, use):
  q = ("" if q is None else str(q))[:280].strip()
  t = ctx["texts"].get(rel, "")
  ok = bool(q) and (q in t or re.sub(r"\s+", " ", q) in re.sub(r"\s+", " ", t))
  sid = "S%02d" % (len(ctx["sources"]) + 1)
  ctx["sources"].append({"source_id": sid, "path": rel or None, "locator": loc, "quote": q, "used_for": use, "quote_verified": ok})
  if not ok and len(ctx["degradations"]) < 25:
    ctx["degradations"].append("%s 引文未逐字命中(%s %s)，quote_verified=false" % (sid, rel, loc))
  return sid


def qs(v):
  return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)


def ckey(n, u=""):
  s = str(n or "").lower()
  for k, p in CN:
    if re.search(p, s):
      return k
  return {"C": "temperature", "K": "temperature", "h": "time", "min": "time", "rpm": "agitation",
      "mL": "volume", "MPa": "pressure", "bar": "pressure", "%": "concentration"}.get(un(u)) or \
    (re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "_", s).strip("_")[:40] or "param")


def rget(R, k, n, u):
  e = R.get(k)
  if not e:
    e = R[k] = {"key": k, "name": str(n or k), "unit": un(u), "levels": [], "bounds": [], "step": None, "fixed": None, "names": []}
  if n and str(n) not in e["names"]:
    e["names"].append(str(n))
  if not e["unit"] and u:
    e["unit"] = un(u)
  return e


def addb(R, k, n, u, lo, hi, sid, kd, note=""):
  """register one bound with provenance; converts units when the dimension matches."""
  if lo is None and hi is None:
    return
  e = rget(R, k, n, u)
  uu = un(u)
  if uu and e["unit"] and uu != e["unit"]:
    a, b = cv(lo, uu, e["unit"]), cv(hi, uu, e["unit"])
    if a is None and b is None:
      e["bounds"].append({"lo": lo, "hi": hi, "kind": kd, "source_id": sid, "note": note + " 单位不可换算"})
      return
    lo, hi = a, b
  e["bounds"].append({"lo": lo, "hi": hi, "kind": kd, "source_id": sid, "note": note})


def eff(e):
  """tightest lower / upper bound and the source that sets each side."""
  lo = hi = bl = bh = None
  for b in e["bounds"]:
    if b["lo"] is not None and (lo is None or b["lo"] > lo):
      lo, bl = b["lo"], b
    if b["hi"] is not None and (hi is None or b["hi"] < hi):
      hi, bh = b["hi"], b
  return lo, hi, bl, bh


def rcost(M):
  """material cost per run from given unit price x per-run amount; unknown items listed, never invented."""
  it, unk, tot = [], [], 0.0
  for m in M:
    p, pu, a = m.get("unit_price"), (m.get("price_unit") or ""), m.get("amount")
    if p is None or a is None:
      unk.append(m["name"] + ("缺单价" if p is None else "缺用量"))
      continue
    q = cv(a, m.get("amount_unit") or "", pu) if (m.get("amount_unit") and pu and m["amount_unit"] != pu) else a
    q = a if q is None else q
    tot += p * q
    it.append({"item": m["name"], "unit_price": p, "price_unit": pu, "qty": rnd(q), "amount": rnd(p * q),
                   "formula": "%s×%s" % (ft(p), ft(q)), "source_id": m["source_id"]})
  return {"items": it, "unknown": unk, "subtotal": rnd(tot) if it else None}


def tbl(h, rows):
  return "\n".join(["| " + " | ".join(h) + " |", "|" + "|".join(["---"] * len(h)) + "|"] +
                     ["| " + " | ".join(str(c).replace("|", "/") for c in r) + " |" for r in rows])


def wcsv(p, rows):
  """rows: list of dicts; header = keys of the first row, list cells joined by ';'."""
  rows = list(rows)
  ks = list(rows[0].keys()) if rows else []
  with open(p, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(ks)
    w.writerows([[(";".join(map(str, r.get(k))) if isinstance(r.get(k), (list, tuple)) else r.get(k)) for k in ks] for r in rows])


def wj(p, o):
  Path(p).write_text(json.dumps(cl(o), ensure_ascii=False, indent=2), encoding="utf-8")


def tables(case, ctx):
  """flat list-of-dict tables from the case plus any CSV/TSV material."""
  out = [{"ptr": p, "rows": v} for p, v in walk(case) if isinstance(v, list) and len(v) >= 3
         and all(isinstance(x, dict) for x in v) and all(not isinstance(z, (dict, list)) for x in v for z in x.values())]
  for rel, t in list(ctx["texts"].items()):
    if rel.lower().endswith((".csv", ".tsv")):
      rs = [r for r in csv.reader(io.StringIO(t)) if r and any(c.strip() for c in r)]
      if len(rs) >= 3:
        h = [x.strip() for x in rs[0]]
        out.append({"ptr": rel, "rows": [dict(zip(h, r)) for r in rs[1:] if len(r) >= 2]})
  return out


def check(a):
  ctx = {"errors": [], "degradations": [], "texts": {}, "sources": []}
  out, ind = Path(a.output), Path(a.input)
  rep = {"skill_version": V, "at": iso(), "input": str(ind), "output": str(out)}
  try:
    disc(ind, ctx)
    case, _ = lcase(ind, ctx)
    cf = clist(fcon(case, ind, ctx)[0])
    res = json.loads((out / "result.json").read_text(encoding="utf-8")) if (out / "result.json").is_file() else {}
    miss = [k for k, _ in cf if k not in res]
    bad = [s["source_id"] for s in res.get("sources", []) if s.get("quote_verified") and s.get("path") in ctx["texts"]
               and s.get("quote") and s["quote"] not in ctx["texts"][s["path"]]]
    need = ["protocol.md", "parameter_plan.csv", "risk_table.csv"]
    rep.update({"contract_fields": len(cf), "contract_missing": miss, "status": res.get("status"),
          "quotes_checked": sum(1 for s in res.get("sources", []) if s.get("quote")), "quotes_failed": bad,
          "case_id_match": (str(res.get("case_id")) == str(case.get("case_id"))) if case else None,
          "missing_artifacts": [n for n in need if not (out / n).is_file()],
          "artifact_bytes": {n: ((out / n).stat().st_size if (out / n).is_file() else 0) for n in need}})
    rep["checks"] = {"json_valid": bool(res), "contract_complete": not miss, "quotes_ok": not bad,
                         "artifacts_ok": not rep["missing_artifacts"], "has_sources": bool(res.get("sources")),
                         "has_uncertainty": bool(res.get("uncertainty")), "has_pending": "pending_human" in res,
                         "has_case_id": bool(res.get("case_id"))}
    rep["pass"] = all(rep["checks"].values())
  except Exception as e:
    rep["error"] = "%s: %s" % (type(e).__name__, e)
    rep["pass"] = False
  try:
    wj(out / "verify_report.json", rep)
  except Exception:
    pass
  print(json.dumps({k: rep.get(k) for k in ("pass", "checks", "missing_artifacts", "quotes_failed")}, ensure_ascii=False))
  return 0


if __name__ == "__main__":
  ap = argparse.ArgumentParser(prog="verify.py", description="experiment-03 自检：契约字段、引文定位、主产物。")
  ap.add_argument("--input", "-i", default="/input")
  ap.add_argument("--output", "-o", default="/app/output")
  try:
    check(ap.parse_args())
  except SystemExit:
    pass
  except Exception:
    pass
  raise SystemExit(0)
