# -*- coding: utf-8 -*-
"""feas.py — 审查内核（标准库）：解析/归一化、量纲算术、证据定位、protocol.md 渲染。"""
import math
import re
import unicodedata

VERSION = "1.0.0"
CLASSES = (("HYPOTHESIS", "假设与变量"), ("CONTROL", "对照组"), ("RESOURCE", "设备与材料"),
           ("TIME", "时间与成本"), ("PARAM", "参数范围"), ("RISK", "风险与异常"),
           ("ETHICS", "伦理与安全"))
CLS_CN = dict(CLASSES)
CLS_ORDER = [c for c, _ in CLASSES]
UNIT = {"ng": ("mass", 1e-6), "ug": ("mass", 1e-3), "mg": ("mass", 1.0), "g": ("mass", 1e3),
        "kg": ("mass", 1e6), "nl": ("volume", 1e-3), "ul": ("volume", 1.0), "ml": ("volume", 1e3),
        "l": ("volume", 1e6), "s": ("time", 1 / 60.0), "min": ("time", 1.0), "h": ("time", 60.0),
        "hr": ("time", 60.0), "d": ("time", 1440.0), "wk": ("time", 10080.0), "mo": ("time", 43200.0),
        "pm": ("conc", 1e-9), "nm": ("conc", 1e-6), "um": ("conc", 1e-3), "mm": ("conc", 1.0),
        "°c": ("temp", 1.0), "rcf": ("rcf", 1.0), "rpm": ("rpm", 1.0), "%": ("pct", 1.0),
        "hz": ("freq", 1.0), "bar": ("press", 100.0)}
UWORD = {"weeks": ("time", 10080.0), "week": ("time", 10080.0), "days": ("time", 1440.0),
         "day": ("time", 1440.0), "hours": ("time", 60.0), "hour": ("time", 60.0)}
UA = ("rcf|rpm|°c|ng/ml|ug/ml|mg/ml|months|weeks|hours|mins|days|month|week|hour|day|mo|wk|"
      "min|hr|pm|nm|um|mm|mg|kg|ng|ug|ml|ul|nl|hz|kpa|bar|d|h|s|g|l|%")
QRE = re.compile(r"(?<![a-z0-9.])([-+]?\d+(?:\.\d+)?)\s*(" + UA + r")(?![a-z])", re.I)
RRE = re.compile(r"(?<![a-z0-9.])([-+]?\d+(?:\.\d+)?)\s*(?:-|~|to|至|到)\s*"
                 r"([-+]?\d+(?:\.\d+)?)\s*(" + UA + r")(?![a-z])", re.I)
UPE = re.compile(r"(?:<=|≤|up to|max(?:imum)?\.?|最大|至多|不超过)\s*"
                 r"([-+]?\d+(?:\.\d+)?)\s*(" + UA + r")(?![a-z])", re.I)
GROUPS = {"plans": ("plan", "candidate", "version", "protocol", "方案", "候选", "版本"),
          "equipment": ("equipment", "instrument", "device", "apparatus", "asset", "设备", "仪器"),
          "materials": ("reagent", "material", "consumable", "kit", "试剂", "材料", "耗材"),
          "params": ("parameter", "param", "factor", "参数", "因素", "取值")}
TRIG = {"human": r"人体|受试者|患者|志愿者|血清|血浆|血样|尿液|活检|pbmc|human|patient|donor|"
                 r"serum|plasma|blood|tissue|biopsy",
        "animal": r"动物|小鼠|大鼠|兔|斑马鱼|猴|mice|mouse|\brat\b|rabbit|zebrafish",
        "hazard": r"危化|有毒|致癌|放射性|病原|病毒|bsl-?[23]|甲醛|氯仿|苯酚|叠氮|phenol|"
                  r"chloroform|formaldehyde|radioactiv|toxic|carcinogen",
        "pdata": r"个人数据|隐私|基因数据|gdpr|可识别|测序数据|genomic data"}
FB = "\n".join("%s-90|%s|%s 检查项库缺失|R-GEN|major|0|-|恢复 references/checks.md"
                % (c[:3], c, cn) for c, cn in CLASSES)


def norm_txt(s):
    s = s if isinstance(s, str) else str(s)
    s = unicodedata.normalize("NFKC", s)
    for a, b in (("μ", "u"), ("µ", "u"), ("℃", "°c"), ("°C", "°c"), ("×g", "rcf"), ("xg", "rcf"),
                 ("\u00a0", " "), ("\u3000", " "), ("–", "-"), ("—", "-")):
        s = s.replace(a, b)
    return s


