#!/usr/bin/env python3
"""extract.py - 材料读取（PDF/DOCX/文本）与"实体—连接—步骤—阶段—参数"确定性抽取。"""
import json, re, shutil, subprocess, zipfile
from pathlib import Path

EQ = ("反应器 换热器 冷凝器 分离器 蒸发器 干燥器 离心机 搅拌器 培养箱 摇床 灭菌锅 超净台 传感器 检测器 "
      "色谱仪 质谱仪 光谱仪 蠕动泵 注射泵 真空泵 气泵 水泵 进样泵 柱塞泵 隔膜泵 流量计 压力表 热电偶 "
      "温控器 电磁阀 阀门 储罐 储液罐 反应釜 烧瓶 锥形瓶 量筒 烧杯 试管 培养皿 膜组件 过滤器 电极 "
      "电解槽 电解池 水浴锅 恒温槽 烘箱 马弗炉 管式炉 色谱柱 吸附柱 混合器 天平 吸收瓶 冷阱").split()
WEAK = "泵 阀 罐 釜 柱 炉 槽 池 瓶 塔 膜 器 机 仪".split()
JUNK = set("装置 系统 设备 仪器 部件 容器 器件 管路 流程 过程 方法 条件 参数 指标".split())
STOP = set("在将用以由把对向从和与及并被为经的了后前内中上下入出至到量个台套只支根组批称取加置于"
           "约共各每两三四五六七八九十百第步°%自身该其此")
VB = ("送入 泵入 流入 进入 引入 通入 注入 输入 导入 输送 转入 移入 送至 送往 通往 连接到 连接至 接入 "
      "接到 供给 提供 排出 流出 导出 输出 返回 回流 循环 排入 收集 充入 压入 抽入 抽出 转移到 移至 加入").split()
SB = ("称取 量取 加入 加热 搅拌 离心 过滤 干燥 冷却 取样 测定 溶解 稀释 旋涂 刻蚀 沉积 培养 接种 灭菌 "
      "装柱 预平衡 冲洗 采集 测试 表征 分析 混合 浇筑 固化 封装 清洗 曝气 启动 驯化 监测 运行 调节 静置").split()
SB2 = tuple(v[:2] for v in SB)
NUM = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?(?:\s*[-–~]\s*\d+(?:\.\d+)?)?)\s*(°C|℃|K|min|h|s|mL|μL|L|rpm|MPa|"
                 r"kPa|Pa|bar|mol/L|mmol/L|mM|μM|g/L|mg/L|mL/min|L/min|L/h|sccm|psi|g|mg|μg|kg|nm|μm|mm|cm|"
                 r"kV|V|mA|W|kW|Hz|kHz|MHz|%|Da|kDa|d)(?![\w])")
HEAD = re.compile(r"^(?:#+\s*)?(?:第[一二三四五六七八九十]+(?:阶段|部分|步)|阶段\s*[一二三四1-4]|"
                  r"Stage\s*\d|Phase\s*\d|里程碑|Milestone)")


def sq(s):
  return re.sub(r"\s+", "", str(s or ""))


def deep(d, *ns):
  if isinstance(d, dict):
    f = {re.sub(r"[^a-z0-9]", "", str(k).lower()): v for k, v in d.items()}
    for n in ns:
      if f.get(re.sub(r"[^a-z0-9]", "", n.lower())) not in (None, ""):
        return f[re.sub(r"[^a-z0-9]", "", n.lower())]
    return next((r for x in d.values() for r in [deep(x, *ns)] if r is not None), None)
  if isinstance(d, list):
    return next((r for x in d for r in [deep(x, *ns)] if r is not None), None)
  return None


def jload(p):
  try:
    return json.loads(Path(p).read_text("utf-8", "replace"))
  except Exception as e:
    return {"__err__": str(e)}


