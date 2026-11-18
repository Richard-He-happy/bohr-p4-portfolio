"""deckkit: stdlib helpers for paper->PPTX (PDF text/figure readers, sentence and
slide-role analysis, OOXML package writer that inherits an organizer template).
OOXML shells come from ../references/deck-parts.json."""
import hashlib
import os
import json
import math
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
import zipfile
import zlib
from pathlib import Path

A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
P = 'http://schemas.openxmlformats.org/presentationml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
PKGREL = 'http://schemas.openxmlformats.org/package/2006/relationships'
CT = 'application/vnd.openxmlformats-officedocument.'
PKGRT = 'http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties'
SLIDE_W, SLIDE_H = 12192000, 6858000
PARTS_PATH = Path(__file__).resolve().parent.parent / 'references' / 'deck-parts.json'
_PARTS = {}

def parts():
    global _PARTS
    if not _PARTS:
        doc = json.loads(PARTS_PATH.read_text(encoding='utf-8'))
        _PARTS = dict(doc.get('parts', doc))
        _PARTS.update({k: v for k, v in doc.items() if k != 'parts'})
        _PARTS['NS'] = ('xmlns:a="%s" xmlns:r="%s" xmlns:p="%s"' % (A, R, P))
    return _PARTS

def F(key, **kw):
    return parts()[key].format(**kw)

def esc(s):
    return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')

def bullet(text, sz=1800, bold=False, lvl=0, bu=None, tf=None):
    out = F('bullet', lvl=lvl, marL=228600 + 342900 * lvl, bu=bu or ('•' if not lvl else '–'),
            sz=sz, b=' b="1"' if bold else '', text=esc(text))
    if tf:
        # state the theme font on the run itself: PowerPoint and LibreOffice then agree,
        # and the PDF export can be checked against the theme font scheme
        out = out.replace('<a:rPr lang="en-US" sz="%d"%s dirty="0"/>' % (sz, ' b="1"' if bold else ''),
                          '<a:rPr lang="en-US" sz="%d"%s dirty="0"><a:latin typeface="%s"/></a:rPr>'
                          % (sz, ' b="1"' if bold else '', esc(tf)))
        out = out.replace('<a:buFont typeface="Arial"/>', '<a:buFont typeface="%s"/>' % esc(tf))
    return out

def sp(sid, name, ph, x, y, cx, cy, paras, sz=1800, bold=False, anchor='t', tf=None):
    body = ''.join(bullet(p[0], sz, bold, p[1], tf=tf) if isinstance(p, tuple) else p for p in paras)
    phx = ('<p:ph%s%s/>' % (' type="%s"' % ph[0] if ph[0] else '',
                            '' if ph[1] is None else ' idx="%d"' % ph[1])) if ph else '<p:ph/>'
    return F('sp', id=sid, name=esc(name), ph=phx, x=int(x), y=int(y), cx=int(cx), cy=int(cy),
             anchor=anchor, body=body)

def pic(sid, rid, name, x, y, cx, cy):
    return F('pic', id=sid, name=esc(name), rid=rid, x=int(x), y=int(y), cx=int(cx), cy=int(cy))

def slide_xml(shapes):
    return F('slide', NS=parts()['NS'], shapes=''.join(shapes))

def notes_xml(text):
    body = ''.join('<a:p><a:r><a:rPr lang="en-US" dirty="0"/><a:t>%s</a:t></a:r></a:p>' % esc(t)
                   for t in str(text).split('\n') if t.strip())
    return F('notes', NS=parts()['NS'], shapes=sp(2, 'Notes Placeholder 1', ('body', 1), 685800,
                                                  4343400, 5486400, 4114800, [body], 1200))

def rels(items):
    return F('rels', items=''.join(F('relItem', id=i, type=t, target=g) for i, t, g in items))

def norm(t):
    t = t.replace('\u00ad', '').replace('\ufb01', 'fi').replace('\ufb02', 'fl')
    t = re.sub(r'(\w)-\s*\n\s*(\w)', r'\1\2', t)
    t = re.sub(r'[ \t\u00a0]+', ' ', t)
    return re.sub(r'\n{2,}', '\n', t).strip()

