"""formula_core.py - MathML->LaTeX engine, text mining, envelope. stdlib only."""
import ast
import html
import math
import re
from xml.etree import ElementTree as ET

_G = list(zip("αβγδεζηθικλμνξοπρστυφχψω",
              "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi "
              "omicron pi rho sigma tau upsilon phi chi psi omega".split()))
_G += list(zip("ΓΔΘΛΞΠΣΥΦΨΩ",
               "Gamma Delta Theta Lambda Xi Pi Sigma Upsilon Phi Psi Omega".split()))
GREEK = {k: "\\" + v for k, v in _G}
GREEK.update({"∂": "\\partial"})
FUNCS = {"sin", "cos", "tan", "cot", "sec", "csc", "log", "ln", "lg", "exp", "max", "min",
         "lim", "sup", "inf", "det", "arg"}
OPS = {"-": "-", "+": "+", "=": "=", "<": "<", ">": ">", "*": "*", "/": "/", ",": ",",
       ";": ";", "(": "(", ")": ")", "[": "[", "]": "]", "|": "|", "×": "\\times",
       "·": "\\cdot", "±": "\\pm", "≤": "\\le", "≥": "\\ge", "≠": "\\neq",
       "≈": "\\approx", "∼": "\\sim", "∝": "\\propto", "→": "\\to", "∈": "\\in",
       "∑": "\\sum", "∫": "\\int", "√": "\\sqrt", "°": "^{\\circ}",
       "%": "\\%", "_": "\\_"}
BIG = {"\\sum", "\\prod", "\\int", "lim", "max", "min"}
CONT = {"disp-formula", "formula", "equation"}
CUES = [("substitution", r"substitut"), ("rearrangement", r"rearrang|solv\w* for"),
        ("assumption", r"assum|suppos"), ("approximation", r"approximat|negligib|lineariz"),
        ("limit", r"in the limit|for small|for large"), ("integration", r"integrat"),
        ("differentiation", r"differentiat|derivative"),
        ("result", r"yields|gives|we obtain|follows|therefore|hence")]
DEF_WHERE = (r"(?:where|here|in which|with)\s+([^\W\d_][\w]{0,9})\s+(?:is|are|denotes|"
             r"represents|is the|is a|is an|is defined as)\s+([^.;]{3,200})")
DEF_AND = (r"(?:\band|,)\s+([^\W\d_][\w]{0,9})\s+(?:is|are)\s+(?:the|a|an)?\s*([^.;]{3,200})")
VAL_ASSIGN = (r"(?<![\w.])([^\W\d_][\w]{0,9})\s*=\s*(-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)\s*"
              r"([A-Za-z\u00b5\u03bc\u00b0\u03a9%/^0-9\u00b7.\-]{0,12})")
UNIT_IN = (r"(?:in|units of|measured in|expressed in)\s+"
           r"([A-Za-z\u00b5\u03bc\u00b0\u03a9%/\u00b7^0-9\-]{1,20})")

def n(s):
    return re.sub(r"\s+", " ", (s or "").replace("\u2212", "-")).strip()

def local(tag):
    
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag.rsplit(":", 1)[-1]

def text_of(el):
    return "".join(el.itertext())

# ---------------------------------------------------------------- xml handling
def _ent(m):
    if m.group(1) in ("lt", "gt", "amp", "quot", "apos"):
        return m.group(0)
    rep = html.entities.html5.get(m.group(1) + ";") or html.entities.html5.get(m.group(1))
    return "".join("&#x%X;" % ord(c) for c in rep) if rep else "&amp;" + m.group(1) + ";"

def parse_xml(txt):
    
    try:
        return ET.fromstring(txt), "parsed"
    except ET.ParseError:
        pass
    body = re.sub(r"^\s*<\?xml[^>]*\?>", "", txt)
    body = re.sub(r"<!DOCTYPE[^>]*>", "", body, flags=re.S)
    body = re.sub(r"&([A-Za-z][A-Za-z0-9]{1,30});", _ent, body)
    return ET.fromstring(body), "parsed_after_entity_repair"

def read_text(path):
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")

def xpath_of(root, target):
    
    out = []

    def walk(node, cur):
        if node is target:
            out.extend(cur)
            return True
        seen = {}
        for k in list(node):
            ln = local(k.tag)
            seen[ln] = seen.get(ln, 0) + 1
            if walk(k, cur + ["%s[%d]" % (ln, seen[ln])]):
                return True
        return False

    return "/" + "/".join(out) if walk(root, [local(root.tag) + "[1]"]) else ""