def quantities(text):
    out = []
    for m in QRE.finditer(norm_txt(text)):
        u = m.group(2).lower()
        dim, f = UWORD.get(u) or UNIT.get(u, (None, 1.0))
        if u == "nm" and float(m.group(1)) >= 100:
            dim, f = "length", 1.0
        try:
            v = float(m.group(1))
        except ValueError:
            continue
        out.append({"value": v, "unit": u, "dim": dim, "base": v * f, "raw": m.group(0)})
    return out


def ranges_in(text):
    out, t = [], norm_txt(text)
    for m in RRE.finditer(t):
        u, lo, hi = m.group(3).lower(), float(m.group(1)), float(m.group(2))
        f = UNIT.get(u, (None, 1.0))[1]
        out.append({"lo": min(lo, hi) * f, "hi": max(lo, hi) * f, "unit": u,
                    "dim": UNIT.get(u, (None, 1))[0]})
    for m in UPE.finditer(t):
        u = m.group(2).lower()
        out.append({"lo": None, "hi": float(m.group(1)) * UNIT.get(u, (None, 1.0))[1], "unit": u,
                    "dim": UNIT.get(u, (None, 1))[0]})
    return out


def fmt(x, nd=2):
    if x is None:
        return "NA"
    if isinstance(x, float) and x == int(x) and abs(x) < 1e12:
        return str(int(x))
    return ("%." + str(nd) + "f") % x if isinstance(x, float) else str(x)


def load_lib(base):
    """解析 checks.md 的 checks 块。"""
    txt = ""
    for p in (base / "references" / "checks.md", base.parent / "references" / "checks.md"):
        try:
            if p.is_file():
                txt = p.read_text(encoding="utf-8", errors="replace")
                break
        except OSError:
            txt = ""
    m = re.search(r"```checks\n(.*?)```", txt, re.S)
    lib = {}
    for ln in (m.group(1) if m else FB).splitlines():
        p = [x.strip() for x in ln.split("|")]
        if len(p) >= 8:
            lib[p[0]] = {"id": p[0], "cls": p[1], "item": p[2], "basis": p[3], "sev": p[4],
                         "human": p[5] == "1", "action": p[7],
                         "groups": [] if p[6] == "-" else
                         [[a.strip() for a in g.split(";") if a.strip()]
                          for g in p[6].split("@@")]}
    return lib, ("checks.md" if m else "builtin-fallback")


def _esc(k):
    return str(k).replace("~", "~0").replace("/", "~1")


def walk(obj, ptr="", d=0):
    if d > 8:
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = ptr + "/" + _esc(k)
            yield p, k, v
            yield from walk(v, p, d + 1)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            p = ptr + "/" + str(i)
            if isinstance(v, str):
                yield p, i, v
            else:
                yield from walk(v, p, d + 1)


def collect_lists(node, g, lo=1, hi=24):
    return [(ptr, v) for ptr, k, v in walk(node)
            if isinstance(v, list) and lo <= len(v) <= hi and v
            and all(isinstance(i, (dict, str)) for i in v)
            and any(p in str(k).lower() for p in GROUPS[g])]


class Pool:
    """可检索文本 + 行级 locator。"""

    def __init__(self, sid, kind="case"):
        self.sid, self.kind, self.lines, self._t = sid, kind, [], None

    def add(self, text, ptr=None):
        for ln in str(text).split("\n"):
            if ln.strip():
                self.lines.append((ptr, ln.rstrip()))
        self._t = None

    @property
    def text(self):
        if self._t is None:
            self._t = norm_txt("\n".join(t for _, t in self.lines))
        return self._t

    def subset(self, prefix):
        p = Pool(self.sid, self.kind)
        p.lines = [x for x in self.lines if (x[0] or "").startswith(prefix)]
        return p

    def locator(self, pos):
        n = self.text.count("\n", 0, max(0, pos)) + 1
        ptr = self.lines[n - 1][0] if 0 < n <= len(self.lines) else None
        if self.kind == "case" and ptr:
            return "%s#%s" % (self.sid, ptr)
        return "%s#L%d" % (self.sid, n)

    def sentence(self, pos):
        t = self.text
        if not t:
            return ""
        a = max([t.rfind(c, 0, pos) for c in "。！？；\n.;"] + [-1]) + 1
        e = [x for x in (t.find(c, pos) for c in "。！？；\n") if x >= 0]
        s = t[a:(min(e) if e else len(t))].strip()
        return (s if len(s) >= 8 else t[max(0, pos - 50):pos + 80].strip())[:400]