def pdf_pages(path, log=None):
    exe = shutil.which('pdftotext')
    if exe:
        try:
            r = subprocess.run([exe, '-layout', '-enc', 'UTF-8', str(path), '-'],
                               capture_output=True, timeout=120)
            if r.returncode == 0 and r.stdout.strip():
                pages = [norm(p) for p in r.stdout.decode('utf-8', 'replace').split('\f')]
                pages = [p for p in pages if len(p) > 20]
                if pages:
                    return pages, 'pdftotext -layout'
        except Exception as e:
            log and log('pdftotext failed: %s' % e)
    try:
        pages = [p for p in _builtin(path.read_bytes()) if len(p) > 20]
        return pages, 'builtin-pdf-parser'
    except Exception as e:
        log and log('builtin pdf parser failed: %s' % e)
        return [], 'none'

def _builtin(data):
    objs = {int(m.group(1)): m.group(2)
            for m in re.finditer(rb'(?<![0-9])(\d+)\s+0\s+obj(.*?)endobj', data, re.S)}
    pages = sorted(n for n, b in objs.items() if re.search(rb'/Type\s*/Page(?![s\w])', b))
    out = []
    for n in pages:
        blobs = []
        for r in re.findall(rb'/Contents\s*(\[[^\]]*\]|\d+\s+\d+\s+R)', objs[n]):
            for num in re.findall(rb'(\d+)\s+\d+\s+R', r):
                sb = objs.get(int(num), b'')
                m = re.search(rb'stream\r?\n(.*?)endstream', sb, re.S)
                if not m:
                    continue
                raw = m.group(1)
                if b'FlateDecode' in sb:
                    try:
                        raw = zlib.decompressobj().decompress(raw)
                    except Exception:
                        continue
                blobs.append(raw)
        out.append(_content(b'\n'.join(blobs)))
    return out

def _pdf_str(tok):
    if tok[:1] == b'<':
        h = re.sub(rb'[^0-9A-Fa-f]', b'', tok)
        h += b'0' * (len(h) % 2)
        try:
            raw = bytes.fromhex(h.decode('ascii'))
        except Exception:
            return ''
        return raw.decode('utf-16-be', 'replace') if raw[:2] == b'\xfe\xff' else raw.decode('latin-1')
    s = tok[1:-1]
    mp = {b'n': b'\n', b'r': b'\r', b't': b'\t', b'b': b'\b', b'f': b'\f',
          b'(': b'(', b')': b')', b'\\': b'\\'}
    s = re.sub(rb'\\([nrtbf()\\])', lambda m: mp[m.group(1)], s)
    s = re.sub(rb'\\([0-7]{1,3})', lambda m: bytes([int(m.group(1), 8) & 255]), s)
    try:
        return s.decode('utf-8')
    except Exception:
        return s.decode('latin-1')

def _content(b):
    if not b:
        return ''
    out, buf = [], []
    for m in re.finditer(rb'\((?:\\.|[^\\()])*\)|<[0-9A-Fa-f\s]*>|TJ|Tj|T\*|ET|BT', b):
        t = m.group(0)
        if t in (b'Tj', b'TJ'):
            out.append(''.join(buf))
            buf = []
        elif t in (b'T*', b'ET', b'BT'):
            out.append('\n')
            buf = []
        else:
            buf.append(_pdf_str(t))
    out.append(''.join(buf))
    return norm(''.join(out))

def pdf_jpegs(path, limit=3):
    try:
        data = path.read_bytes()
    except Exception:
        return []
    out = []
    for m in re.finditer(rb'/Subtype\s*/Image(.{0,500}?)stream\r?\n', data, re.S):
        if b'DCTDecode' not in m.group(1):
            continue
        end = data.find(b'endstream', m.end())
        blob = data[m.end():end].rstrip(b'\r\n') if end > 0 else b''
        if blob[:2] == b'\xff\xd8' and len(blob) > 25000:
            out.append(blob)
    out.sort(key=len, reverse=True)
    return out[:limit]

def jpeg_size(blob):
    i = 2
    while i < len(blob) - 9:
        if blob[i] != 0xFF:
            i += 1
            continue
        if blob[i + 1] in (0xC0, 0xC1, 0xC2):
            return (int.from_bytes(blob[i + 7:i + 9], 'big'), int.from_bytes(blob[i + 5:i + 7], 'big'))
        i += 2 + int.from_bytes(blob[i + 2:i + 4], 'big')
    return (0, 0)

