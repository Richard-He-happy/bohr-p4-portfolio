"""build.py: page planning, plan reuse, notice deck, slide assembly, OOXML packaging."""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import deckkit as dk  # noqa: E402

# role -> (bullets, preferred sections, keyword boost)
RULES = {'background': (3, ('abstract', 'intro'), r'gap|need|challenge|however|remains|未'),
         'question': (2, ('abstract', 'intro'), r'\bwe (aim|ask|investigate|test)|objective|here we|本文'),
         'methods': (3, ('methods', 'related'), None),
         'results': (3, ('results', 'abstract'), r'\d'),
         'discussion': (3, ('discussion', 'results'), r'suggest|indicat|imply|consistent|表明'),
         'limitations': (3, ('limits', 'discussion'), r'limitation|future|further|only|局限'),
         'conclusion': (3, ('conclusion', 'abstract'), r'conclu|overall|summary|综上')}
NOTE = {'zh': '本页角色：{t}。要点逐字取自 {l}。讲法：先结论「{f}」，再按页序给证据，末句过渡到「{n}」。讲稿为提示非原文。',
        'en': 'Role: {t}. Bullets verbatim from {l}. Open "{f}", then evidence in page order; bridge to "{n}". Speaking prompt.'}


def clean_title(t):
    t = re.sub(r'^[#=\-*\s]+', '', str(t or ''))
    t = re.sub(r'\s*#+\s*$', '', t)
    return re.sub(r'\s+', ' ', t).strip()


def make_pages(pool, meta, n, lang, exc):
    L, rr, used, pages = (1 if lang == 'zh' else 0), dk.roles(max(3, n)), set(), []
    # every section that some later role names in its contract is reserved until that
    # role has had its turn; otherwise a results page steals the only conclusion line
    reserved = {s for r, (_k, kinds, _kw) in RULES.items() if r in rr for s in kinds[:1]}
    for role in rr:
        t = dk.ROLE_T[role][L]
        if role in ('title', 'outline', 'thanks'):
            bl = ([(b, 0) for b in meta['subtitle']] if role == 'title' else
                  [(dk.ROLE_T[r][L], 0) for r in rr if r not in ('title', 'outline', 'thanks')]
                  if role == 'outline' else [(meta['credit'], 0)])
            pages.append({'role': role, 'title': meta['title'] if role == 'title' else t, 'src': [],
                          'bullets': bl, 'frame': True})
            continue
        k, kinds, kw = RULES[role]
        must = r'\b(fig(?:ure)?|table)s?\.?\s*\d|图\s*\d|表\s*\d' if role == 'results' else None
        # a page may only borrow sentences another role has a claim on after that role
        # has had its turn (see RESERVED / the second pass below)
        ss = dk.pick(pool, used, k, kinds, kw, strict=True, must=must, anchor=kinds[0],
                     ban=reserved - {kinds[0]}) or dk.pick(pool, used, 2)
        if not ss:
            exc.append({'code': 'POOL_EXHAUSTED', 'stage': 'plan', 'detail': 'no sentence left for %s' % role})
            continue
        if role == 'results':
            t = '%s %d' % (t, 1 + sum(1 for p in pages if p['role'] == 'results'))
        pages.append({'role': role, 'title': t, 'src': ss,
                      'bullets': [(dk.display(s['text']), 0) for s in ss]})
    return pages


def fill_notes(pages, meta, lang):
    """Speaker notes are prompts, not a second copy of the paper."""
    L = 1 if lang == 'zh' else 0
    for i, p in enumerate(pages):
        if p['role'] in ('title', 'thanks', 'notice'):
            p['notes'] = ('封面/致谢页：%s。来源：%s。' if L else 'Opening/closing: %s. Source: %s.') % (
                p['title'], meta['src_label'])
        else:
            p['notes'] = NOTE['zh' if L else 'en'].format(
                t=p['title'], l='、'.join(sorted({'p.%d' % s['page'] for s in p['src']})) or meta['src_label'],
                f=dk.display(p['bullets'][0][0], 60) if p['bullets'] else '',
                n=pages[i + 1]['title'] if i + 1 < len(pages) else ('结束' if L else 'the end'))
    return pages


