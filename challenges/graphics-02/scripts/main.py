#!/usr/bin/env python3
"""source-value-chart: source table -> data-to-mark model -> editable layered SVG + PDF/PNG ->
result.json with a per-mark locator map and compliance checks. Stdlib only, CWD independent."""
import argparse, hashlib, json, math, os, re, sys, time, traceback
from pathlib import Path
from xml.sax.saxutils import escape
sys.path.insert(0, str(Path(__file__).resolve().parent))
import toolkit as T

FONTS = "Helvetica, Arial, 'Noto Sans CJK SC', 'DejaVu Sans', sans-serif"
S = {}
EMPTY = {"chart": None, "series": [], "axes": [], "legend": [], "coverage": {"required": 0, "mapped": 0, "missing": []}}

def ex(c, d, sev="warn", act=""):
    S["exceptions"].append({"code": c, "detail": d, "severity": sev, "action": act})

def wjson(p, o):
    t = Path(str(p) + ".tmp")
    t.write_text(json.dumps(o, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(t, p)

def cr(i):
    s, i = "", i + 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s

def build(B, sp, tb):
    hs, chart = tb["headers"], T.kind(sp, B)
    cats = []
    for s in B["ser"]:
        cats += [p["x"] for p in s["p"] if p["x"] not in cats]
    if chart != "bar" and not B["xc"]:
        xs = []
        for s in B["ser"]:
            for p in s["p"]:
                p["xn"] = T.parse_number(p["x"])[0]
                xs += [p["xn"]] if p["xn"] is not None else []
        cats = sorted(set(xs)) or cats
    ys = [p["v"] for s in B["ser"] for p in s["p"]]
    if not ys:
        raise ValueError("no numeric values in " + tb["file"])
    log = sp["ysc"].startswith("log") and any(v > 0 for v in ys)
    if sp["ysc"].startswith("log") and not log:
        ex("log_axis_no_positive", "log scale requested, no positive value", "warn", "linear used")
    if log:
        lo, hi, tk = T.log_ticks(min(v for v in ys if v > 0), max(ys))
    else:
        v0, v1 = min(ys), max(ys)
        lo, hi, tk = T.nice_ticks(0. if (chart == "bar" and v0 >= 0) else min(v0, 0.), max(v1, 0.))
    if isinstance(sp["ylim"], (list, tuple)) and len(sp["ylim"]) == 2:
        lo, hi = float(sp["ylim"][0]), float(sp["ylim"][1])
    hi = hi if hi > lo else lo + 1.
    tk = [t for t in tk if lo - 1e-9 <= t <= hi + 1e-9] or [lo, hi]
    ser, leg = [], []
    for si, s in enumerate(B["ser"]):
        ps, sid = [], f"s{si + 1}"
        for pi, p in enumerate(s["p"]):
            r = p["row"]
            q = {"id": f"{sid}-p{pi + 1}", "x": p["x"], "yr": p["r"], "y": p["v"], "cat": B["xc"],
                 "src": {"file": tb["file"], "sheet": tb["sheet"], "row": r["row"], "col": cr(p["c"]),
                         "col_index": p["c"], "header": hs[p["c"]], "x_header": hs[B["xi"]],
                         "x_col": cr(B["xi"]), "quote": r["line"]}}
            if p.get("xn") is not None:
                q["xn"] = p["xn"]
            if s["c"] in B["errs"]:
                ec, er = B["errs"][s["c"]], r["cells"][B["errs"][s["c"]]]
                ev, ek = T.parse_number(er)
                q.update(eraw=er, err=ev, emode=sp["em"] or "as reported in the source",
                         esrc={"file": tb["file"], "sheet": tb["sheet"], "row": r["row"], "col": cr(ec),
                               "header": hs[ec], "quote": r["line"]})
                if ek != "ok":
                    ex("error_value_unparsable", f"row {r['row']} err={er!r}", "info", "bar omitted")
            ps.append(q)
        ser.append({"id": sid, "name": s["n"], "unit": s["u"] or "", "column": hs[s["c"]],
                    "color": T.PAL[si % 8], "marker": T.MARK[si % 8], "points": ps})
        leg.append({"id": "legend-" + sid, "series_id": sid, "label": s["n"], "color": T.PAL[si % 8]})
    yu = sp["yu"] or ser[0]["unit"]
    if not yu:
        ex("unit_unknown", "y unit absent from header and workorder", "warn",
           "axis says 'unit not reported', no unit invented")
    return {"chart_type": chart, "title": sp["ti"] or "",
            "axes": {"x": {"label": B["xl"], "unit": B["xu"] or "",
                           "scale": "category" if B["xc"] else "linear", "categories": cats,
                           "source": {"header": hs[B["xi"]], "col": cr(B["xi"])}},
                     "y": {"label": sp["yl"] or ser[0]["column"], "unit": yu, "scale": "log" if log else "linear",
                           "min": lo, "max": hi, "ticks": tk,
                           "source": {"header": ser[0]["column"], "note": "from header/workorder"}}},
            "series": ser, "legend": leg,
            "source_table": {"file": tb["file"], "sheet": tb["sheet"], "header_row": tb["header_row"],
                             "data_rows": len(tb["rows"]), "headers": hs}}

def render(m, sty, W, H):
    s, ya = T.style_for(sty), m["axes"]["y"]
    log, lo, hi, cats = ya["scale"] == "log", ya["min"], ya["max"], m["axes"]["x"]["categories"]
    x0, y0 = max(48., s["f"] * 5.2), 26 + (14 if m["title"] else 0) + (16 if m["legend"] else 0)
    x1, y1 = W - 18, H - max(40., s["f"] * 3.4)
    L = {k: [] for k in ("background", "title", "axes", "data", "error", "legend", "labels")}
    L["background"].append(f'<rect id="canvas-bg" x="0" y="0" width="{W:g}" height="{H:g}" fill="#ffffff"/>')
    if m["title"]:
        L["title"].append(T.tx("figure-title", W / 2, 18, s["ti"], m["title"], e=' font-weight="bold"'))
    yl = ya["label"] or ""
    yl = f"{yl} ({ya['unit']})" if ya["unit"] else yl + " (unit not reported)"
    xl, xu = m["axes"]["x"]["label"] or "", m["axes"]["x"]["unit"]
    xl = (f"{xl} ({xu})" if xl else xu) if (xu and xu not in xl) else xl
    L["axes"] += [T.ln("axis-y", x0, y0, x0, y1, "#111111", s["axl"]), T.ln("axis-x", x0, y1, x1, y1, "#111111", s["axl"])]
    for ti, tv in enumerate(ya["ticks"]):
        yy = T.ymap(tv, lo, hi, y0, y1, log)
        if yy is None or not (y0 - .5 <= yy <= y1 + .5):
            continue
        L["axes"] += [T.ln(f"ytick-{ti}", x0 - 3, yy, x0, yy, "#111111", s["axl"]),
                      T.tx(f"yticklabel-{ti}", x0 - 5, yy + s["s"] * .35, s["s"], T.fmt_num(tv), "end")]
    band = (x1 - x0) / max(1, len(cats))
    rot = any(T.text_width(c, s["s"]) > 46 for c in cats)
    for ci, ct in enumerate(cats):
        cx = x0 + (ci + .5) * band
        L["axes"].append(T.tx(f"xtick-{ci}", cx + (2 if rot else 0), y1 + (6 if rot else 12), s["s"], ct,
                            "end" if rot else "middle",
                            f' transform="rotate(-35 {cx + 2:.2f} {y1 + 6:.2f})"' if rot else ""))
    yx = max(12., x0 - 34)
    L["labels"] += [T.tx("label-yaxis", yx, (y0 + y1) / 2, s["f"], yl,
                       e=f' transform="rotate(-90 {yx:.2f} {(y0 + y1) / 2:.2f})"'),
                    T.tx("label-xaxis", (x0 + x1) / 2, y1 + (34 if rot else 26), s["f"], xl)]
    bv = max(lo, 0.) if lo <= 0 <= hi else lo
    base = T.ymap(bv, lo, hi, y0, y1, log)
    base = y1 if base is None else base
    slot = (band * (1 - s["bg"])) / max(1, len(m["series"]))
    for si, sr in enumerate(m["series"]):
        for p in sr["points"]:
            ci = cats.index(p["x"]) if p["x"] in cats else 0
            yy = T.ymap(p["y"], lo, hi, y0, y1, log)
            if yy is None:
                ex("value_off_log_axis", f"point {p['id']} value={p['yr']!r} off log axis", "info", "skipped")
                continue
            g = {"id": p["id"], "kind": m["chart_type"], "y_px": round(yy, 2), "pt": y0, "pb": y1}
            if m["chart_type"] == "bar":
                bx = x0 + ci * band + s["bg"] * band / 2 + si * slot + slot * s["gg"] / 2
                bw, t = max(1., slot * (1 - s["gg"])), min(yy, base)
                L["data"].append(f'<rect id="bar-{p["id"]}" class="mark" x="{bx:.2f}" y="{t:.2f}" width="{bw:.2f}" '
                                 f'height="{abs(base - yy):.2f}" fill="{sr["color"]}"/>')
                g.update(x_px=round(bx, 2), w_px=round(bw, 2), top=round(t, 2), h=round(abs(base - yy), 2),
                         base=round(base, 2), bv=bv)
            else:
                cx = x0 + (ci + .5) * band
                if p.get("xn") is not None and len(cats) > 1 and isinstance(cats[0], (int, float)):
                    cx = x0 + (p["xn"] - cats[0]) / ((cats[-1] - cats[0]) or 1) * (x1 - x0)
                L["data"].append(f'<circle id="pt-{p["id"]}" class="mark" cx="{cx:.2f}" cy="{yy:.2f}" '
                                 f'r="{max(1.6, s["f"] * .24):g}" fill="{sr["color"]}" stroke="#ffffff" stroke-width="0.5"/>')
                g.update(x_px=round(cx, 2))
            if p.get("err") is not None:
                e = abs(p["err"])
                yt, yb = T.ymap(p["y"] + e, lo, hi, y0, y1, log), T.ymap(p["y"] - e, lo, hi, y0, y1, log)
                if yt is None or yb is None:
                    ex("error_bar_off_axis", f"error range of {p['id']} off axis", "info", "skipped")
                else:
                    yt, yb = max(y0, min(y1, yt)), max(y0, min(y1, yb))
                    xc = g.get("x_px", 0) + (g.get("w_px", 0) / 2 if g["kind"] == "bar" else 0)
                    L["error"] += [T.ln("err-" + p["id"], xc, yt, xc, yb, "#111111", s["axl"]),
                                   T.ln("errc-" + p["id"], xc - 3, yt, xc + 3, yb, "#111111", s["axl"])]
                    g.update(et=round(yt, 2), eb=round(yb, 2))
            p["g"] = g
    lx, ly = 16., 29.
    for it in m["legend"]:
        w = 16 + T.text_width(it["label"], s["s"])
        if lx + w > W - 16:
            lx, ly = 16., ly + 14
        sw = (f'<rect id="{it["id"]}-swatch" x="{lx:.2f}" y="{ly - 8:.2f}" width="9" height="8" fill="{it["color"]}"/>'
              if m["chart_type"] == "bar" else
              f'<circle id="{it["id"]}-swatch" cx="{lx + 4:.2f}" cy="{ly - 4:.2f}" r="3.4" fill="{it["color"]}"/>')
        L["legend"].append(sw + T.tx(it["id"] + "-text", lx + 13, ly - 1, s["s"], it["label"], "start"))
        it["xy"] = [round(lx, 1), round(ly, 1)]
        lx += w + 14
    body = "\n".join(f' <g id="layer-{k}">\n  ' + "\n  ".join(L[k]) + "\n </g>"
                     for k in ("background", "title", "axes", "data", "error", "legend", "labels") if L[k])
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n<svg xmlns="http://www.w3.org/2000/svg" version="1.1" '
            f'width="{m["canvas"]["w_mm"]:.2f}mm" height="{m["canvas"]["h_mm"]:.2f}mm" viewBox="0 0 {W:g} {H:g}" '
            f'font-family="{FONTS}">\n <title>{escape(m["title"] or "scientific data chart")}</title>\n'
            f' <desc>Editable chart from {escape(m["source_table"]["file"])}; text stays live, mark ids map to '
            f'content_map.</desc>\n{body}\n</svg>\n')

def run(a):
    t0 = time.time()
    inp, out = Path(a.input).resolve(), Path(a.output).resolve()
    out.mkdir(parents=True, exist_ok=True)
    S.update(out=str(out), case_id="unknown", status="partial", contract={}, sources=[], errors=[],
             degradations=[], exceptions=[], pending_human=[], changes=[], uncertainty=[], instruction="",
             log=[], runtime={"python": sys.version.split()[0], "budget": "900 s / 64 requests"})
    T.fin(S, out)
    if not inp.is_dir():
        S.update(status="input_error", errors=["input_dir_missing"])
        S["pending_human"].append("place case.json and the source table under /input")
        return T.fin(S, out)
    d = T.disc(inp)
    case = d["case"] if isinstance(d["case"], dict) else {}
    S["case_id"] = case.get("case_id") or case.get("id") or "unknown"
    S["contract"] = case.get("output_contract") or {}
    S["instruction"] = str(case.get("task_instruction") or case.get("instruction") or "")
    S["sources"] = [{"kind": "case_json", "path": d["cp"]},
                    {"kind": "task_md", "path": str(inp / "task.md") if (inp / "task.md").exists() else None}]

    for e in d["cerr"]:
        S["errors"].append(e)
        S["degradations"].append("case.json unreadable; continued from the directory scan")
    sp = T.spec(d["wo"])
    sp["st"] = a.style or sp["st"]
    if d["wo"]:
        S["changes"].append({"step": "workorder_in", "detail": f"keys: {sorted(d['wo'])[:10]}"})
    tabs = []
    for p in d["tables"]:
        try:
            for t in T.read_table(p):
                t["path"] = str(p)
                tabs.append(t)
        except Exception as e:
            S["errors"].append(f"table_read_failed:{p.name}:{str(e)[:60]}")
    S["sources"] += [{"kind": "data_table", "path": t["path"], "file": t["file"], "sheet": t["sheet"],
                      "rows": len(t["rows"])} for t in tabs]
    if not tabs:
        S["errors"].append("no_parsable_data_table")
        S.update(status="insufficient_evidence", content_map=EMPTY,
                 compliance_checks={"pass": False, "failures": ["no_source_table"]}, export_artifact={})
        S["pending_human"].append("provide the source table (CSV/TSV/XLSX)")
        return T.fin(S, out)
    tb = None
    if sp["tb"]:
        b = str(sp["tb"]).lower()
        tb = next((t for t in tabs if t["file"].lower() in b or b in t["file"].lower()), None)
    tb = tb or max(tabs, key=lambda t: 2 * sum(T.parse_number(c)[1] == "ok" for r in t["rows"] for c in r["cells"])
                   + len(t["rows"]))
    try:
        B = T.cols(tb, sp)
        if not B["ser"]:
            raise ValueError("no numeric series resolved")
        m = build(B, sp, tb)
    except Exception as e:
        S["errors"].append(f"model_build_failed:{str(e)[:130]}")
        S.update(status="insufficient_evidence", content_map=EMPTY,
                 export_artifact={}, compliance_checks={"pass": False, "failures": ["model_build_failed"]})
        S["pending_human"].append("column binding unresolved: check workorder fields vs headers")
        return T.fin(S, out)
    for c, d_, act in B["issues"]:
        ex(c, d_, "warn", act)
    for w in sp.get("warn", []):
        ex("chart_type_unsupported", w, "warn", "bars drawn instead")
    W = round(sp["wm"] * 96 / 25.4, 2)
    hm = sp["hm"] or round(sp["wm"] * .62, 1)
    H = round(float(hm) * 96 / 25.4, 2)
    m["canvas"] = {"w_px": W, "h_px": H, "w_mm": round(sp["wm"], 2), "h_mm": round(float(hm), 2), "dpi": sp["dpi"]}
    svg = render(m, sp["st"] or "journal", W, H)
    (out / "chart.svg").write_bytes(svg.encode("utf-8"))
    wjson(out / "chart_model.json", m)
    pe = T.export_pdf(str(out / "chart.svg"), str(out / "chart.pdf"), S["log"])
    if pe is None:
        S["degradations"].append("pdf: no renderer available (rsvg/soffice failed)")
    pi = T.inspect_pdf(out / "chart.pdf")
    ne = T.pdf_png(str(out / "chart.pdf"), str(out / "chart.png"), sp["dpi"], S["log"]) \
        if pi.get("header_ok") else None
    if ne is None:
        S["errors"].append("png_export_failed:no rasteriser produced chart.png")
    qi = T.inspect_png(out / "chart.png")
    try:
        cm, gc, lc = T.cmap(m), T.gcheck(m), T.lcheck(m)
    except Exception as e:
        ex("check_failed", str(e)[:80], "warn", "geometry kept in chart_model.json")
        cm, gc, lc = {"series": [], "axes": [], "legend": [], "coverage": {"required": 0, "mapped": 0,
                      "missing": []}}, {"ok": False, "checked": 0}, {"ok": False}
    fails = [n for b, n in ((not lc["ok"], "legend_series_mismatch"), (not gc["ok"], "geometry_mismatch"),
                            (cm["coverage"]["mapped"] != cm["coverage"]["required"], "coverage_incomplete"),
                            (qi.get("ink_present") is False, "png_blank"), (not pi.get("header_ok"), "pdf_missing"))
             if b]
    wide = [c for c in m["axes"]["x"]["categories"] if T.text_width(c, 6.5) > 90]
    layers = re.findall(r'<g id="(layer-[^"]+)"', svg)
    checks = {"canvas": {"width_mm": m["canvas"]["w_mm"], "height_mm": m["canvas"]["h_mm"],
                         "width_px": W, "height_px": H, "dpi": sp["dpi"]},
              "fonts": {"family": FONTS, "cjk_in_figure": T.has_cjk(svg), "text_elements": svg.count("<text"),
                        "text_kept_as_text": True},
              "line_widths": {k: T.style_for(sp["st"] or "journal")[k] for k in ("lw", "axl", "gl")},
              "colors": {"palette": [x["color"] for x in m["series"]], "distinct": lc["distinct_colors"]},
              "legend_consistency": lc, "geometry_roundtrip": gc, "content_coverage": cm["coverage"],
              "canvas_overflow": {"x_labels_rotated": bool(wide), "layers": layers},
              "png": qi, "pdf": pi, "pass": not fails, "failures": fails}
    S.update(content_map=cm, compliance_checks=checks)
    S["editable_source"] = {"path": "chart.svg", "format": "svg", "editable": True, "layers": layers,
                            "text_count": svg.count("<text"), "element_count": len(re.findall(r'id="', svg)),
                            "sha256": hashlib.sha256(svg.encode()).hexdigest(),
                            "bytes": (out / "chart.svg").stat().st_size, "viewBox": f"0 0 {W:g} {H:g}",
                            "text_selectable": True, "model": "chart_model.json"}
    S["editable_source"]["layer_count"] = len(layers)
    S["export_artifact"] = {"svg": "chart.svg",
                            "pdf": {"path": "chart.pdf", "engine": pe, "pages": pi.get("pages"),
                                    "vector": bool(pi.get("header_ok")), "mediabox_pt": pi.get("mediabox_pt"),
                                    "bytes": pi.get("bytes")},
                            "png": {"path": "chart.png", "engine": ne, "width": qi.get("width"),
                                    "height": qi.get("height"), "dpi": sp["dpi"], "color_type": qi.get("color_type"),
                                    "mean_level": qi.get("mean_level"), "bytes": qi.get("bytes")}}
    S["pending_human"] += [f"{e['code']}: {e['detail']}" for e in S["exceptions"]
                          if e["code"] in ("unit_unknown", "error_column_missing", "column_not_found")]
    S["uncertainty"] = [{"item": "chart_type", "note": "from workorder" if sp["t"] else "inferred from table shape"},
                        {"item": "units/statistics", "note": "units copied from source, statistics transmitted not computed"}]
    S["changes"] += [{"step": "bind", "detail": f"x={tb['headers'][B['xi']]} y={[x['column'] for x in m['series']]}"},
                     {"step": "render_export", "detail": f"{W:.1f}x{H:.1f}px {sp['st'] or 'journal'} pdf={pe} png={ne}"}]
    S["status"] = "ok" if (checks["pass"] and not S["degradations"] and not S["errors"]) else "partial"
    S["runtime"]["elapsed_s"] = round(time.time() - t0, 2)
    return T.fin(S, out)

def parse_args(argv):
    ap = argparse.ArgumentParser(prog="source-value-chart",
                                 description="Editable source-bound data chart: table -> chart_model.json -> "
                                             "layered SVG + PDF/PNG -> result.json.")
    ap.add_argument("--input", help="input dir (default /input, else ./input)")
    ap.add_argument("--output", help="output dir (default /app/output, else ./output)")
    ap.add_argument("--style", help="journal|nature|thesis|presentation|default")
    ap.add_argument("--version", action="store_true", help="print version")
    a = ap.parse_args(argv)
    a.input = a.input or ("/input" if Path("/input").is_dir() else str(Path.cwd() / "input"))
    a.output = a.output or ("/app/output" if Path("/app").is_dir() else str(Path.cwd() / "output"))
    return a

def main(argv=None):
    a = parse_args(sys.argv[1:] if argv is None else argv)
    if a.version:
        print("source-value-chart 1.0.0 (stdlib only)")
        return 0
    try:
        return run(a)
    except Exception:  # never leave without a legal result.json
        out = Path(a.output)
        out.mkdir(parents=True, exist_ok=True)
        rp = out / "result.json"
        try:
            cur = json.loads(rp.read_text(encoding="utf-8"))
        except Exception:
            cur = {"case_id": "unknown"}
        cur["status"] = "partial"
        cur.setdefault("errors", []).append("unhandled:" + traceback.format_exc()[-300:])
        for k in ("exceptions", "pending_human", "degradations", "sources", "uncertainty", "changes"):
            cur.setdefault(k, [])
        for k in ("editable_source", "export_artifact", "content_map", "compliance_checks"):
            cur.setdefault(k, None)
        cur["pending_human"].append("pipeline crashed; inspect errors")
        try:
            wjson(rp, cur)
        except Exception:
            pass
        return 0

if __name__ == "__main__":
    sys.exit(main())