SEC = [('abstract', r'^abstract\b'), ('intro', r'^(\d+\.?\s*)?(introduction|background)\b'),
       ('related', r'^(\d+\.?\s*)?(related work|literature review)\b'),
       ('methods', r'^(\d+\.?\s*)?(methods?|materials and methods|experimental|methodology|approach|data)\b'),
       ('results', r'^(\d+\.?\s*)?(results?|findings)\b'), ('discussion', r'^(\d+\.?\s*)?discussion\b'),
       ('conclusion', r'^(\d+\.?\s*)?(conclusions?|summary)\b'),
       ('limits', r'^(\d+\.?\s*)?(limitations?|future (work|directions?))\b')]
CJK = re.compile(r'[\u4e00-\u9fff]')
# Chinese section headings: the English regexes never match them, so a Chinese paper
# would otherwise expose a single 'body' label and the page diff could not check anything
CJK_HDR = [('limits', ('局限', '局限性与展望', '不足与展望')), ('conclusion', ('结论', '总结', '结束语')),
           ('discussion', ('讨论', '结果与讨论', '解读')), ('related', ('相关工作', '文献综述')),
           ('results', ('结果', '研究结果', '主要结果')), ('methods', ('方法', '材料与方法', '研究方法', '实验设计')),
           ('intro', ('引言', '前言', '背景', '研究背景')), ('abstract', ('摘要', '中文摘要'))]

def is_cjk(text):
    return bool(text) and len(CJK.findall(text)) > max(20, 0.04 * len(text))

def heading(ln):
    """Section label of a heading line, else None.

    Markdown '#' prefixes and '1.' numbering are accepted. A prose sentence that happens
    to start with a section word ("Data were collected ...") is not a heading: it is
    rejected by the word limit and the terminal punctuation.
    """
    raw = ln.strip()
    h = raw.lower().lstrip('#').strip().rstrip('.:').strip()
    lo = 2 if len(CJK.findall(h)) > 0.3 * max(len(h), 1) else 3
    if not (lo <= len(h) <= 45) or len(h.split()) > 6:
        return None
    if raw.endswith(('.', '。', '!', '?', ';', '；', '！', '？')) and len(h.split()) > 3:
        return None
    for name, pat in SEC:
        if re.match(pat, h):
            return name
    hh = re.sub(r'^[\d.\s、一二三四五六七八九十]+', '', h)
    for name, pres in CJK_HDR:
        if hh.startswith(pres):
            return name
    return None

def sents(pages, legacy=False):
    """Sentences with the section label of their own position in the text.

    legacy=True restores the v1 behaviour (one label per page: the last heading seen
    before the sentences), which mislabels every sentence of a single-page source.
    """
    out, sec, first = [], 'body', None
    for i, pg in enumerate(pages, 1):
        lines = [ln.strip() for ln in pg.split('\n') if ln.strip()]
        if first is None and lines:
            first = lines[0]
        head = next((j for j, ln in enumerate(lines) if heading(ln)), None)
        if legacy:
            for ln in lines[:500]:
                sec = heading(ln) or sec
        for j, ln in enumerate(lines):
            if first and (ln == first or (len(first) > 20 and ln.startswith(first[:30]))):
                continue        # document title / running header
            if i == 1 and head not in (None, 0) and j < head:
                continue        # title block before the first section heading
            h = heading(ln)
            if h:
                if not legacy:
                    sec = h
                continue
            if ln.startswith('#'):
                continue
            # a Chinese sentence carries the same content in fewer characters
            lim = 18 if len(CJK.findall(ln)) > 0.3 * max(len(ln), 1) else 45
            if len(ln) < lim - 5:
                continue
            for s in re.split(r'(?<=[.!?;])\s+|(?<=[。！？；])', ln):
                s = s.strip().lstrip('-•\u2022 ')
                if len(s) >= lim and re.search(r'[A-Za-z\u4e00-\u9fff]', s):
                    out.append({'text': s, 'sec': sec, 'page': i})
    return out

def score(s):
    t, v = s['text'], 0.0
    if re.search(r'\d', t):
        v += 2.0
    if re.search(r'%|p\s*[<=>]\s*0?\.\d|\bCI\b|±|increase|decrease|higher|lower|reduc|improv', t, re.I):
        v += 1.4
    if re.search(r'\b(fig(?:ure)?\.?\s*\d|table\s*\d)\b|图\s*\d|表\s*\d', t, re.I):
        v += 1.2
    if s['sec'] in ('results', 'abstract', 'conclusion'):
        v += 1.0
    if re.search(r'\b(we|our|here|this (study|paper|work))\b|本文|本研究', t, re.I):
        v += 0.5
    if re.search(r'\b(however|but|although|limitation|only|warrant|caution)\b|然而|局限', t, re.I):
        v += 0.4
    return v - min(len(t) / 400.0, 1.2)