def attr_id(el):
    for k in ("id", "source_id", "{http://www.w3.org/XML/1998/namespace}id"):
        if el.get(k):
            return el.get(k)
    return ""

def collect_formulas(root):
    
    out, done = [], set()
    for el in root.iter():
        if local(el.tag) not in CONT:
            continue
        math_el = next((m for m in el.iter() if local(m.tag) == "math"), None)
        if math_el is None or id(math_el) in done:
            continue
        done.add(id(math_el))
        label = next((n(text_of(k)) for k in el.iter() if local(k.tag) == "label"), "")
        tex = next((n(text_of(a)) for a in math_el.iter() if local(a.tag) == "annotation"
                    and "tex" in (a.get("encoding") or "").lower()), "")
        out.append({"node": math_el, "fid": attr_id(el) or attr_id(math_el), "eq": label, "tex": tex,
                    "path": xpath_of(root, math_el),
                    "raw": n(ET.tostring(math_el, encoding="unicode"))[:1500]})
    for m in [x for x in root.iter() if local(x.tag) == "math"]:
        if id(m) not in done:
            done.add(id(m))
            out.append({"node": m, "fid": attr_id(m), "eq": "", "path": xpath_of(root, m),
                        "raw": n(ET.tostring(m, encoding="unicode"))[:1500]})
    return out

def iter_blocks(root):
    
    out, seen = [], set()

    def walk(node):
        ln = local(node.tag)
        if ln in ("math", "inline-formula", "disp-formula"):
            return
        if ln in ("p", "title", "caption", "td", "th", "list-item"):
            t = n(text_of(node))
            if len(t) >= 8 and t not in seen:
                seen.add(t)
                out.append({"path": xpath_of(root, node), "text": t})
            return
        for k in list(node):
            walk(k)

    walk(root)
    return out

# --------------------------------------------------------------- latex mapping
def _bal(s):
    d, i = 0, 0
    while i < len(s):
        if s[i] == "\\":
            i += 2
            continue
        d += {"{": 1, "}": -1}.get(s[i], 0)
        if d < 0:
            return False
        i += 1
    return d == 0

def _g(s):
    s = s.strip()
    if not s:
        return "{}"
    if re.fullmatch(r"[A-Za-z0-9]|\\[A-Za-z]+", s):
        return s
    return s if (s[0] == "{" and s[-1] == "}" and _bal(s)) else "{" + s + "}"

def esc_ch(c):
    return OPS.get(c) or (c if c.isalnum() else "\\square")

def mi_latex(el):
    s = n(text_of(el))
    if not s:
        return ""
    variant = (el.get("mathvariant") or "").lower()
    body = "".join(GREEK.get(c, esc_ch(c)) for c in s)
    if len(s) == 1:
        return body
    if s in FUNCS:
        return "\\" + s
    return ("\\mathrm{%s}" % body) if s.isalpha() else body