def ev(pool, pos):
    return {"source_id": pool.sid, "locator": pool.locator(pos), "quote": pool.sentence(pos)}


def probe(pool, groups):
    pos = None
    for alts in groups:
        if not alts:
            continue
        m = re.search("|".join(re.escape(a) for a in alts), pool.text, re.I)
        if not m:
            return None
        pos = m.start() if pos is None else pos
    return pos


def ev_first(pool, names):
    tl = pool.text.lower()
    for n in names:
        k = (n or "")[:6].lower()
        if k and k in tl:
            return ev(pool, tl.find(k))
    return None


def _num(x):
    if isinstance(x, bool):
        return None
    if isinstance(x, (int, float)):
        return float(x)
    m = re.search(r"[-+]?\d+(?:\.\d+)?", norm_txt(x)) if isinstance(x, str) else None
    return float(m.group(0)) if m else None


def _item(ptr, it, asset):
    """设备/试剂归一化。"""
    d = dict(it) if isinstance(it, dict) else {"name": str(it)}
    nm = next((d[k].strip() for k in ("name", "item", "device", "instrument", "reagent",
                                      "material", "model", "名称", "设备", "试剂", "材料")
               if isinstance(d.get(k), str) and d[k].strip()), "")
    blob = " ".join(norm_txt(v) for v in d.values() if isinstance(v, (str, int, float)))
    r = {"name": (nm or blob[:60] or "unnamed")[:120], "ptr": ptr, "status": "", "lead": None,
         "price": None, "spec": "", "stock": None, "raw": blob[:200],
         "ranges": ranges_in(blob) if asset else []}
    for k, v in d.items():
        kl = str(k).lower()
        if any(s in kl for s in ("status", "avail", "state", "状态", "可用", "归属")):
            r["status"] = r["status"] or norm_txt(str(v))[:100]
        elif any(s in kl for s in ("lead", "货期", "周期", "wait", "booking")):
            r["lead"] = r["lead"] if r["lead"] is not None else _num(v)
        elif any(s in kl for s in ("price", "cost", "fee", "价格", "费用", "单价", "报价")):
            r["price"] = r["price"] if r["price"] is not None else _num(v)
        elif any(s in kl for s in ("spec", "grade", "range", "量程", "规格", "精度")):
            r["spec"] = r["spec"] or norm_txt(str(v))[:100]
        elif any(s in kl for s in ("stock", "inventory", "库存", "现货", "余量")):
            q = quantities(str(v))
            r["stock"] = r["stock"] or (q[0] if q else None)
    return r


def get_params(case, pool):
    """结构化参数（dict 列表）+ 文本 `名称: 值 单位`，去重。"""
    out = []
    for ptr, lst in collect_lists(case, "params"):
        for j, it in enumerate(lst):
            if not isinstance(it, dict):
                continue
            nm = next((it[k].strip() for k in ("name", "parameter", "param", "指标")
                       if isinstance(it.get(k), str) and it[k].strip()), "")
            val, unit, rng = None, "", None
            for k, v in it.items():
                kl = str(k).lower()
                if val is None and any(s in kl for s in ("value", "target", "setting", "值", "设定")):
                    q = quantities(str(v))
                    val, unit = (q[0]["value"], q[0]["unit"]) if q else (_num(v), unit)
                elif any(s in kl for s in ("unit", "单位")):
                    unit = norm_txt(str(v)).strip().lower()
                elif any(s in kl for s in ("range", "domain", "tol", "范围", "容差", "域")):
                    rng = norm_txt(str(v))[:120]
            if nm:
                out.append({"name": nm[:60], "value": val, "unit": unit, "range": rng,
                            "dim": UNIT.get(unit, (None, 1))[0] if unit else None,
                            "ptr": ptr + "/%d" % j})
    for ptr, ln in (pool.lines if pool else []):
        n = norm_txt(ln)
        for m in re.finditer(r"([A-Za-z\u4e00-\u9fa5][\w\u4e00-\u9fa5\-/]{0,18})\s*[:=为]\s*"
                             r"([-+]?\d+(?:\.\d+)?)\s*(" + UA + r")(?![a-z])", n, re.I):
            u = m.group(3).lower()
            out.append({"name": m.group(1).strip()[:40], "value": float(m.group(2)), "unit": u,
                        "dim": UNIT.get(u, (None, 1))[0], "range": None, "ptr": ptr})
    uniq, seen = [], set()
    for p in out:
        k = (p["name"].lower(), p["value"], p["unit"])
        if k not in seen:
            seen.add(k)
            uniq.append(p)
    return uniq[:60]


