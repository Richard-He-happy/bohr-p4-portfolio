"""checks.py: export/render inspection and template-inheritance inspection.

Both checks read the real artefacts (the PDF with pdfinfo/pdffonts/pdftotext -bbox-layout,
the .pptx as a zip) and return per-item pass/fail with the evidence used, so a reviewer
can re-run the same command and see the same numbers.
"""
import hashlib
import re
import shutil
import subprocess
import zipfile
from pathlib import Path

# metric-compatible substitutes a fontconfig/LibreOffice stack may use; these are
# aliases, not silent substitutions, so they are reported but not failed
ALIAS = {
    'arial': ('liberationsans', 'arimo', 'helvetica', 'nexussans', 'arialunicodems', 'dejavusans'),
    'helvetica': ('arial', 'liberationsans'), 'timesnewroman': ('liberationserif', 'times', 'nimbusroman',
                                                               'dejavuserif'),
    'calibri': ('carlito', 'calibrilight'), 'cambria': ('caladea',), 'georgia': ('gelasio',),
    'couriernew': ('liberationmono', 'courier'), 'segoeui': ('selawik',), 'verdana': ('dejavusans',),
}


def sha(b):
    if isinstance(b, str):
        b = b.encode('utf-8')
    return hashlib.sha256(b or b'').hexdigest()


def clip(s, n=140):
    s = re.sub(r'\s+', ' ', str(s or '')).strip()
    return s if len(s) <= n else s[:n - 1].rstrip() + '…'


def esc(s):
    return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')


def run(cmd, timeout=180):
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout)
        return r.returncode, r.stdout.decode('utf-8', 'replace'), r.stderr.decode('utf-8', 'replace')
    except Exception as e:
        return -1, '', '%s: %s' % (type(e).__name__, e)


CJK_FONT = ('notosans', 'notoserif', 'sourcehan', 'simsun', 'simhei', 'pingfang', 'microsoftyahei',
            'wenquany', 'droid', 'uming', 'ukai', 'fandol', 'arphic')


def is_cjk_font(fam):
    return any(k in fam for k in CJK_FONT)


def family(name):
    """Font family key: subset prefix, weight/style suffix, MT suffix and separators removed."""
    f = re.sub(r'^[A-Z]{6}\+', '', str(name))
    f = re.sub(r'[-,_]?(Bold|Italic|Regular|Light|Medium|Semibold|Oblique|Black|Roman).*$', '', f, flags=re.I)
    f = re.sub(r'(PSMT|MT)$', '', f, flags=re.I)
    return re.sub(r'[^a-z0-9]', '', f.lower())


# ------------------------------------------------------------------ export
def pdf_fonts(pdf):
    exe = shutil.which('pdffonts')
    if not exe:
        return None, 'pdffonts unavailable on this runtime'
    rc, out, err = run([exe, str(pdf)])
    if rc != 0:
        return None, 'pdffonts rc=%d %s' % (rc, err.strip()[:120])
    rows = []
    for ln in out.splitlines():
        m = re.match(r'^(\S+)\s+(.+?)\s+(\S+)\s+(yes|no)\s+(yes|no)\s+(yes|no)\s+(\d+)\s+(\d+)\s*$', ln)
        if m:
            rows.append(dict(name=m.group(1), type=m.group(2).strip(), encoding=m.group(3),
                             embedded=m.group(4) == 'yes', subset=m.group(5) == 'yes'))
    return rows, 'pdffonts'


def pdf_boxes(pdf):
    """Word boxes per page from `pdftotext -bbox-layout` (real rendered geometry)."""
    exe = shutil.which('pdftotext')
    if not exe:
        return None, 'pdftotext unavailable on this runtime'
    rc, out, err = run([exe, '-bbox-layout', str(pdf), '-'])
    if rc != 0 or '<page' not in out:
        return None, 'pdftotext -bbox-layout rc=%d %s' % (rc, err.strip()[:120])
    pages = []
    for pm in re.finditer(r'<page width="([\d.]+)" height="([\d.]+)">(.*?)</page>', out, re.S):
        words = [(float(a), float(b), float(c), float(d)) for a, b, c, d in
                 re.findall(r'<word xMin="([\d.-]+)" yMin="([\d.-]+)" xMax="([\d.-]+)" yMax="([\d.-]+)"',
                            pm.group(3))]
        pages.append(dict(width=float(pm.group(1)), height=float(pm.group(2)), words=words))
    return pages, 'pdftotext -bbox-layout on %d page(s)' % len(pages)