def to_latex(el, flags=None, depth=0):
    
    flags = flags if flags is not None else []
    if depth > 60:
        flags.append("max_nesting_depth")
        return "\\square"
    ln, kids = local(el.tag), list(el)
    if ln == "semantics":
        for k in kids:
            if local(k.tag) == "annotation" and "tex" in (k.get("encoding") or "").lower():
                return n(text_of(k))
        return to_latex(kids[0], flags, depth + 1) if kids else ""
    if ln == "mi":
        return mi_latex(el)
    if ln == "mn":
        return n(text_of(el)).replace(" ", "")
    if ln == "mtext":
        return "\\text{%s}" % n(text_of(el)).replace("_", "\\_").replace("%", "\\%")
    if ln == "mo":
        s = n(text_of(el))
        return OPS.get(s) or "".join(OPS.get(c, esc_ch(c)) for c in s)
    if ln in ("mspace", "none", "prescripts"):
        return ""
    if ln in ("mstyle", "mpadded", "mphantom", "menclose", "math", "mrow", "mtd"):
        return "".join(filter(None, [to_latex(k, flags, depth + 1) for k in kids]))
    if ln == "mfrac":
        if len(kids) < 2:
            flags.append("mfrac_arity")
            return "\\frac%s{}" % _g(to_latex(kids[0], flags, depth + 1) if kids else "")
        return "\\frac%s%s" % (_g(to_latex(kids[0], flags, depth + 1)),
                              _g(to_latex(kids[1], flags, depth + 1)))
    if ln == "msqrt":
        return "\\sqrt{%s}" % "".join(to_latex(k, flags, depth + 1) for k in kids)
    if ln == "mroot":
        if len(kids) < 2:
            flags.append("mroot_arity")
            return "\\sqrt{}"
        return "\\sqrt[%s]{%s}" % (to_latex(kids[1], flags, depth + 1),
                                   to_latex(kids[0], flags, depth + 1))
    if ln in ("msub", "msup", "msubsup"):
        if len(kids) < 2:
            flags.append(ln + "_arity")
            return "".join(to_latex(k, flags, depth + 1) for k in kids)
        base = to_latex(kids[0], flags, depth + 1)
        sub = to_latex(kids[1], flags, depth + 1)
        if ln == "msub":
            return "%s_{%s}" % (_g(base), sub)
        sup = to_latex(kids[2], flags, depth + 1) if len(kids) > 2 else ""
        return "%s^{%s}" % (_g(base), sub) if ln == "msup" else "%s_{%s}^{%s}" % (
            _g(base), sub, sup)
    if ln in ("munder", "mover", "munderover"):
        base = to_latex(kids[0], flags, depth + 1) if kids else ""
        lo = to_latex(kids[1], flags, depth + 1) if len(kids) > 1 else ""
        hi = to_latex(kids[2], flags, depth + 1) if len(kids) > 2 else ""
        if ln == "munder":
            return "%s_{%s}" % (_g(base), lo)
        if ln == "mover":
            if n(text_of(kids[1]) if len(kids) > 1 else "") in ("^", "~", "¯"):
                flags.append("accent_normalized")
                return "\\overline%s" % _g(base)
            return "%s^{%s}" % (_g(base), lo)
        if base.strip() not in BIG:
            flags.append("munderover_nonbigop")
        return "%s_{%s}^{%s}" % (_g(base) if base.strip() not in BIG else base, lo, hi)
    if ln == "mfenced":
        op, cl = el.get("open", "("), el.get("close", ")")
        inner = ", ".join(to_latex(k, flags, depth + 1) for k in kids)
        if op or cl:
            return "\\left%s %s\\right%s" % (OPS.get(op, op) or ".", inner, OPS.get(cl, cl) or ".")
        return inner
    if ln == "mtable":
        rows = [[to_latex(c, flags, depth + 1) for c in r if local(c.tag) == "mtd"]
                for r in kids if local(r.tag) in ("mtr", "mlabeledtr")]
        w = max((len(r) for r in rows), default=0)
        if not w:
            flags.append("empty_mtable")
            return "\\square"
        if w == 2 and len(rows) > 1:
            flags.append("mtable_as_cases")
            return "\\begin{cases} %s \\end{cases}" % " \\\\ ".join(
                "%s & %s" % (r[0], r[1] if len(r) > 1 else "") for r in rows)
        flags.append("mtable_as_matrix")
        return "\\begin{matrix} %s \\end{matrix}" % " \\\\ ".join(
            " & ".join(r + [""] * (w - len(r))) for r in rows)
    if ln in ("mtr", "mlabeledtr"):
        return " & ".join(to_latex(k, flags, depth + 1) for k in kids)
    flags.append("unmapped:" + ln)
    return "\\square"

def tidy_latex(s):
    s = re.sub(r"\s+", " ", s or "").strip()
    sp = r"(\\times|\\cdot|\\pm|\\approx|\\le|\\ge|\\neq|\\sim|\\propto|\\to|\\in)"
    s = re.sub(r"(?<=[^\s{])(%s)" % sp, r" \1", s)
    s = re.sub(r"(%s)(?=[^\s}])" % sp, r"\1 ", s)
    s = re.sub(r"\s{2,}", " ", s)
    return s.replace("\\left ", "\\left").replace("\\right ", "\\right").strip()

# ------------------------------------------------------- structure and symbols
def structure_of(el, acc=None):
    
    acc = acc if acc is not None else {"fracs": 0, "subsups": 0, "radicals": 0,
                                       "matrices": 0, "cases": 0}
    ln = local(el.tag)
    if ln == "mfrac":
        acc["fracs"] += 1
    elif ln in ("msub", "msup", "msubsup"):
        acc["subsups"] += 1
    elif ln in ("msqrt", "mroot"):
        acc["radicals"] += 1
    elif ln == "mtable":
        w = max((len([c for c in r if local(c.tag) == "mtd"]) for r in el
                 if local(r.tag) in ("mtr", "mlabeledtr")), default=0)
        acc["cases" if w == 2 else "matrices"] += 1
    for k in el:
        structure_of(k, acc)
    return acc