BOOST = (("budget", ("budget", "预算", "经费")),
         ("deadline", ("deadline", "horizon", "window", "周期", "期限")),
         ("personnel", ("personnel", "staff", "人员", "fte", "人数")))


def harvest(case):
    """收集设备/材料/参数/预算/时间窗/人力。"""
    ctx = {"assets": [], "materials": [], "params": [], "budget": None, "budget_src": "",
           "deadline": None, "deadline_src": "", "personnel": None}
    for ptr, lst in collect_lists(case, "equipment"):
        ctx["assets"] += [_item(ptr + "/%d" % i, x, True) for i, x in enumerate(lst)]
    for ptr, lst in collect_lists(case, "materials"):
        ctx["materials"] += [_item(ptr + "/%d" % i, x, False) for i, x in enumerate(lst)]
    ctx["params"] = get_params(case, None)
    for ptr, k, v in walk(case):
        kl = (str(k) + " " + str(ptr)).lower()
        if isinstance(v, bool):
            continue
        for f, keys in BOOST:
            if ctx[f] is not None or not any(x in kl for x in keys):
                continue
            if isinstance(v, (int, float)):
                if f == "deadline" and not 0 < float(v) < 3650:
                    continue
                if f == "personnel" and v <= 0:
                    continue
                ctx[f] = float(v)
                if f != "personnel":
                    ctx[f + "_src"] = ptr
            elif isinstance(v, str):
                for q in quantities(v):
                    if f == "budget" and q["dim"] != "time":
                        ctx[f], ctx[f + "_src"] = q["value"], ptr
                        break
                    if f == "deadline" and q["dim"] == "time":
                        ctx[f], ctx[f + "_src"] = q["base"] / 1440.0, ptr
                        break
    return ctx


def _mk(raw, i, ptr, pool, sources):
    pl = {"id": "v%d" % (i + 1), "label": "v%d" % (i + 1), "pointer": ptr, "steps": [],
          "groups": [], "pool": None, "source": "case.json", "params": []}
    if isinstance(raw, str):
        if raw in sources:
            pl["pool"], pl["label"], pl["source"] = sources[raw], raw[:60], raw
            return pl
        pl["pool"] = Pool("case.json")
        pl["pool"].add(raw, ptr)
        pl["params"] = get_params({}, pl["pool"])
        return pl
    if isinstance(raw, dict):
        for k in ("id", "name", "version", "label", "title", "编号", "名称", "版本"):
            if isinstance(raw.get(k), str) and raw[k].strip():
                pl["label"] = raw[k].strip()[:60]
                break
        for k, v in raw.items():
            kl = str(k).lower()
            if isinstance(v, list) and any(s in kl for s in ("step", "procedure", "流程", "步骤")):
                pl["steps"] = [x for x in v if isinstance(x, (dict, str))]
            if isinstance(v, list) and any(s in kl for s in ("group", "arm", "组")):
                pl["groups"] = [x if isinstance(x, str) else str(x) for x in v]
    pl["pool"] = pool.subset(ptr) if (ptr and pool is not None) else pool
    if pl["pool"] is None or not pl["pool"].lines:
        pl["pool"] = pool or Pool("case.json")
    pl["params"] = get_params(raw if isinstance(raw, dict) else {}, pl["pool"])
    return pl


def build_plans(case, pool, sources):
    cands = collect_lists(case, "plans")
    if cands:
        cands.sort(key=lambda x: (-len(x[1]), len(str(x[0]))))
        ptr, lst = cands[0]
        plans = [_mk(r, i, "%s/%d" % (ptr, i), pool, sources) for i, r in enumerate(lst[:6])]
    else:
        plans = [_mk(k, i, None, pool, sources) for i, k in enumerate(list(sources)[:3])]
    return plans or [_mk(case, 0, None, pool, sources)]


def _tbl(head, body):
    if not body:
        return "_（无）_\n"
    rows = [head] + body
    return "\n".join("| " + " | ".join(str(x).replace("|", "/").replace("\n", " ")
                                       for x in r) + " |" for r in rows) + "\n"