def plan_from_file(path, pool, exc):
    """v0 rollback: rebuild the deck from a recorded plan instead of re-planning."""
    try:
        d = json.loads(Path(path).read_text(encoding='utf-8', errors='replace'))
    except Exception:
        d = None
    if not isinstance(d, dict) or not isinstance(d.get('pages'), list):
        exc.append({'code': 'PLAN_REUSE_INVALID', 'stage': 'plan', 'detail': '%s is not a page plan' % path})
        return None
    idx = {s['text']: s for s in pool}
    pages, miss = [], 0
    for p in d['pages']:
        q = [idx[t] for t in (p.get('quotes') or []) if t in idx]
        miss += sum(1 for t in (p.get('quotes') or []) if t not in idx)
        if not q and p.get('role') not in ('title', 'outline', 'thanks'):
            continue
        pages.append({'role': p.get('role') or 'background', 'title': p.get('title') or p.get('role'),
                      'src': q, 'bullets': [(dk.display(s['text']), 0) for s in q]})
    if miss:
        exc.append({'code': 'PLAN_REUSE_MISS', 'stage': 'plan',
                    'detail': '%d recorded quote(s) missing from the current source' % miss})
    return pages or None


def ensure_frames(pages, meta, lang):
    """Re-fill cover/outline/closing lines after a plan replay (they carry no quotes)."""
    L = 1 if lang == 'zh' else 0
    rr = [p['role'] for p in pages if p['role'] not in ('title', 'outline', 'thanks', 'notice')]
    for p in pages:
        if p.get('bullets'):
            continue
        if p['role'] == 'title':
            p['bullets'] = [(b, 0) for b in meta['subtitle']]
        elif p['role'] == 'outline':
            p['bullets'] = [(dk.ROLE_T[r][L], 0) for r in rr]
        elif p['role'] == 'thanks':
            p['bullets'] = [(meta['credit'], 0)]
    return pages


def notice_pages(lang, missing):
    """A minimal, honest deck for an empty/broken input: no scientific claim."""
    zh = lang == 'zh'
    return [
        {'role': 'notice', 'title': '输入不完整：没有可用正文' if zh else 'Input incomplete - no usable source text',
         'src': [], 'frame': True, 'bullets': [
             ('未在输入目录找到可读正文（PDF 文本层 / DOCX / TXT / MD）。' if zh else
              'No readable source text was found in the input directory (PDF text layer, DOCX, TXT, MD).', 0),
             ('已检查：case.json、material.json、artifacts/slide-workorder.json 与全部附件。' if zh else
              'Checked: case.json, material.json, artifacts/slide-workorder.json and every attachment.', 0),
             ('请把带文本层的论文放进输入目录后重跑；本次未生成任何科学结论。' if zh else
              'Re-run with a paper that has a text layer; no scientific claim was generated here.', 0)]},
        {'role': 'notice', 'title': '需要什么输入' if zh else 'What this skill needs', 'src': [], 'frame': True,
         'bullets': [('case.json（output_contract 原样回填）' if zh else 'case.json with output_contract', 0),
                     ('论文 PDF/DOCX/TXT/MD，需可提取文字' if zh else 'paper PDF/DOCX/TXT/MD with extractable text', 0),
                     ('可选：template.pptx 与 artifacts/slide-workorder.json' if zh else
                      'optional: template.pptx and artifacts/slide-workorder.json', 0)]},
        {'role': 'notice', 'title': '本次状态' if zh else 'Status of this run', 'src': [], 'frame': True,
         'bullets': [('status = insufficient_evidence；缺口：%s' % '、'.join(missing[:4]) if zh else
                      'status = insufficient_evidence; gaps: %s' % ', '.join(missing[:4]), 0)]}]