def extract(p):
  e, h = p.suffix.lower(), b""
  try:
    h = p.open("rb").read(4)
  except Exception:
    pass
  if e == ".pdf" or h[:4] == b"%PDF":
    if not shutil.which("pdftotext"):
      return "", "pdf_no_text_tool"
    try:
      return subprocess.run(["pdftotext", "-layout", str(p), "-"], stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=150).stdout.decode("utf-8", "replace"), "pdftotext"
    except Exception:
      return "", "pdf_unreadable"
  if h[:2] == b"PK" or e in (".docx", ".pptx", ".xlsx"):
    try:
      with zipfile.ZipFile(p) as z:
        ns = sorted(n for n in z.namelist() if re.search(
            r"word/document\.xml|ppt/slides/slide\d+\.xml|xl/sharedStrings\.xml", n))
        return "\n\n".join(re.sub(r"<[^>]+>", " ", re.sub(r"</w:p>|</a:p>|</si>", "\n\n",
                                                           z.read(n).decode("utf-8", "replace")))
                           for n in ns), "ooxml"
    except Exception:
      return "", "ooxml_unreadable"
  if e in (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"):
    return "", "image_no_text"
  try:
    t = p.read_text("utf-8", "replace")
    return (t, "text") if "\x00" not in t[:300] else ("", "binary")
  except Exception:
    return "", "unreadable"


def blocks(pg):
  """段落切分：标题/编号项/项目符号各自成段，其余按空行、连续行合并（应对 PDF 折行）。"""
  out, buf = [], []

  def flush():
    if buf:
      out.append(" ".join(buf))
      buf.clear()
  for ln in pg.split("\n"):
    s = ln.strip()
    if not s:
      flush()
    elif re.match(r"^(#{1,6}\s|[-*•·]\s|[（(]?\d{1,2}[)）.、]\s|步骤\s*\d|Step\s*\d)", s):
      flush()
      out.append(s)
    else:
      buf.append(s)
  flush()
  return out


def ingest(inp, probs):
  case, cj, srcs, pars = {}, None, [], []
  for c in [inp / "case.json"] + sorted(inp.glob("case*.json")):
    if c.is_file():
      cj = c
      break
  if cj:
    d = jload(cj)
    case = {} if "__err__" in d else d
    if "__err__" in d:
      probs.append({"code": "case_json_invalid", "detail": d["__err__"][:150]})
  fn = sorted(x for x in inp.rglob("*") if x.is_file() and x != cj and not x.name.startswith(".")
              and x.stat().st_size < 40 << 20)
  for i, p in enumerate(fn, 1):
    t, kind = extract(p)
    s = {"id": "S%d" % i, "file": p.name, "path": str(p), "kind": kind, "chars": len(t)}
    srcs.append(s)
    if not t.strip():
      probs.append({"code": "material_no_text", "source": s["id"], "kind": kind})
      continue
    pages, j = t.count("\f") + 1, 0
    for pi, pg in enumerate(t.split("\f"), 1):
      for b in blocks(pg):
        j += 1
        pars.append({"sid": s["id"], "loc": "%s p%d ¶%d" % (s["id"], pi, j) if pages > 1
                     else "%s ¶%d" % (s["id"], j), "text": b})
    s["paragraphs"] = j
  return case, srcs, pars, cj


def names(pars):
  seen = {}
  for suf in EQ:
    for p in pars:
      t = p["text"]
      for m in re.finditer(re.escape(suf), t):
        k, j = m.start(), m.end()
        while k > 0 and j - k < 14 and t[k - 1].isalnum() and t[k - 1] not in STOP:
          k -= 1
        nm = re.sub(r"^[的了和与及将为是由把对向从在]+", "", t[k:j])
        if len(nm) > 1 and nm not in JUNK and not re.search(r"条件|过程|方法|指标|参数", nm):
          seen[nm] = seen.get(nm, 0) + 1
  if len(seen) < 3:
    for suf in WEAK:
      for p in pars:
        for m in re.finditer(re.escape(suf), p["text"]):
          k, j = m.start(), m.end()
          while k > 0 and j - k < 6 and p["text"][k - 1].isalnum() and p["text"][k - 1] not in STOP:
            k -= 1
          seen[p["text"][k:j]] = seen.get(p["text"][k:j], 0) + 1
  out = []
  for n in sorted(seen, key=lambda n: (-seen[n], -len(n))):
    if not any(n != k and n in k for k in out):
      out.append(n)
  return out[:12]


def role(n):
  if re.search(r"计|传感器|检测|电极|表$", n):
    return "measurement"
  if re.search(r"废|尾气|吸收瓶|排放", n):
    return "waste"
  if re.search(r"罐|储|料|瓶|袋", n):
    return "material"
  return "device" if re.search(r"泵|阀|反应器|釜|柱|炉|槽|池|塔|膜|机|器|管", n) else "other"


def auto(pars, case):
  nm, edges, steps, stages = names(pars), [], [], []
  loc = {n: next((p for p in pars if sq(n) in sq(p["text"])), None) for n in nm}
  nodes = [{"id": "N%d" % (i + 1), "label": n, "role": role(n),
            "params": [m.group(0).replace(" ", "") for m in NUM.finditer(loc[n]["text"][:200])][:2]
                      if loc[n] else [],
            "quote": loc[n]["text"][:200] if loc[n] else "",
            "locator": loc[n]["loc"] if loc[n] else "", "source": loc[n]["sid"] if loc[n] else "",
            "resolution": "exact" if loc[n] else "missing"} for i, n in enumerate(nm)]
  for a in nm:
    for b in nm:
      if a == b or len(edges) >= 14 or not loc[a] or not loc[b]:
        continue
      fa, fb = "N%d" % (nm.index(a) + 1), "N%d" % (nm.index(b) + 1)
      for p in pars:
        ta = sq(p["text"])
        if sq(a) in ta and sq(b) in ta:
          seg = p["text"][ta.index(sq(a)) + len(sq(a)):][:70]
          if b in seg and any(v in seg.split(b)[0] for v in VB) and not any(
              e["from"] == fa and e["to"] == fb for e in edges):
            edges.append({"id": "E%d" % (len(edges) + 1), "from": fa, "to": fb, "flow": "material",
                          "quote": p["text"][:200], "locator": p["loc"], "source": p["sid"],
                          "resolution": "exact"})
          break
  if not edges and len(nodes) > 1:  # 句序推断：显式标注，不冒充原文连接
    edges = [{"id": "E%d" % (i + 1), "from": nodes[i]["id"], "to": nodes[i + 1]["id"],
              "flow": "material", "label": "顺序", "inferred": True, "quote": nodes[i]["quote"],
              "locator": nodes[i]["locator"], "source": nodes[i]["source"], "resolution": "inferred"}
             for i in range(len(nodes) - 1)]
  for p in pars:
    t = p["text"]
    m = re.match(r"^[（(]?(\d{1,2})[)）.、]\s*(\S.{3,})$", t) or re.match(
        r"^(?:步骤|Step)\s*(\d+)[.:：]?\s*(.+)$", t, re.I)
    if len(steps) < 12 and (m or (len(t) < 150 and t[:2] in SB2)):
      steps.append({"id": "P%d" % (len(steps) + 1), "no": len(steps) + 1,
                    "text": (m.group(2) if m else t)[:80], "quote": t[:200], "locator": p["loc"],
                    "source": p["sid"], "resolution": "exact"})
    elif len(stages) < 5 and (HEAD.match(t) or re.match(r"^(阶段|里程碑)", t)):
      stages.append({"id": "G%d" % (len(stages) + 1), "label": re.sub(r"^#+\s*", "", t)[:24],
                     "quote": t[:160], "locator": p["loc"], "source": p["sid"], "resolution": "exact"})
  order = [p["loc"] for p in pars]
  for s in steps:  # 步骤归入其前最近的阶段
    g = [x for x in stages if s["locator"] in order and
         order.index(x["locator"]) <= order.index(s["locator"])]
    s["stage"] = g[-1]["id"] if g else None
  ttl = next((v.strip()[:60] for v in (deep(case, "figure_title"), deep(case, "title"))
              if isinstance(v, str) and v.strip()), "") or next(
      (p["text"][:60] for p in pars[:8] if 6 <= len(p["text"]) <= 40 and
       re.search(r"图|Fig|装置|流程|路线|方法", p["text"])), "")
  return {"title": ttl or "实验装置与技术路线图", "figure_kind": "hybrid", "lang": "zh",
          "caption": "图 1　实验装置连接与技术路线示意（图元均标注来源，见 content_map.json）",
          "nodes": nodes[:12], "edges": edges, "steps": steps, "stages": stages,
          "global_params": [m.group(0).replace(" ", "") for p in pars for m in
                            NUM.finditer(p["text"])][:6], "source": "auto"}