def _csv(rows):
    return "\n".join(",".join('"%s"' % str(c).replace('"', "'").replace("\n", " ")
                              for c in r) for r in rows) + "\n"


def resource_rows(ctx):
    return [[x["name"][:34], k, (x["spec"] or x["raw"])[:26], x["status"] or "—",
             (x["stock"] or {}).get("raw", "—") if k == "耗材" else "—",
             fmt(x["lead"]), fmt(x["price"])]
            for k, xs in (("设备", ctx["assets"]), ("耗材", ctx["materials"])) for x in xs]


def protocol_md(res):
    """可执行方案（protocol.md）。缺失写〔待补〕。"""
    ps = res.get("plans") or [{}]
    p = next((x for x in ps if x.get("plan") == res.get("recommended")), ps[0])
    ch = res.get("checks") or []
    q = {}
    for c in ch:
        if c.get("evidence") and c["check_id"] not in q:
            q[c["check_id"]] = c["evidence"][0]["quote"]
    L = ["# 实验方案与可行性审查：%s" % res.get("case_id", "case"), "",
         "> 结论 **%s**（基准版本 %s）。Skill experiment-feasibility-review v%s 依据输入材料生成；"
         "〔待补〕= 需人工确认。" % (p.get("verdict", "partial"),
                                          p.get("plan"), VERSION), "",
         "## 0. 一页结论", "",
         _tbl(["项", "值"], [["结论", p.get("verdict")], ["覆盖率", p.get("coverage")],
                             ["推荐版本", res.get("recommended")],
                             ["阻断项", "、".join(b["check_id"] for b in p.get("blocking", []))
                              or "无"], ["运行状态", res.get("status")]]),
         "### 执行条件（满足后才能开工）", ""]
    L += ["%d. %s" % (i + 1, c) for i, c in enumerate(p.get("conditions") or [])] or ["_无_"]
    L += ["", "## 1. 目标与假设", "",
          "- 目标：%s" % ((res.get("task") or {}).get("goal") or "〔待补〕"),
          "- 假设（原文）：%s" % (q.get("H-01") or "〔待补〕"), "",
          "## 2. 变量与判读", "",
          _tbl(["项", "方案原文"], [["自变量", (q.get("H-02") or "〔待补〕")[:120]],
                                   ["因变量", (q.get("H-03") or "〔待补〕")[:120]],
                                   ["判读标准", (q.get("H-04") or "〔待补〕")[:120]]]),
          "## 3. 分组", "",
          "- 分组：%s" % ("／".join(str(g)[:20] for g in (res.get("groups") or []))
                          or "〔待补：见 C-01/C-04〕"),
          "## 4. 材料与仪器", "",
          _tbl(["名称", "类型", "规格", "状态", "库存", "货期d", "单价"],
               res.get("resource_rows") or [["〔待补〕", "", "", "", "", "", ""]]),
          "## 5. 参数表", "",
          _tbl(["参数", "值", "单位", "输入范围"],
               res.get("param_rows") or [["〔待补〕", "", "", ""]]),
          "## 6. 步骤", "",
          _tbl(["步骤", "时长"], res.get("step_rows") or [["〔待补〕", "无步骤表"]]),
          "## 7. 判读/停止", "",
          "- 判读：%s" % ((q.get("H-04") or "〔待补〕")[:160]),
          "- 停止/转人工：%s" % ((q.get("K-06") or "〔待补〕")[:160]), "",
          "## 8. 风险处置", "",
          _tbl(["风险", "判定", "预案/需补"],
               [[c["item"], c["verdict"], ((c["evidence"] or [{}])[0].get("quote", "")
                                          or c["action"])[:60]]
                for c in ch if c["class"] == "RISK" and c["plan"] == p.get("plan")]),
          "## 9. 伦理与安全", "",
          _tbl(["项", "判定", "所需动作"],
               [[c["item"], c["verdict"], c["action"][:60]] for c in ch
                if c["class"] == "ETHICS" and c["verdict"] != "na"]),
          "## 10. 缺失信息", ""]
    L += ["- [%s] %s → %s" % (g.get("class"), g.get("item"), g.get("supply"))
          for g in (res.get("gaps") or [])[:40]]
    L += ["", "---", "证据见 `check_matrix.csv`。生成 %s · Skill v%s"
          % ((res.get("runtime") or {}).get("finished_at", ""), VERSION)]
    return "\n".join(L)
