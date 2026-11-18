"""discover.py: input discovery, output-directory resolution, contract echo.

No assumption about key names: case.json is read wherever it is, the workorder is found
by content, and every key of the input `output_contract` is echoed back under its own
spelling through an alias table.
"""
import json
import os
import re
import time
from pathlib import Path

ALIASES = {'case_id': ('case_id', 'id'), 'status': ('status', 'state'),
           'editable_source': ('editable_source', 'deck', 'presentation', 'pptx'),
           'export_artifact': ('export_artifact', 'export', 'pdf', 'render'),
           'content_map': ('content_map', 'slide_map', 'page_map', 'evidence_map'),
           'compliance_checks': ('compliance_checks', 'compliance', 'checks'),
           'exceptions': ('exceptions', 'exception', 'issues'),
           'page_golden': ('page_golden', 'pagegolden', 'golden', 'goldstandard'),
           'page_diff': ('page_diff', 'pagediff', 'diff', 'pagediffcheck'),
           'version_history': ('version_history', 'versionhistory', 'versions', 'changelog'),
           'export_check': ('export_check', 'exportcheck', 'rendercheck', 'exportrendercheck'),
           'template_check': ('template_check', 'templatecheck', 'templateinheritancecheck')}
AN = {c: [re.sub(r'[^a-z]', '', a) for a in (c,) + al] for c, al in ALIASES.items()}


def now():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def wjson(p, o):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(o, ensure_ascii=False, indent=1), encoding='utf-8')


def clip(s, n):
    s = re.sub(r'\s+', ' ', str(s or '')).strip()
    return s if len(s) <= n else s[:n - 1].rstrip() + '…'


def load_json(p):
    try:
        return json.loads(Path(p).read_text(encoding='utf-8', errors='replace'))
    except Exception:
        return None


def find_case(indir):
    """case.json, else any case*.json; a list is read through its first dict."""
    for p in [indir / 'case.json'] + sorted(indir.glob('case*.json')):
        d = load_json(p)
        if isinstance(d, dict):
            return d
        if isinstance(d, list) and d and isinstance(d[0], dict):
            return d[0]
    return {}


def fk(o, keys, d=0):
    """Fuzzy key lookup: exact normalised key, then substring, then depth-first."""
    if d > 6 or o is None:
        return None
    if isinstance(o, dict):
        low = {re.sub(r'[^a-z0-9]', '', str(k).lower()): v for k, v in o.items()}
        for k in keys:
            if k in low and not isinstance(low[k], (dict, list)):
                return low[k]
            for k2, v in low.items():
                if k in k2 and not isinstance(v, (dict, list)):
                    return v
        for v in o.values():
            r = fk(v, keys, d + 1)
            if r is not None:
                return r
    elif isinstance(o, list):
        for v in o[:30]:
            r = fk(v, keys, d + 1)
            if r is not None:
                return r
    return None


def num(*vals):
    for v in vals:
        if isinstance(v, bool) or v is None:
            continue
        if isinstance(v, int):
            return v
        m = re.search(r'\b(\d{1,3})\b', str(v))
        if m:
            return int(m.group(1))


def scan(indir):
    """Classify every input file by extension and magic bytes, never by label."""
    out = {k: [] for k in ('pdf', 'pptx', 'json', 'doc', 'image')}
    ext = {'.pptx': 'pptx', '.docx': 'doc', '.json': 'json', '.md': 'doc', '.txt': 'doc',
           '.png': 'image', '.jpg': 'image', '.svg': 'image'}
    for p in sorted(indir.rglob('*')) if indir.exists() else []:
        try:
            head = p.open('rb').read(4) if p.is_file() and p.stat().st_size else b''
        except Exception:
            continue
        if head:
            out[ext.get(p.suffix.lower()) or ('pdf' if head[:4] == b'%PDF' else 'doc')].append(p)
    return out


def by_name(files, keys):
    return next((p for p in files if any(k in p.name.lower() for k in keys)), None)


def pick_workorder(js, indir):
    for n in ('slide-workorder.json', 'workorder.json', 'artifacts/slide-workorder.json'):
        d = load_json(indir / n)
        if isinstance(d, dict):
            return d
    for p in js:
        d = load_json(p)
        if isinstance(d, dict) and fk(d, ('slidecount', 'totalslides', 'slidespec')):
            return d
    return {}


def out_dir(arg, log=None):
    for c in ([arg] if arg else []) + [os.environ.get('OUTPUT_DIR'), '/app/output', 'output']:
        if c:
            try:
                p = Path(c)
                p.mkdir(parents=True, exist_ok=True)
                (p / '.w').write_text('1')
                (p / '.w').unlink()
                return p
            except Exception:
                log and log('output dir not writable: %s' % c)
    return Path.cwd()


def in_dir(arg):
    for c in ([arg] if arg else []) + ['/input', '/app/input', str(Path.cwd() / 'input')]:
        if Path(c).is_dir():
            return Path(c)
    return Path(arg or 'input')


def contract_keys(c):
    return ([str(k) for k in c] if isinstance(c, dict) else
            [k for k in c if isinstance(k, str)] if isinstance(c, list) else [])


def fill_contract(res, keys):
    """Echo each output_contract key under its own spelling; return the unresolved ones."""
    unk = []
    for k in keys:
        kl = re.sub(r'[^a-z]', '', str(k).lower())
        c = next((c for c, al in AN.items() if kl in al), None) or next(
            (c for c, al in AN.items() if any(len(a) > 4 and a in kl for a in al)), None)
        if c and res.get(c) is not None:
            res[k] = res[c]
        else:
            res[k] = [] if re.search(r'(map|list|slides|checks|exceptions)', kl) else None
            unk.append(k)
    return unk