def export_check(pdf, slides, fits, figures, tpl):
    out = dict(path=str(pdf) if pdf else None, checks=[], overall_pass=False)
    if not pdf or not Path(pdf).exists():
        out['checks'].append(dict(id='pdf_present', item='PDF export produced', status='fail',
                                  evidence='no PDF at %s (soffice missing or conversion failed)' % pdf))
        out['verdict'] = 'no PDF: the pptx remains the deliverable'
        return out
    b = Path(pdf).read_bytes()
    theme = [f for f in (tpl.get('fonts') or []) if f] or ['Arial']

    def add(i, item, status, evidence):
        out['checks'].append(dict(id=i, item=item, status=status, evidence=evidence))

    out['pdf'] = dict(bytes=len(b), sha256=sha(b), header=b[:4].decode('latin-1', 'replace'),
                      header_ok=b[:4] == b'%PDF')
    add('pdf_header', 'file starts with %PDF-', 'pass' if b[:4] == b'%PDF' else 'fail',
        'first bytes %r · %d bytes · sha256 %s' % (b[:5], len(b), sha(b)[:16]))
    # page count
    n, via = None, 'regex /Type /Page'
    if shutil.which('pdfinfo'):
        rc, info, _e = run([shutil.which('pdfinfo'), str(pdf)])
        m = re.search(r'Pages:\s+(\d+)', info)
        if rc == 0 and m:
            n, via = int(m.group(1)), 'pdfinfo'
    if n is None:
        n = len(re.findall(rb'/Type\s*/Page[^s]', b))
    out['page_count'] = dict(slides=slides, pdf_pages=n, via=via, ok=n == slides)
    add('page_count', 'PDF page count equals slide count', 'pass' if n == slides else 'fail',
        '%d slide(s) -> %d PDF page(s) via %s' % (slides, n, via))
    # fonts
    fonts, src = pdf_fonts(pdf)
    tm = [family(f) for f in theme]
    res, unembedded = [], [f['name'] for f in (fonts or []) if not f['embedded']]
    for f in fonts or []:
        fam = family(f['name'])
        st = ('inherited' if fam in tm else
              'metric-alias' if any(fam in ALIAS.get(t, ()) or t in ALIAS.get(fam, ()) for t in tm) else
              'cjk-fallback' if is_cjk_font(fam) else 'substituted')
        res.append(dict(pdf_font=f['name'], family=fam, theme_fonts=theme, status=st, embedded=f['embedded']))
    sub = [r['pdf_font'] for r in res if r['status'] == 'substituted']
    cjk = [r['pdf_font'] for r in res if r['status'] == 'cjk-fallback']
    out['fonts'] = dict(source=src, theme_fonts=theme, base_fonts=[f['name'] for f in (fonts or [])],
                        resolution=res, all_embedded=bool(fonts) and not unembedded, substituted=sub,
                        cjk_fallback=cjk, ok=(bool(fonts) and not unembedded and not sub))
    add('fonts_embedded', 'every PDF font is embedded (no viewer-side substitution)',
        'pass' if (fonts and not unembedded) else 'fail',
        'pdffonts: %s' % (', '.join('%s emb=%s' % (f['name'], 'yes' if f['embedded'] else 'no')
                                    for f in (fonts or [])) or 'not parsed'))
    add('fonts_inherited', 'PDF font families match the template theme font scheme',
        'pass' if (fonts and not sub) else ('warn' if fonts else 'fail'),
        'theme %s -> PDF %s%s%s' % (theme, [f['name'] for f in (fonts or [])],
                                    '' if not sub else ' · substituted: %s' % sub,
                                    '' if not cjk else ' · CJK glyph fallback (expected for Han text): %s' % cjk))
    # text overflow from rendered geometry
    boxes, bsrc = pdf_boxes(pdf)
    viol, worst = [], 0.0
    for i, pg in enumerate(boxes or [], 1):
        bad = []
        for x0, y0, x1, y1 in pg['words']:
            over = max(x1 - (pg['width'] - 1.0), y1 - (pg['height'] - 1.0), -x0 - 1.0, -y0 - 1.0)
            worst = max(worst, over)
            if over > 0:
                bad.append([round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1)])
        if bad:
            viol.append(dict(page=i, words=len(bad), sample=bad[:4],
                             page_size=[round(pg['width'], 2), round(pg['height'], 2)]))
    model = dict(max_utilization=max([f['util'] for f in fits] or [0]),
                 overflow_slides=[f['i'] for f in fits if f['util'] > 1.0])
    out['text_overflow'] = dict(method=bsrc, pages_checked=len(boxes or []), violations=viol,
                                worst_excess_pt=round(worst, 2), ok=bool(boxes) and not viol, modelled=model)
    add('text_overflow', 'no word crosses the page box in the rendered PDF',
        'pass' if (boxes and not viol) else ('fail' if boxes else 'unknown'),
        '%d page(s), %d word(s) checked, worst excess %.2f pt; modelled max utilization %.2f, modelled '
        'overflow slide(s) %s' % (len(boxes or []), sum(len(p['words']) for p in (boxes or [])), worst,
                                  model['max_utilization'], model['overflow_slides'] or 'none'))
    # images
    nimg = len(re.findall(rb'/Subtype\s*/Image', b))
    placed = int(figures.get('placed') or 0)
    out['images'] = dict(placed_in_deck=placed, pdf_image_xobjects=nimg, ok=(placed == 0 or nimg >= placed))
    add('figures_rendered', 'every picture placed in the deck reaches the PDF',
        'pass' if out['images']['ok'] else 'fail',
        '%d picture(s) placed -> %d image XObject(s) in the PDF' % (placed, nimg))
    # geometry
    out['geometry'] = dict(first_page_pt=[round(boxes[0]['width'], 2), round(boxes[0]['height'], 2)],
                           emu=[int(round(boxes[0]['width'] * 12700)), int(round(boxes[0]['height'] * 12700))]
                           ) if boxes else None
    hard = [c for c in out['checks'] if c['status'] == 'fail']
    out['overall_pass'] = not hard
    out['verdict'] = 'pass' if not hard else 'fail: ' + ', '.join(c['id'] for c in hard)
    return out