def extract_symbols(el, out=None):
    
    out = out if out is not None else []

    def add(sym, latex, role):
        for it in out:
            if it["symbol"] == sym:
                it["count"] += 1
                return
        out.append({"symbol": sym, "latex": latex, "role": role, "count": 1})

    def walk(node):
        ln, kids = local(node.tag), list(node)
        if ln in ("msub", "msup", "msubsup") and kids and local(kids[0].tag) == "mi":
            base = n(text_of(kids[0]))
            if ln != "msub" and base in ("e", "10"):
                for k in kids[1:]:
                    walk(k)
                return
            sub = to_latex(kids[1]) if ln in ("msub", "msubsup") and len(kids) > 1 else ""
            sup = (to_latex(kids[1]) if ln == "msup" and len(kids) > 1 else
                   to_latex(kids[2]) if ln == "msubsup" and len(kids) > 2 else "")
            sym = base + ("_{%s}" % sub if sub else "") + ("^{%s}" % sup if sup else "")
            add(sym, mi_latex(kids[0]) + ("_{%s}" % sub if sub else "")
                + ("^{%s}" % sup if sup else ""),
                "operator" if base in FUNCS else "variable")
            return
        if ln == "mi":
            s = n(text_of(node))
            if s:
                add(s, mi_latex(node), "operator" if s in FUNCS else "variable")
            return
        for k in kids:
            walk(k)

    walk(el)
    return out

# ------------------------------------------------------------- numeric checks
ALLOWED = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant, ast.Name, ast.Call,
           ast.Attribute, ast.Load, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow,
           ast.USub, ast.UAdd)
FN = {"sqrt", "exp", "log", "log10", "sin", "cos", "tan", "fabs"}

def _expr(el, vm, depth=0):
    
    if depth > 40:
        return None
    ln, kids = local(el.tag), list(el)
    if ln == "mi":
        return vm.get(n(text_of(el)))
    if ln == "mn":
        try:
            return repr(float(n(text_of(el))))
        except ValueError:
            return None
    if ln == "mo":
        s = n(text_of(el))
        return {"+": "+", "-": "-", "*": "*", "/": "/", "×": "*"}.get(s)
    if ln == "mfrac":
        a, b = (_expr(kids[i], vm, depth + 1) for i in (0, 1))
        return "((%s)/(%s))" % (a, b) if a and b else None
    if ln == "msup":
        if local(kids[0].tag) == "mi" and n(text_of(kids[0])) == "e":
            b = _expr(kids[1], vm, depth + 1)
            return "(math.exp(%s))" % b if b else None
        a, b = _expr(kids[0], vm, depth + 1), _expr(kids[1], vm, depth + 1)
        return "((%s)**(%s))" % (a, b) if a and b else None
    if ln == "msqrt":
        a = _expr(kids[0], vm, depth + 1)
        return "(math.sqrt(%s))" % a if a else None
    if ln in ("math", "mrow", "mstyle", "mpadded", "semantics", "mtd"):
        parts = [_expr(k, vm, depth + 1) for k in kids]
        return "(" + "".join(parts) + ")" if parts and all(p is not None for p in parts) else None
    return None

def evaluate(node, values):
    """(value|None, expression|None, reason). values: {'x': 3.2, 'x_1': 3.2}."""
    keys = sorted(values)
    vm = {k: "v%d" % i for i, k in enumerate(keys)}
    env = {"v%d" % i: float(values[k]) for i, k in enumerate(keys)}
    expr = _expr(node, vm)
    if not expr or len(expr) > 4000:
        return None, expr, "expression_not_supported"
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError:
        return None, expr, "expr_parse_failed"
    for nd in ast.walk(tree):
        if not isinstance(nd, ALLOWED):
            return None, expr, "expr_unsupported_node"
        if isinstance(nd, ast.Attribute) and nd.attr not in FN:
            return None, expr, "expr_unsupported_attr"
        if isinstance(nd, ast.Name) and nd.id not in env and nd.id != "math":
            return None, expr, "expr_unknown_name"
    try:
        val = eval(compile(tree, "<formula>", "eval"), {"__builtins__": {}}, dict(env, math=math))
    except Exception as exc:  # noqa: BLE001 - degraded numeric path
        return None, expr, "eval_error:" + type(exc).__name__
    return val, expr, "ok"

