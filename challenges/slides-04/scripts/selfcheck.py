#!/usr/bin/env python3
"""One-command self-check for the slide-template adapter.

Builds a throwaway case (paper + a synthetic-but-real 16:9 template), runs main.py through the
same CLI the harness uses, and asserts the v1 contract plus the six v2 assets. Also exercises the
empty-input and broken-input paths. Exit 0 = all assertions passed.

    python3 -B scripts/selfcheck.py
"""
import json, subprocess, sys, tempfile, zipfile
from pathlib import Path

sys.dont_write_bytecode = True

H = Path(__file__).resolve().parent
HERE = H.parent
PAPER = """# Self-check paper

## Abstract

A short study used by the self-check. The measured gain was 6.8 C and the sample size was n = 24.
The method logged 380 points over 24 months and reported one limitation.

## Methods

We measured 12 treated surfaces and 12 controls with calibrated sensors every 60 s. Uncertainty
was estimated at plus or minus 8 units, which is reported in Figure 1 for both groups.

## Results

Treated surfaces stayed 6.8 C cooler than controls. Peak power reached 92 W/m2 at 34 C ambient.

## Limitations

The sample covers one climate zone, so transfer to other regions is not demonstrated.
"""
FILES = ["presentation.pptx", "result.json", "template_spec.json", "format_compliance.json",
         "page_diff.md", "version_history.md", "run.log", "export_check.json"]


def call(args):
    return subprocess.run([sys.executable, "-B", str(H / "main.py")] + args,
                          capture_output=True, text=True)


def build_case(root):
    root.mkdir(parents=True, exist_ok=True)
    (root / "paper.md").write_text(PAPER, "utf-8")
    (root / "case.json").write_text(json.dumps({
        "case_id": "selfcheck-000", "organizer_workorder": {"total_slide_count": 8, "min_font_pt": 12,
                                                            "footer_text": "Self-check", "page_number_required": True},
        "output_contract": {"case_id": None, "status": None, "editable_source": None, "export_artifact": None,
                            "content_map": None, "compliance_checks": None, "template_spec": None,
                            "format_compliance": None, "page_diff": None, "version_history": None,
                            "run_log": None, "export_check": None, "rollback": None}}, indent=2), "utf-8")
    import importlib.util
    s = importlib.util.spec_from_file_location("_sp", H / "spec.py")
    SP = importlib.util.module_from_spec(s)
    s.loader.exec_module(SP)
    SP.write_parts(SP.synthetic_parts(), root / "template.pptx")


def main():
    ok = True

    def check(name, cond, detail=""):
        nonlocal ok
        ok = ok and bool(cond)
        print(("PASS  " if cond else "FAIL  ") + name + (("  " + str(detail)[:160]) if detail else ""))

    r = call(["--help"])
    check("--help exit 0", r.returncode == 0, "rc=%d" % r.returncode)
    check("--help mentions original options", all(x in r.stdout for x in ("--input", "--output", "--template", "--slides")))

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        case, out = td / "input", td / "output"
        build_case(case)
        r = call(["--input", str(case), "--output", str(out), "--template", str(case / "template.pptx"), "--slides", "8"])
        check("run exit 0", r.returncode == 0, r.stderr[-160:])
        for f in FILES:
            check("artifact " + f, (out / f).exists(), (out / f).stat().st_size if (out / f).exists() else "missing")
        res = json.loads((out / "result.json").read_text("utf-8"))
        check("result.json parses", isinstance(res, dict))
        check("contract fields echoed", all(k in res for k in ("case_id", "status", "editable_source", "export_artifact",
                                                               "content_map", "compliance_checks", "template_spec",
                                                               "format_compliance", "page_diff", "version_history",
                                                               "run_log", "export_check", "rollback")))
        check("status ok", res.get("status") == "ok", res.get("status"))
        z = zipfile.ZipFile(str(out / "presentation.pptx"))
        names = z.namelist()
        check("pptx is a valid zip", z.testzip() is None, "%d parts" % len(names))
        check("theme part kept", "ppt/theme/theme1.xml" in names)
        check("master part kept", any(n.startswith("ppt/slideMasters/") for n in names))
        check("slides present", len([n for n in names if n.startswith("ppt/slides/slide")]) >= 8)
        sp = json.loads((out / "template_spec.json").read_text("utf-8"))
        check("template_spec has layout_map", len(sp.get("layout_map") or []) >= 8)
        check("template_spec protected_parts", len(sp.get("protected_parts") or {}) >= 3)
        fc = json.loads((out / "format_compliance.json").read_text("utf-8"))
        check("format_compliance items 16", fc.get("total") == 16 and len(fc.get("items") or []) == 16)
        check("every item carries evidence", all(i.get("evidence") and i.get("actual") for i in fc["items"]))
        check("evidence snippets verified", all(ev.get("verified_in_part") is not False
                                                for i in fc["items"] for ev in i["evidence"]),
              [i["id"] for i in fc["items"] for ev in i["evidence"] if ev.get("verified_in_part") is False])
        pd = (out / "page_diff.md").read_text("utf-8")
        check("page_diff has per-page rows", pd.count("| 1 |") >= 1 and "未解决偏差" in pd)
        check("version_history has rollback", "回退路径" in (out / "version_history.md").read_text("utf-8"))
        check("run.log has stage lines", (out / "run.log").read_text("utf-8").count("INFO") >= 5)
        pdf = out / "presentation.pdf"
        check("pdf header %PDF-", pdf.exists() and pdf.read_bytes()[:5] == b"%PDF-", "no soffice" if not pdf.exists() else "")
        if pdf.exists():
            ex = json.loads((out / "export_check.json").read_text("utf-8"))
            check("export_check pages match", ex["rules"]["pdf_pages_eq_slides"], ex["consistency"])

        # empty input
        e_in, e_out = td / "empty_in", td / "empty_out"
        e_in.mkdir()
        r = call(["--input", str(e_in), "--output", str(e_out)])
        check("empty input exit 0", r.returncode == 0)
        check("empty input writes result.json", (e_out / "result.json").exists())
        check("empty input still emits a minimal pptx", (e_out / "presentation.pptx").exists())
        if (e_out / "result.json").exists():
            check("empty input result parses", isinstance(json.loads((e_out / "result.json").read_text("utf-8")), dict))

        # broken case.json + broken template
        b_in, b_out = td / "bad_in", td / "bad_out"
        b_in.mkdir()
        (b_in / "case.json").write_text('{"case_id": "bad", "output_contract": {', "utf-8")
        (b_in / "template.pptx").write_bytes(b"not a zip")
        (b_in / "paper.md").write_text(PAPER, "utf-8")
        r = call(["--input", str(b_in), "--output", str(b_out)])
        check("broken input exit 0", r.returncode == 0)
        check("broken input writes result.json", (b_out / "result.json").exists())
        check("broken input still emits a minimal pptx", (b_out / "presentation.pptx").exists())
        if (b_out / "result.json").exists():
            rb = json.loads((b_out / "result.json").read_text("utf-8"))
            check("broken input status partial", rb.get("status") in ("partial", "input_error"), rb.get("status"))
    print("\nSELF-CHECK %s" % ("PASSED" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