def layouts_pick(tpl, role):
    lays, need = tpl.get('layouts') or [], ('ctrTitle' if role == 'title' else 'title')
    if not lays:
        return None
    if role == 'notice':
        return lays[-1][0]
    for name, inf in lays:
        if need in inf['types'] and (role == 'title' or any(t in inf['types'] for t in ('obj', 'body', 'tx'))):
            return name
    return lays[0][0]


def build_package(out, tpl, decks, title, author, stamp):
    """Write the OOXML package, copying the template's master/layouts/theme verbatim."""
    P, R, NS = {}, dk.R, dk.parts()['NS']
    if tpl.get('ok'):
        P.update(tpl['parts'])
        masters, layouts, (sw, sh) = tpl['masters'], [n for n, _i in tpl['layouts']], tpl['sldSz']
    else:
        P.update({k: v.encode() for k, v in dk.parts()['defaultPackage']['parts'].items()})
        masters, layouts = ['ppt/slideMasters/slideMaster1.xml'], ['ppt/slideLayouts/slideLayout1.xml']
        sw, sh = dk.SLIDE_W, dk.SLIDE_H
    prels, mids, sids, rid, media = [], [], [], 0, len([k for k in P if k.startswith('ppt/media/')])
    for m in masters:
        rid += 1
        prels.append(('rId%d' % rid, R + '/slideMaster', m.replace('ppt/', '')))
        mids.append('<p:sldMasterId id="%d" r:id="rId%d"/>' % (2147483647 + rid, rid))
    for i, d in enumerate(decks, 1):
        lay = d.get('layout') if d.get('layout') in layouts else layouts[min(1, len(layouts) - 1)]
        rid += 1
        P['ppt/slides/slide%d.xml' % i] = dk.slide_xml(d['shapes']).encode()
        srels = [('rId1', R + '/slideLayout', '../slideLayouts/' + lay.rsplit('/', 1)[-1])]
        for blob in d.get('images', []):
            media += 1
            P['ppt/media/image%d.jpg' % media] = blob
            srels.append(('rId%d' % (len(srels) + 1), R + '/image', '../media/image%d.jpg' % media))
        srels.append(('rId%d' % (len(srels) + 1), R + '/notesSlide', '../notesSlides/notesSlide%d.xml' % i))
        P['ppt/notesSlides/notesSlide%d.xml' % i] = dk.notes_xml(d.get('notes') or ' ').encode()
        P['ppt/notesSlides/_rels/notesSlide%d.xml.rels' % i] = dk.rels(
            [('rId1', R + '/slide', '../slides/slide%d.xml' % i),
             ('rId2', R + '/notesMaster', '../notesMasters/notesMaster1.xml')]).encode()
        P['ppt/slides/_rels/slide%d.xml.rels' % i] = dk.rels(srels).encode()
        prels.append(('rId%d' % rid, R + '/slide', 'slides/slide%d.xml' % i))
        sids.append('<p:sldId id="%d" r:id="rId%d"/>' % (255 + i, rid))
    rid += 1
    prels.append(('rId%d' % rid, R + '/presProps', 'presProps.xml'))
    P.setdefault('ppt/presProps.xml', dk.F('presProps', NS=NS).encode())
    P['ppt/_rels/presentation.xml.rels'] = dk.rels(prels).encode()
    P['ppt/presentation.xml'] = dk.F('presentation', NS=NS, masters=''.join(mids), slides=''.join(sids),
                                     cx=sw, cy=sh).encode()
    P['_rels/.rels'] = dk.rels([('rId1', R + '/officeDocument', 'ppt/presentation.xml'),
                                ('rId2', dk.PKGRT, 'docProps/core.xml')]).encode()
    P['docProps/core.xml'] = dk.F('core', title=dk.esc(title), author=dk.esc(author), stamp=stamp).encode()
    dk.write_pkg(out, P)
    return {'slides': len(decks), 'bytes': out.stat().st_size, 'sldSz': [sw, sh],
            'sha256': dk.hashlib.sha256(out.read_bytes()).hexdigest()}