def pick(pool, used, n, prefer=(), kw=None, strict=False, must=None, anchor=None, ban=()):
    """Best unused sentences for a page.

    strict=True keeps the page inside its own section contract when that section still
    holds enough unused sentences, so a "methods" page cannot be filled with results
    sentences; it falls back to the whole pool instead of leaving the page empty.
    """
    cands = []
    for i, s in enumerate(pool):
        if i in used or s['sec'] in ban:
            continue
        v = score(s) + (1.5 if s['sec'] in prefer else 0)
        if kw and re.search(kw, s['text'], re.I):
            v += 1.2
        cands.append((v, i, s))
    if strict and prefer:
        inhouse = [c for c in cands if c[2]['sec'] in prefer]
        if len(inhouse) >= n:
            cands = inhouse
    cands.sort(key=lambda x: -x[0])
    top = cands[:n]
    if must and top and not any(re.search(must, c[2]['text'], re.I) for c in top):
        # a results page that reports a figure has to cite it: swap the weakest pick
        alt = next((c for c in cands[n:] if re.search(must, c[2]['text'], re.I)), None)
        if alt:
            top = top[:-1] + [alt]
    if anchor and top and not any(c[2]['sec'] == anchor for c in top):
        # the page named after a section must carry at least one line from it
        alt = next((c for c in cands[n:] if c[2]['sec'] == anchor), None)
        if alt:
            top = top[:-1] + [alt]
    sel = sorted(top, key=lambda x: x[1])
    used.update(i for _v, i, s in sel)
    return [s for _v, _i, s in sel]

def display(s, maxc=118):
    if len(s) <= maxc:
        return s
    cut = s[:maxc]
    for sep in ('; ', ', ', ' '):
        j = cut.rfind(sep)
        if j >= maxc * 0.55:
            return cut[:j].rstrip(' ,;，；') + ' …'
    return cut.rstrip() + ' …'

def roles(n):
    seq = ['title'] + (['outline'] if n >= 8 else []) + ['background', 'question', 'methods']
    seq += ['results'] * max(1, n - len(seq) - 4) + ['discussion', 'limitations', 'conclusion', 'thanks']
    for r in ('limitations', 'outline', 'question', 'discussion', 'background'):
        if len(seq) > n and r in seq:
            seq.remove(r)
    while len(seq) > n:
        seq.pop(len(seq) - 3)
    while len(seq) < n:
        seq.insert(max(1, seq.index('discussion')), 'results')
    return seq[:n]

ROLE_T = {'title': ('', ''), 'outline': ('Outline', '结构'),
          'background': ('Background', '研究背景'),
          'question': ('Research question', '研究问题'),
          'methods': ('Methods & data', '方法与数据'),
          'results': ('Results', '结果'),
          'discussion': ('Interpretation', '解读'),
          'limitations': ('Limitations', '局限与边界'),
          'conclusion': ('Conclusions', '结论'),
          'thanks': ('Thank you', '致谢')}

def type_of(name):
    b = name.rsplit('/', 1)[-1]
    if name == 'ppt/presentation.xml':
        return CT + 'presentationml.presentation.main+xml'
    m = re.search(r'/(slideLayout|slideMaster|notesMaster|notesSlide|slide)\d+\.xml$', name)
    if m:
        return CT + 'presentationml.%s+xml' % m.group(1)
    if name.startswith('ppt/theme/'):
        return CT + 'theme+xml'
    if b in ('presProps.xml', 'viewProps.xml', 'tableStyles.xml'):
        return CT + 'presentationml.' + b[:-4] + '+xml'
    return None

def pjoin(base, tgt):
    out = []
    for s in (base.split('/') if base else []) + tgt.split('/'):
        if s in ('', '.'):
            continue
        if s == '..':
            out and out.pop()
        else:
            out.append(s)
    return '/'.join(out)