# ------------------------------------------------------------------ template
def ph_list(xml):
    out = []
    for m in re.finditer(r'<p:ph([^/>]*)/?>', xml):
        t = re.search(r'type="([^"]+)"', m.group(1))
        i = re.search(r'idx="(\d+)"', m.group(1))
        out.append((t.group(1) if t else 'body', int(i.group(1)) if i else None))
    return out


def _srgb(xml):
    return sorted(set(re.findall(r'<a:srgbClr val="([0-9A-Fa-f]{6})"', xml)))


def template_check(pptx, tpl, tpl_path, meta, n_slides):
    items = []

    def add(i, item, status, expected, actual, evidence):
        items.append(dict(id=i, item=item, status=status, expected=expected, actual=actual, evidence=evidence))

    try:
        with zipfile.ZipFile(pptx) as z:
            P = {n: z.read(n) for n in z.namelist()}
    except Exception as e:
        return dict(source=str(tpl_path), inherited=False, checks=[dict(id='pptx_readable', status='fail',
                                                                        item='pptx opens as an OPC package',
                                                                        evidence='%s: %s' % (type(e).__name__, e))],
                    failures=['pptx_readable'], overall_pass=False)
    T = tpl.get('parts') or {}
    inh = bool(tpl.get('ok'))
    if tpl_path and not inh:
        add('template_readable', 'the supplied template opens as an OPC package', 'warn',
            'readable .pptx', 'unreadable', 'inheritance could not be verified: builtin design was used instead')
    pres = P.get('ppt/presentation.xml', b'').decode('utf-8', 'replace')
    m = re.search(r'<p:sldSz[^>]*cx="(\d+)"[^>]*cy="(\d+)"', pres)
    sz = [int(m.group(1)), int(m.group(2))] if m else None
    want = tpl.get('sldSz') or [None, None]
    add('slide_size', 'slide size inherited from the master',
        'pass' if (sz and (not inh or want == sz)) else 'fail',
        '%s emu' % (want if inh else 'builtin 16:9'), '%s emu' % sz, 'presentation.xml/p:sldSz')
    dm = sorted(n for n in P if re.match(r'ppt/slideMasters/slideMaster\d+\.xml$', n))
    tm = sorted(n for n in T if re.match(r'ppt/slideMasters/slideMaster\d+\.xml$', n))
    add('master', 'slide master carried over byte-identical',
        'pass' if (dm and tm and sha(P[dm[0]]) == sha(T[tm[0]])) else ('n/a' if (not inh and dm) else 'fail'),
        'sha256 %s' % (sha(T[tm[0]])[:16] if tm else 'n/a'), 'sha256 %s' % (sha(P[dm[0]])[:16] if dm else 'none'),
        '%s vs template %s' % (dm[0] if dm else 'no master part', tm[0] if tm else 'no template master'))
    used, unres, same = [], [], 0
    for i in range(1, n_slides + 1):
        rels = P.get('ppt/slides/_rels/slide%d.xml.rels' % i, b'').decode('utf-8', 'replace')
        mm = re.search(r'Target="\.\./slideLayouts/(slideLayout\d+\.xml)"', rels)
        lay = 'ppt/slideLayouts/' + mm.group(1) if mm else None
        used.append(lay)
        if not lay or lay not in P:
            unres.append(i)
        elif inh and lay in T and sha(P[lay]) == sha(T[lay]):
            same += 1
    add('layouts_resolved', 'every slide points at a layout part that exists', 'pass' if not unres else 'fail',
        '%d slide(s), one layout each' % n_slides, '%d unresolved' % len(unres),
        'slide->layout: %s' % [u.rsplit('/', 1)[-1] if u else None for u in used])
    add('layouts_inherited', 'layout parts used are the template layouts, unmodified',
        'pass' if (inh and same == n_slides) else ('n/a' if not inh else 'warn'),
        'all %d slide(s) on unmodified template layouts' % n_slides,
        '%d/%d byte-identical layout part(s)' % (same, n_slides),
        'distinct layouts used: %s' % sorted({u.rsplit('/', 1)[-1] for u in used if u}))
    dt = sorted(n for n in P if re.match(r'ppt/theme/theme\d+\.xml$', n))
    tt = sorted(n for n in T if re.match(r'ppt/theme/theme\d+\.xml$', n))
    add('theme_part', 'theme part carried over byte-identical',
        'pass' if (dt and tt and sha(P[dt[0]]) == sha(T[tt[0]])) else ('n/a' if (not inh and dt) else 'fail'),
        'sha256 %s' % (sha(T[tt[0]])[:16] if tt else 'n/a'), 'sha256 %s' % (sha(P[dt[0]])[:16] if dt else 'none'),
        'theme part %s' % (dt[0] if dt else 'missing'))
    dx = (P[dt[0]] if dt else b'').decode('utf-8', 'replace')
    tx = (T[tt[0]] if tt else b'').decode('utf-8', 'replace')
    df, tf = _srgb(dx), _srgb(tx)
    add('theme_fonts', 'theme font scheme unchanged (no silent font swap)',
        'pass' if (sorted(set(re.findall(r'typeface="([^"]+)"', dx))) ==
                   sorted(set(re.findall(r'typeface="([^"]+)"', tx))) or not inh) else 'fail',
        sorted(set(re.findall(r'typeface="([^"]+)"', tx))) or 'builtin Arial',
        sorted(set(re.findall(r'typeface="([^"]+)"', dx))), 'typefaces declared in the output theme')
    add('theme_colours', 'colour scheme unchanged (accent colours not replaced)',
        'pass' if (df == tf or not inh) else 'fail', tf or 'builtin Academic scheme', df,
        '%d srgbClr value(s) compared with the template theme' % len(tf))
    over = []
    for i in range(1, n_slides + 1):
        x = P.get('ppt/slides/slide%d.xml' % i, b'').decode('utf-8', 'replace')
        over += ['slide%d:%s' % (i, v) for v in _srgb(x)]
    add('no_local_colour_override', 'slide bodies do not hard-code colours over the theme',
        'pass' if not over else 'warn', 'no srgbClr in slide bodies', over or 'none',
        '%d literal colour value(s) inside slide XML' % len(over))
    bad, tot = [], 0
    for i in range(1, n_slides + 1):
        lph = ph_list((T.get(used[i - 1]) or P.get(used[i - 1]) or b'').decode('utf-8', 'replace'))
        for t, idx in ph_list(P.get('ppt/slides/slide%d.xml' % i, b'').decode('utf-8', 'replace')):
            tot += 1
            if not any(t == lt and (idx is None or li is None or idx == li) for lt, li in lph):
                bad.append('slide%d:%s/%s' % (i, t, idx))
    add('placeholder_binding', 'every slide placeholder exists in its layout', 'pass' if not bad else 'fail',
        'ph type/idx present in the bound layout', '%d/%d bound' % (tot - len(bad), tot),
        'unbound: %s' % (bad[:6] or 'none'))
    ftr = [i for i in range(1, n_slides + 1)
           if any(t == 'ftr' for t, _x in ph_list(P.get('ppt/slides/slide%d.xml' % i, b'').decode('utf-8', 'replace')))]
    if tpl.get('footer_slot'):
        add('footer_slot', 'footer uses the template ftr placeholder', 'pass' if ftr else 'fail',
            'ftr placeholder on body slides', '%d slide(s) with ftr' % len(ftr),
            'layouts exposing ftr: %s' % [n.rsplit('/', 1)[-1] for n, inf in tpl.get('layouts', []) if 'ftr' in inf['types']])
    else:
        add('footer_slot', 'footer drawn as a text box (the template has no ftr slot)',
            'n/a' if not inh else 'warn', 'ftr placeholder', '%d slide(s) with ftr' % len(ftr),
            'no ftr placeholder in the template; footer text kept: %s' % clip(meta.get('footer'), 60))
    ft = esc(meta.get('footer') or '')[:48]
    got = sum(1 for i in range(1, n_slides + 1) if ft and ft in
              P.get('ppt/slides/slide%d.xml' % i, b'').decode('utf-8', 'replace'))
    add('footer_text', 'footer string matches the workorder verbatim', 'pass' if (not ft or got) else 'warn',
        clip(meta.get('footer'), 60), '%d/%d slide(s) carry it' % (got, n_slides),
        'single footer string reused on every slide, no per-slide rewrite')
    nm = [n for n in P if re.match(r'ppt/notesMasters/notesMaster\d+\.xml$', n)]
    add('notes_master', 'notes master present so speaker notes stay editable', 'pass' if nm else 'fail',
        'ppt/notesMasters/notesMaster1.xml', nm or 'missing', '%d notesMaster part(s)' % len(nm))
    dmed = sorted(n for n in P if n.startswith('ppt/media/'))
    tmed = sorted(n for n in T if n.startswith('ppt/media/'))
    add('media_copied', 'template media parts preserved', 'pass' if len(dmed) >= len(tmed) else 'warn',
        '%d template media part(s)' % len(tmed), '%d media part(s) in the output' % len(dmed),
        'media: %s' % (dmed[:4] or 'none'))
    hard = [i['id'] for i in items if i['status'] == 'fail' and i['id'] in (
        'slide_size', 'master', 'layouts_resolved', 'theme_fonts', 'theme_colours', 'placeholder_binding',
        'notes_master')]
    src = ('builtin-default' if not tpl_path else str(tpl_path)) if inh else (
        'builtin-default (template unreadable: %s)' % tpl_path if tpl_path else 'builtin-default')
    return dict(source=src, inherited=inh,
                template_sha256=(sha(Path(tpl_path).read_bytes())
                                 if tpl_path and Path(tpl_path).exists() else None),
                checks=items, failures=hard, passes=sum(i['status'] == 'pass' for i in items),
                fails=sum(i['status'] == 'fail' for i in items), warns=sum(i['status'] == 'warn' for i in items),
                na=sum(i['status'] == 'n/a' for i in items), overall_pass=not hard)