# ----------------------------------------------------------------- text mining
def mine_defs(blocks):
    
    D, V = {}, {}
    for b in blocks:
        t, loc, sid = b["text"], b["path"], b["source_id"]
        for m in re.finditer(DEF_WHERE, t, re.I):
            u0 = re.search(UNIT_IN, m.group(2))
            D.setdefault(m.group(1), {"definition": n(re.split(r",\s*and\s|;\s", m.group(2))[0])[:220],
                                      "unit": n(u0.group(1)) if u0 else "", "quote": t[:400],
                                      "locator": loc, "source_id": sid})
        for m in re.finditer(DEF_AND, t, re.I):
            u = re.search(UNIT_IN, m.group(2))
            D.setdefault(m.group(1), {"definition": n(re.split(r",\s*and\s|;\s", m.group(2))[0])[:220],
                                      "unit": n(u.group(1)) if u else "", "quote": t[:400],
                                      "locator": loc, "source_id": sid})
        for m in re.finditer(VAL_ASSIGN, t):
            try:
                V.setdefault(m.group(1), {"value": float(m.group(2)), "unit": n(m.group(3)),
                                          "quote": t[:300], "locator": loc, "source_id": sid})
            except ValueError:
                continue
    return D, V

def mine_steps(blocks):
    
    steps, seen, rows = [], set(), []
    for b in blocks:
        for s in re.split(r"(?<=[.!?])\s+(?=[A-Z])|(?<=[!?])\s+", b["text"]):
            s = n(s)
            low = s.lower()
            if len(s) >= 25 and s not in seen:
                rules = [k for k, r in CUES if re.search(r, low)]
                if rules:
                    seen.add(s)
                    steps.append({"step_id": "D%d" % (len(steps) + 1), "from": None,
                                  "to": None, "rule": rules[0], "statement": s[:300],
                                  "assumptions": [s[:200]] if re.search(r"assum|suppos", low) else [],
                                  "approximations": [s[:200]] if re.search(
                                      r"approximat|negligib|lineariz", low) else [],
                                  "boundary_conditions": [s[:200]] if re.search(
                                      r"\bif\b|\bfor\b|in the limit|\bwhen\b", low) else [],
                                  "depends_on": [], "quote": s[:300], "locator": b["path"],
                                  "source_id": b["source_id"], "verified": False,
                                  "status": "textual_only"})
        for m in re.finditer(r"(?<![\w.])([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)\s*"
                             r"([A-Za-z%\u00b0\u00b5][A-Za-z%\u00b0\u00b5/\u00b7^0-9\-]{0,11})\b",
                             b["text"]):
            if m.group(2).lower() not in ("and", "or", "the", "of", "to", "in", "is"):
                rows.append({"value": m.group(1), "unit": m.group(2), "quote": b["text"][:240],
                             "locator": b["path"], "source_id": b["source_id"],
                             "checked": "reported_as_written"})
    return steps[:24], rows[:40]

def lcheck(s):
    
    d, bad, i = 0, False, 0
    while i < len(s):
        if s[i] == "\\":
            i += 2
            continue
        d += {"{": 1, "}": -1}.get(s[i], 0)
        bad = bad or d < 0
        i += 1
    return [k for k, c in (("empty_latex", not s), ("unbalanced_braces", bad or d),
                           ("placeholder_square", "\\square" in s)) if c]

# ------------------------------------------------------------ result envelope
PENDING = {"status": "pending", "detail": "filled during the finalise stage of the same run"}


def compose(st):
    
    r = {"case_id": st["case_id"], "status": st["status"], "result": st["result"]}
    for k in ("claims", "uncertainties", "sources", "pending_human", "errors",
              "degradations", "changes", "runtime"):
        r[k] = st[k]
    r["uncertainty"] = st["uncertainties"]   # alias expected by the task spec
    r["golden_standard"] = st.get("golden") or dict(PENDING)
    r["diff_report"] = st.get("diff") or dict(PENDING)
    r["version_history"] = st.get("vhistory") or dict(PENDING)
    r["self_check"] = st.get("selfcheck") or dict(PENDING)
    con = st["contract"] if isinstance(st["contract"], dict) else {}
    vals = st.get("contract_values") or {}
    for k, v in con.items():
        if k not in r:
            if k in vals:
                r[k] = vals[k]              # semantic fill (evidence/notes/...) instead of null
            elif k in st["result"]:
                r[k] = st["result"][k]
            else:
                r[k] = type(v)() if isinstance(v, (list, dict)) else None
    r["output_contract_echo"] = {
        k: ("result." + k if k in st["result"] else
            ("semantic_fill" if k in vals else ("contract_default" if k in r else None)))
        for k in con}
    r["contract_fields_missing"] = [k for k in con if k not in r]
    return r