def write_pkg(path, parts_):
    parts_ = dict(parts_)
    names = set(parts_)
    for n in [x for x in names if x.endswith('.rels')]:
        try:
            root = ET.fromstring(parts_[n])
        except Exception:
            parts_.pop(n, None)
            continue
        src = n.replace('_rels/', '')
        src = src[:-5] if src.endswith('.rels') else src
        base = src.rsplit('/', 1)[0] if '/' in src else ''
        dropped = False
        for rel in list(root):
            tgt = rel.get('Target') or ''
            if (rel.get('TargetMode') or '') == 'External':
                continue
            full = tgt.lstrip('/') if tgt.startswith('/') else pjoin(base, tgt)
            if full not in names:
                root.remove(rel)
                dropped = True
        if dropped:
            parts_[n] = ET.tostring(root, encoding='UTF-8', xml_declaration=True)
    ct = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.'
          'openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType='
          '"application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" '
          'ContentType="application/xml"/><Default Extension="jpg" ContentType="image/jpeg"/>'
          '<Default Extension="png" ContentType="image/png"/>']
    ct += ['<Override PartName="/%s" ContentType="%s"/>' % (n, t) for n in sorted(parts_)
           if not n.endswith('.rels') for t in [type_of(n)] if t]
    parts_['[Content_Types].xml'] = ('%s</Types>' % ''.join(ct)).encode('utf-8')
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        for n in ['[Content_Types].xml'] + sorted(k for k in parts_ if k != '[Content_Types].xml'):
            zi = zipfile.ZipInfo(n, date_time=(2020, 1, 1, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(zi, parts_[n])
    return path

def read_template(path):
    info = {'parts': {}, 'layouts': [], 'masters': [], 'sldSz': [SLIDE_W, SLIDE_H], 'fonts': [],
            'footer_slot': False, 'ok': False, 'path': str(path), 'error': None}
    keep = ('ppt/slideMasters/', 'ppt/slideLayouts/', 'ppt/theme/', 'ppt/notesMasters/', 'ppt/media/')
    try:
        with zipfile.ZipFile(path) as z:
            for n in z.namelist():
                if n.startswith(keep) or n in ('ppt/tableStyles.xml', 'ppt/presProps.xml'):
                    info['parts'][n] = z.read(n)
            pres = z.read('ppt/presentation.xml').decode('utf-8', 'replace')
        P = info['parts']
        m = re.search(r'<p:sldSz[^>]*cx="(\d+)"[^>]*cy="(\d+)"', pres)
        if m:
            info['sldSz'] = [int(m.group(1)), int(m.group(2))]
        for n in sorted(k for k in P if re.match(r'ppt/slideLayouts/slideLayout\d+\.xml$', k)):
            info['layouts'].append((n, probe(P[n])))
        info['masters'] = sorted(k for k in P if re.match(r'ppt/slideMasters/slideMaster\d+\.xml$', k))
        th = sorted(k for k in P if re.match(r'ppt/theme/theme\d+\.xml$', k))
        if th:
            info['theme_part'] = th[0]
            info['fonts'] = sorted(set(f for f in re.findall(r'typeface="([^"]+)"',
                                                             P[th[0]].decode('utf-8', 'replace')) if f))
        info['footer_slot'] = any('ftr' in i['types'] for _n, i in info['layouts'])
        if th:
            tx = P[th[0]].decode('utf-8', 'replace')
            mj = re.search(r'<a:majorFont>\s*<a:latin typeface="([^"]*)"', tx)
            mn = re.search(r'<a:minorFont>\s*<a:latin typeface="([^"]*)"', tx)
            info['major_font'] = mj.group(1) if mj else ''
            info['minor_font'] = mn.group(1) if mn else ''
        info['ok'] = bool(info['layouts']) and bool(info['masters'])
    except Exception as e:
        info['error'] = '%s: %s' % (type(e).__name__, e)
    return info

def probe(data):
    out = {'types': []}
    try:
        root = ET.fromstring(data)
    except Exception:
        return out
    for s_ in root.iter('{%s}sp' % P):
        ph = s_.find('.//{%s}ph' % P)
        if ph is not None:
            out['types'].append(ph.get('type') or 'body')
    return out

def export_pdf(pdf, pptx, work, pages, exc):
    exe = shutil.which('soffice') or shutil.which('libreoffice')
    if exe:
        try:
            (work / '_lo').mkdir(parents=True, exist_ok=True)
            subprocess.run([exe, '--headless', '--norestore', '--nologo', '--convert-to', 'pdf',
                            '--outdir', str(pdf.parent.resolve()), str(pptx.resolve())],
                           capture_output=True, timeout=280, cwd=str(work),
                           env=dict(os.environ, HOME=str((work / '_lo').resolve())))
            if pdf.exists() and pdf.read_bytes()[:4] == b'%PDF' and pdf.stat().st_size > 800:
                return {'method': 'libreoffice-headless', 'degraded': False}
        except Exception:
            pass
    try:
        txt_pdf(pdf, pages)
        exc.append({'code': 'PDF_TEXT_FALLBACK', 'stage': 'export',
                    'detail': 'no LibreOffice/soffice on this runtime; a stdlib text-layer PDF was '
                              'written as export preview (pptx remains the authoritative editable source)',
                    'action': 're-export with PowerPoint/LibreOffice for pixel-accurate delivery'})
        return {'method': 'stdlib-text-fallback', 'degraded': True}
    except Exception as _e:
        exc.append({'code': 'PDF_RENDER_UNAVAILABLE', 'stage': 'export',
                    'detail': 'no working LibreOffice/soffice on this runtime; PDF fallback failed: %s' % _e,
                    'action': 're-export the pptx to PDF in PowerPoint/LibreOffice for delivery'})
        return {'method': 'none', 'degraded': True}

def checks(pages, tpl, meta, audit, fits, figs, exp, pdfn, tsrc, filled, unk, W):
    r, n = [p['role'] for p in pages], len(pages)
    return {'mode': meta.get('mode'),
            'source_preservation': meta.get('source_preservation'),
            'template_inheritance': meta.get('template_inheritance'),
            'slide_count': {'requested': meta['requested'], 'actual': n, 'pass': meta['requested'] in (None, n)},
            'page_order': {'roles': r, 'pass': r[0] == 'title' and r[-1] == 'thanks'},
            'template': {'source': tsrc, 'inherited': bool(tpl.get('ok')), 'slide_width_emu': W,
                         'layouts': len(tpl.get('layouts', [])), 'theme_fonts': (tpl.get('fonts') or ['Arial'])[:5],
                         'footer_slot': bool(tpl.get('footer_slot')), 'footer_text': meta['footer'],
                         'title_slide': r[0] == 'title', 'thanks_slide': r[-1] == 'thanks'},
            'notes': {'with_notes': sum(1 for p in pages if p.get('notes')), 'pass': all(p.get('notes') for p in pages)},
            'text_fit': {'max_utilization': max([f['util'] for f in fits] or [0]),
                         'overflow_slides': [f['i'] for f in fits if f['util'] > 1.0]},
            'figures': figs, 'evidence': {'bullets': audit['bullets'], 'verified': audit['verified'],
                                          'pass': audit['bullets'] > 0 and audit['verified'] == audit['bullets']},
            'export': {'method': exp['method'], 'degraded': exp['degraded'], 'pages': pdfn, 'matches_slides': pdfn in (None, n)},
            'contract': {'required_keys': filled + len(unk), 'filled': filled, 'unknown_keys': unk},
            'overall_pass': bool(audit['bullets'] and audit['verified'] == audit['bullets'] and not exp['degraded'])}

def fit_util(texts, cx, cy, sz, cjk):
    pt = max(sz / 100.0, 6.0)
    cpl = max(8, int((cx / 12700) * 0.98 / (pt if cjk else pt * 0.52)))
    return sum(max(1, math.ceil(len(t) / cpl)) for t in texts) / max(1, int((cy / 12700 - 10) / (pt * 1.34)))

def slide_shapes(page, W, H, tpl, footer, zh):
    M, TW, ty, th = int(W * 0.062), W - int(W * 0.124), int(H * 0.05), int(H * 0.16)
    by = ty + th + int(H * 0.015)
    bh = int(H * 0.885) - by
    MJ, MN = tpl.get('major_font') or '', tpl.get('minor_font') or ''
    shapes = []
    if page['role'] == 'title':
        shapes.append(sp(2, 'Title 1', ('ctrTitle', None) if tpl.get('has_ctr') else ('title', None),
                            M, int(H * 0.26), TW, int(H * 0.26), [(page['title'], 0)], 3200, True, tf=MJ))
        if page['bullets']:
            shapes.append(sp(3, 'Subtitle 2', (None, 1), M, int(H * 0.56), TW, int(H * 0.2),
                                [(t, 0) for t, _l in page['bullets']], 1600, tf=MN))
        return shapes, 0.0
    shapes.append(sp(2, 'Title 1', ('title', None), M, ty, TW, th, [(page['title'], 0)], 3000, True, tf=MJ))
    texts, img = [t for t, _l in page['bullets']], page.get('images') or []
    bw = int(TW * 0.52) if img else TW
    sz, util = (2000 if len(texts) <= 3 else 1800 if len(texts) <= 4 else 1600), 0.0
    while sz > 1200:
        util = fit_util(texts, bw, bh, sz, zh)
        if util <= 1.0:
            break
        sz -= 100
    if texts:
        shapes.append(sp(3, 'Content 2', (None, 1), M, by, bw, bh, list(page['bullets']), sz, tf=MN))
    if img:
        iw = int(TW * 0.44)
        w, h = jpeg_size(img[0])
        ih = min(bh, int(iw * (h / w)) if w else int(bh * 0.7))
        shapes.append(pic(9, 'rId2', 'Figure 1', M + bw + int(TW * 0.02), by, iw, max(ih, int(bh * 0.4))))
    if footer:
        shapes.append(sp(4, 'Footer 3', ('ftr', None) if tpl.get('footer_slot') else None,
                            M, int(H * 0.93), TW, int(H * 0.05), [(footer, 0)], 1000, tf=MN))
    return shapes, round(util, 2)


def txt_pdf(path, pages):
    """Minimal standards-compliant PDF (text layer) used when LibreOffice is unavailable."""
    from pathlib import Path as _P
    W, H = 842, 595

    def _san(s):
        out = []
        for ch in str(s or ''):
            o = ord(ch)
            if o < 32:
                continue
            out.append(ch if o < 256 else '?')
        return ''.join(out)

    def _esc(s):
        return _san(s).replace('\\', r'\\').replace('(', r'\(').replace(')', r'\)')

    def _wrap(s, n):
        words = str(s or '').split()
        lines, cur = [], ''
        for w in words:
            if len(cur) + len(w) + 1 > n and cur:
                lines.append(cur)
                cur = w
            else:
                cur = (cur + ' ' + w).strip()
        if cur:
            lines.append(cur)
        return lines or ['']

    objs = [None, None, None]
    objs[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objs[2] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
    kids = []
    for pg in pages or []:
        pg = pg if isinstance(pg, dict) else {'title': str(pg)}
        title = pg.get('title') or pg.get('claim') or pg.get('heading') or ''
        bullets = pg.get('bullets') or pg.get('points') or []
        if isinstance(bullets, dict):
            bullets = list(bullets.values())
        items = [(20, title)]
        for b in bullets[:9]:
            if isinstance(b, dict):
                b = b.get('text') or b.get('bullet') or b.get('point') or ''
            items.append((12, '- ' + str(b)))
        lines = []
        for size, t in items:
            for ln in _wrap(t, 92 if size > 15 else 108):
                lines.append((size, ln))
        ops = ['BT', '1 0 0 1 46 548 Tm']
        y = 548
        for size, ln in lines[:40]:
            y -= (size + 9)
            ops.append('/F1 %d Tf' % size)
            ops.append('1 0 0 1 46 %d Tm' % max(30, y))
            ops.append('(%s) Tj' % _esc(ln))
        ops.append('ET')
        stream = ('\n'.join(ops)).encode('latin-1', 'replace')
        cid = len(objs) + 1
        objs.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
        pid = len(objs) + 1
        objs.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d] /Resources << /Font << /F1 3 0 R >> >> /Contents %d 0 R >>" % (W, H, cid))
        kids.append(pid)
    if not kids:
        stream = b"BT /F1 18 Tf 1 0 0 1 46 520 Tm (No pages) Tj ET"
        cid = len(objs) + 1
        objs.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
        pid = len(objs) + 1
        objs.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 842 595] /Resources << /Font << /F1 3 0 R >> >> /Contents %d 0 R >>" % cid)
        kids.append(pid)
    objs[1] = b"<< /Type /Pages /Kids [" + b" ".join(b"%d 0 R" % k for k in kids) + b"] /Count %d >>" % len(kids)
    buf = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offs = []
    for i, o in enumerate(objs, 1):
        offs.append(len(buf))
        buf += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(buf)
    buf += b"xref\n0 %d\n" % (len(objs) + 1)
    buf += b"0000000000 65535 f \n"
    for off in offs:
        buf += b"%010d 00000 n \n" % off
    buf += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    _P(path).write_bytes(bytes(buf))
    return len(kids)
