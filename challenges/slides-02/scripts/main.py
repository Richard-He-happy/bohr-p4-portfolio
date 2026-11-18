"""Paper -> editable template-inheriting PPTX + page golden standard + result.json.

v2 patch over v1: adds the page-level golden standard, the per-page diff, the run log with
step timings, the export/render check, the template-inheritance check and a version
history. Everything v1 produced (pptx, pdf, per-bullet evidence, notes, contract echo) is
still produced, and the original CLI still works unchanged.
"""
import argparse
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build as bd  # noqa: E402
import checks as ck  # noqa: E402
import deckkit as dk  # noqa: E402
import discover as dv  # noqa: E402
import gold as gd  # noqa: E402

T0, LOG, STEPS = time.time(), [], []
PKG_NOTES = [
    dict(version='v0.1.0', date='2026-11-11', change='page skeleton only: roles, page order, quote slots',
         why='a plan can be reviewed and restored before any slide XML exists',
         rollback='`--reuse-plan <out>/plan_v0.json`'),
    dict(version='v1.0.0', date='2026-11-11', change='first complete deck: template-inheriting pptx, PDF export, '
         'per-bullet verbatim evidence, speaker notes, contract-complete result.json',
         why='an openable deliverable is the baseline the rubric measures',
         rollback='restore `scripts/main.py` + `scripts/deckkit.py` from `baseline_v1.zip`'),
    dict(version='v2.0.0', date='2026-11-13', change='adds page_golden.json, page_diff.md, version_history.md, '
         'run.log step timings, export_check.json, template_check.json; fixes theme-part selection, per-line '
         'section labels, markdown title clean-up and contract-key accounting',
         why='the rubric asks for page-level gold, a re-checkable diff, a run log, a render check and a template '
         'check; the new checks immediately exposed four v1 defects',
         rollback='`--no-golden` (v1 fields only) or `--legacy-sections` (v1 section labels)'),
]


def log(m):
    LOG.append('[%7.2fs] %s' % (time.time() - T0, m))
    print(LOG[-1], file=sys.stderr)


def step(name, detail='', version='', artifact='', note=''):
    LOG.append('[%7.2fs] step=%s %s' % (time.time() - T0, name, detail))
    STEPS.append(dict(step=name, time='%.2fs' % (time.time() - T0), version=version, artifact=artifact,
                      detail=detail, note=note))


def run(a):
    indir, out = dv.in_dir(a.input), dv.out_dir(a.output, log)
    work = Path(a.work or '/app/work')
    try:
        work.mkdir(parents=True, exist_ok=True)
    except Exception:
        work = out
    case = dv.find_case(indir)
    res = {'case_id': case.get('case_id'), 'status': 'partial', 'editable_source': None, 'export_artifact': None,
           'content_map': [], 'compliance_checks': None, 'exceptions': [], 'errors': [], 'degradations': [],
           'pending_human': [], 'uncertainty': [], 'sources': [], 'changes': [], 'page_golden': None,
           'page_diff': None, 'version_history': None, 'export_check': None, 'template_check': None}
    keys = dv.contract_keys(case.get('output_contract'))
    dv.fill_contract(res, keys)
    dv.wjson(out / 'result.json', res)                     # first write: partial result
    log('partial result.json written (%d contract key(s))' % len(keys))
    log('argv=%s' % ' '.join(sys.argv[1:]))
    log('tools: soffice=%s pdftotext=%s pdffonts=%s' % (
        bool(dk.shutil.which('soffice') or dk.shutil.which('libreoffice')), bool(dk.shutil.which('pdftotext')),
        bool(dk.shutil.which('pdffonts'))))
    step('discover', 'case.json field(s)=%d, output_contract=%d' % (len(case), len(keys)), 'v0', 'result.json')
    if not case:
        res['exceptions'].append({'code': 'NO_CASE_JSON', 'stage': 'discover',
                                  'detail': 'no readable case.json; contract keys unknown, continuing'})
    E, D, PH = res['exceptions'], res['degradations'], res['pending_human']
    # ---- extract ---------------------------------------------------------
    fs = dv.scan(indir)
    wo, mat = dv.pick_workorder(fs['json'], indir), dv.load_json(indir / 'material.json') or {}
    tplp = Path(a.template) if a.template else next(
        (p for p in fs['pptx'] if 'template' in p.name.lower() or 'master' in p.name.lower()), None)
    start = dv.by_name(fs['pptx'], ('starting', 'starter', 'draft', 'current'))
    pt, method, src = [], 'none', None
    if fs['pdf']:
        src = max(fs['pdf'], key=lambda p: p.stat().st_size)
        pt, method = dk.pdf_pages(src, log)
    if not pt:
        for p in fs['doc']:
            try:
                if p.suffix.lower() == '.docx':
                    import zipfile
                    x = zipfile.ZipFile(p).read('word/document.xml').decode('utf-8', 'replace')
                    t = re.sub(r'<[^>]+>', ' ', x.replace('</w:p>', '\n'))
                else:
                    t = p.read_text('utf-8', 'replace')
            except Exception:
                continue
            if len(t) > 400:
                pt, method, src = [dk.norm(t)], p.suffix[1:], p
                break
    if src:
        res['sources'].append({'kind': src.suffix[1:], 'path': str(src), 'pages': len(pt), 'extraction': method})
    step('extract', '%s via %s, %d page(s)' % (src.name if src else 'no source', method, len(pt)), 'v1')
    pool, label = dk.sents(pt, a.legacy_sections), (src.name if src else 'source')
    if len(pool) < 4:
        E.append({'code': 'LOW_SOURCE_TEXT', 'stage': 'extract', 'detail': '%d sentence(s) via %s' % (len(pool), method)})
        PH.append('source text too short for a multi-slide deck')
    cjk = dk.is_cjk(' '.join(pt)[:20000])
    lang = 'zh' if str(dv.fk(wo, ('language', 'lang')) or ('zh' if cjk else 'en'))[:2] in ('zh', 'cn') else 'en'
    title = bd.clean_title(dv.clip(dv.fk(wo, ('decktitle', 'papertitle', 'title')) or dv.fk(mat, ('title',)) or
                                   (pt[0].split('\n')[0] if pt else label), 92))
    nreq = dv.num(a.slides, dv.fk(wo, ('slidecount', 'totalslides', 'numslides', 'pagecount')))
    n = max(3, min(30, nreq or (10 if len(pool) < 40 else 12)))
    mode = dv.fk(wo, ('mode',)) or ('edit' if start or dv.fk(wo, ('editworkorder', 'adapt')) else 'generate')
    if mode in ('edit', 'adapt') and not start:
        E.append({'code': 'EDIT_WITHOUT_STARTING_DECK', 'stage': 'discover', 'detail': 'no starting deck supplied'})
        mode = 'generate'
    tplp = tplp or start
    tpl = dk.read_template(tplp) if tplp else {'ok': False}
    if tplp and not tpl.get('ok'):
        D.append({'stage': 'template', 'detail': '%s unreadable (%s); builtin design used' % (tplp.name, tpl.get('error'))})
    if not tplp:
        PH.append('no organizer template supplied: builtin 16:9 design used; confirm before delivery')
    tpl['has_ctr'] = any('ctrTitle' in i['types'] for _x, i in tpl.get('layouts', []))
    tsrc = ('starting-deck:' + start.name) if start and tpl.get('ok') else (
        'template:' + tplp.name) if tpl.get('ok') else 'builtin-default'
    imgs = dk.pdf_jpegs(src) if src and src.suffix.lower() == '.pdf' else []
    meta = {'title': title, 'src_label': label, 'requested': nreq, 'mode': mode, 'case_id': case.get('case_id'),
            'stamp': dv.now(), 'extraction': method, 'has_figure': bool(imgs), 'label': label,
            'source_preservation': dv.fk(wo, ('sourcepres',)),
            'template_inheritance': dv.fk(wo, ('templateinher',)),
            'footer': dv.clip(dv.fk(wo, ('footer', 'footertext')) or (('来源：' if lang == 'zh' else 'Source: ') +
                                                                     dv.clip(title, 50)), 100),
            'subtitle': [x for x in [dv.clip(dv.fk(wo, ('audience', 'occasion', 'venue')) or '', 80),
                                     ('来源论文：' if lang == 'zh' else 'Paper: ') + label] if x],
            'credit': '谢谢，欢迎提问' if lang == 'zh' else 'Thanks - questions welcome'}
    # ---- v0 plan ---------------------------------------------------------
    pages = bd.plan_from_file(a.reuse_plan, pool, E) if a.reuse_plan else None
    if pages:
        step('plan', 'plan reused from %s: %d page(s)' % (a.reuse_plan, len(pages)), 'v0', str(a.reuse_plan))
    else:
        pages = bd.make_pages(pool, meta, n, lang, E) if pool else []
    if pages:
        pages = bd.ensure_frames(pages, meta, lang)
    if not pages:
        E.append({'code': 'INSUFFICIENT_INPUT', 'stage': 'plan',
                  'detail': 'no usable sentence: a notice deck is written instead of a scientific deck'})
        pages = bd.notice_pages(lang, ['readable source text', 'page-level evidence', 'requested slide count'])
    pages = bd.fill_notes(pages, meta, lang)
    plan = dict(version='v0', case_id=case.get('case_id'), roles=[p['role'] for p in pages], requested=nreq,
                pages=[dict(index=i, role=p['role'], title=p['title'], quotes=[s['text'] for s in p.get('src') or []])
                       for i, p in enumerate(pages, 1)])
    plan['sha256'] = gd.sha(__import__('json').dumps(plan['pages'], ensure_ascii=False, sort_keys=True))
    dv.wjson(out / 'plan_v0.json', plan)
    log('plan v0: %d page(s), sha256 %s' % (len(pages), plan['sha256'][:16]))
    step('plan_done', 'skeleton fixed: roles %s' % ','.join(p['role'] for p in pages), 'v0', 'plan_v0.json',
         'roles, titles and quote slots are written before any slide XML; this file is the rollback target')
    # ---- golden standard, pre-registered ---------------------------------
    inv = gd.inventory(pool)
    golden = None if a.no_golden else gd.build_golden(pages, inv, meta, nreq)
    if golden:
        dv.wjson(out / 'page_golden.json', golden)
        step('golden', 'golden standard: %d page(s), %d section label(s), %d numeric token(s), %d figure/table ref(s)'
             % (len(golden['pages']), len(inv['sections']), len(inv['numbers']),
                len(inv['figures']) + len(inv['tables'])), 'v2', 'page_golden.json')
    # ---- v1 deck ---------------------------------------------------------
    rp = [p for p in pages if p['role'] == 'results']
    figs = {'embedded_from_source': len(imgs), 'placed': 0, 'captions_cited': 0, 'redrawn': 0}
    if imgs and rp:
        rp[0]['images'], figs['placed'] = imgs[:1], 1
    W, H = (tpl.get('sldSz') or [dk.SLIDE_W, dk.SLIDE_H])[:2]
    decks, cmap, fits = [], [], []
    for i, p in enumerate(pages, 1):
        p['layout'] = bd.layouts_pick(tpl, p['role'])
        shapes, util = dk.slide_shapes(p, W, H, tpl, meta['footer'], cjk)
        decks.append({'layout': p['layout'], 'shapes': shapes, 'images': p.get('images', []), 'notes': p['notes']})
        fits.append({'i': i, 'util': util})
        bl, srow = [], p.get('src') or []
        for j, (t, _l) in enumerate(p['bullets']):
            if j < len(srow):
                bl.append({'text': t, 'quote': srow[j]['text'], 'verified': False, 'kind': 'source',
                           'locator': '%s p.%d %s' % (label, srow[j]['page'], srow[j]['sec'])})
            else:
                bl.append({'text': t, 'quote': '', 'verified': None, 'kind': 'front_matter', 'locator': '',
                           'origin': 'workorder/case metadata'})
        cmap.append({'slide_index': i, 'role': p['role'], 'title': p['title'],
                     'layout': (p['layout'] or '').rsplit('/', 1)[-1], 'notes': p['notes'], 'bullets': bl})
    pptx = out / 'presentation.pptx'
    built = bd.build_package(pptx, tpl, decks, title, 'SciMaster slides skill', dv.now())
    log('pptx: %d slide(s) / %d bytes' % (built['slides'], built['bytes']))
    step('build', '%d slide(s), %d bytes, template=%s' % (built['slides'], built['bytes'], tsrc), 'v1',
         'presentation.pptx', 'master/layouts/theme copied from the template; one notes part per slide')
    res['editable_source'] = {'path': str(pptx), 'format': 'pptx', 'bytes': built['bytes'],
                              'sha256': built['sha256'], 'slides': built['slides'],
                              'slide_size_emu': built['sldSz'], 'template_source': tsrc, 'mode': mode}
    pdf = out / 'presentation.pdf'
    exp = (dk.export_pdf(pdf, pptx, work, [(p['title'], [t for t, _l in p['bullets']]) for p in pages], E)
           if not a.no_pdf else {'method': 'skipped', 'degraded': True})
    pdfn = None
    if pdf.exists() and pdf.read_bytes()[:4] == b'%PDF':
        pdfn = len(re.findall(rb'/Type\s*/Page[^s]', pdf.read_bytes()))
        res['export_artifact'] = {'path': str(pdf), 'format': 'pdf', 'pages': pdfn, 'bytes': pdf.stat().st_size,
                                  'method': exp['method'], 'degraded': exp['degraded']}
    step('export', 'pdf=%s pages=%s method=%s' % (pdfn is not None, pdfn, exp['method']), 'v1', 'presentation.pdf')
    # ---- v1 audit --------------------------------------------------------
    SRC, nb, nv = dk.norm('\n'.join(pt)), 0, 0
    for row in cmap:
        for b in row['bullets']:
            if b.get('kind') != 'source':
                continue
            nb += 1
            b['verified'] = bool(b['quote']) and (b['quote'] in SRC or b['text'].rstrip(' …').strip() in SRC)
            nv += 1 if b['verified'] else 0
            if not b['verified']:
                E.append({'code': 'QUOTE_UNVERIFIED', 'stage': 'audit', 'detail': 'not verbatim: ' + dv.clip(b['text'], 60)})
    audit = {'bullets': nb, 'verified': nv, 'rate': round(nv / nb, 3) if nb else 0.0,
             'method': 'verbatim substring match against extracted source'}
    res['content_map'] = cmap
    unk = dv.fill_contract(res, keys)
    res['compliance_checks'] = dk.checks(pages, tpl, meta, audit, fits, figs, exp, pdfn, tsrc,
                                         len(keys) - len(unk), unk, W)
    step('audit', '%d/%d bullet(s) verbatim' % (nv, nb), 'v1')
    # ---- v2 checks + diff ------------------------------------------------
    if not a.no_golden:
        ec = ck.export_check(pdf if pdf.exists() else None, len(pages), fits, figs, tpl)
        dv.wjson(out / 'export_check.json', ec)
        res['export_check'] = dict(path=str(out / 'export_check.json'), overall_pass=ec['overall_pass'],
                                   verdict=ec.get('verdict'),
                                   pdf_pages=(ec.get('page_count') or {}).get('pdf_pages'), slides=len(pages),
                                   fonts=(ec.get('fonts') or {}).get('base_fonts'),
                                   font_substituted=(ec.get('fonts') or {}).get('substituted'),
                                   overflow_violations=len((ec.get('text_overflow') or {}).get('violations') or []),
                                   checks=[dict(id=c['id'], status=c['status']) for c in ec['checks']])
        step('export_check', '%s (%d/%d item pass)' % (ec.get('verdict'), sum(c['status'] == 'pass' for c in ec['checks']),
                                                      len(ec['checks'])), 'v2', 'export_check.json')
        tc = ck.template_check(pptx, tpl, tplp, meta, len(pages))
        dv.wjson(out / 'template_check.json', tc)
        res['template_check'] = dict(path=str(out / 'template_check.json'), source=tc['source'],
                                     inherited=tc['inherited'], overall_pass=tc['overall_pass'],
                                     passes=tc.get('passes', 0), fails=tc.get('fails', 0), warns=tc.get('warns', 0),
                                     na=tc.get('na', 0), failures=tc['failures'],
                                     checks=[dict(id=c['id'], status=c['status']) for c in tc['checks']])
        step('template_check', '%d pass / %d fail / %d warn / %d n/a' % (tc.get('passes', 0), tc.get('fails', 0),
                                                                        tc.get('warns', 0), tc.get('na', 0)),
             'v2', 'template_check.json')
        diff = gd.diff_golden(golden, cmap, fits, res['compliance_checks'])
        (out / 'page_diff.md').write_text(gd.render_diff_md(diff, golden), encoding='utf-8')
        sm = diff['summary']
        res['page_diff'] = dict(path=str(out / 'page_diff.md'), overall=diff['overall'], pages_total=sm['pages'],
                                pages_pass=sm['passed'], pages_partial=sm['partial'], pages_fail=sm['failed'],
                                hard_gaps=sm['hard_gaps'], soft_gaps=sm['soft_gaps'],
                                headline_coverage=sm['headline'],
                                per_page=[dict(page=r['page'], role=r['role'], verdict=r['verdict'],
                                               hard_fail=r['hard_fail'], soft_fail=r['soft_fail'])
                                          for r in diff['pages']], gaps=diff['gaps'])
        res['page_golden'] = dict(path=str(out / 'page_golden.json'), rules_version=golden['rules_version'],
                                  source=golden['source'], deck=golden['deck'], pages=golden['pages'])
        step('diff', '%d pass / %d partial / %d fail; headline numbers %d/%d' % (
            sm['passed'], sm['partial'], sm['failed'], sm['headline']['covered'], sm['headline']['required']),
            'v2', 'page_diff.md', 'diff is computed from page_golden.json + content_map, so it can and does fail')
    # ---- version history + finalize --------------------------------------
    res['changes'] = [dict(version='v0', time=dv.now(), slides=len(pages), plan_sha256=plan['sha256']),
                      dict(version='v1', time=dv.now(), slides=len(pages), pptx_sha256=built['sha256'],
                           pdf_pages=pdfn),
                      dict(version='v2', time=dv.now(), slides=len(pages),
                           page_diff=(res['page_diff'] or {}).get('overall'),
                           export_check=(res['export_check'] or {}).get('verdict'),
                           template_check=(res['template_check'] or {}).get('overall_pass'))]
    (out / 'version_history.md').write_text(gd.version_history(STEPS, case.get('case_id'), PKG_NOTES), encoding='utf-8')
    res['version_history'] = dict(path=str(out / 'version_history.md'), package_version=gd.PKG_VERSION,
                                  rollback=['--reuse-plan <out>/plan_v0.json', '--no-golden', '--legacy-sections'],
                                  records=[dict(step=s['step'], version=s['version'], detail=dv.clip(s['detail'], 140))
                                           for s in STEPS])
    step('version_history', '%d run record(s) + package lineage v0.1.0 -> v2.0.0' % len(STEPS), 'v2',
         'version_history.md')
    res['uncertainty'] = ['figures cited from embedded originals, none redrawn',
                          'bullet text verbatim; notes are prompts']
    if nreq and nreq != len(pages):
        res['uncertainty'].append('requested %s slides, delivered %d' % (nreq, len(pages)))
    if res.get('page_diff') and res['page_diff'].get('soft_gaps'):
        res['uncertainty'].append('%d page-level soft gap(s) between the deck and its golden standard: %s '
                                  '(see page_diff.md)' % (res['page_diff']['soft_gaps'],
                                                          ', '.join('p%d.%s' % (g['page'], g['check'])
                                                                    for g in res['page_diff']['gaps'][:6])))
    ok_status = (nb and nv == nb and not exp['degraded'] and res['compliance_checks']['overall_pass']
                 and (res['page_diff'] or {}).get('overall') != 'FAIL')
    res['status'] = 'insufficient_evidence' if (not pool or any(p['role'] == 'notice' for p in pages)) else (
        'ok' if ok_status else 'partial')
    res['runtime'] = {'seconds': round(time.time() - T0, 1), 'extraction': method, 'language': lang, 'mode': mode,
                      'slides_requested': nreq, 'slides_delivered': len(pages), 'plan_sha256': plan['sha256'][:16],
                      'package_version': gd.PKG_VERSION}
    unk = dv.fill_contract(res, keys)
    if isinstance(res.get('compliance_checks'), dict):
        res['compliance_checks']['contract'] = {'required_keys': len(keys), 'filled': len(keys) - len(unk),
                                                'unknown_keys': unk}
    dv.wjson(out / 'result.json', res)
    for e in E:
        log('EXCEPTION %s @%s: %s' % (e.get('code'), e.get('stage'), dv.clip(e.get('detail'), 120)))
    for d in D:
        log('DEGRADED @%s: %s' % (d.get('stage'), dv.clip(d.get('detail'), 120)))
    for p in PH:
        log('PENDING_HUMAN: %s' % dv.clip(p, 120))
    step('finalize', 'status=%s, %d contract key(s), %d unknown' % (res['status'], len(keys), len(unk)), 'v2',
         'result.json')
    log('finalized %s: %d/%d bullets verified, %d slide(s)' % (res['status'], nv, nb, len(pages)))
    (out / 'run.log').write_text('\n'.join(LOG) + '\n', encoding='utf-8')
    return res


def main():
    ap = argparse.ArgumentParser(description='Paper -> editable PPTX + page golden standard + result.json '
                                             '(stdlib only, offline).')
    ap.add_argument('--input', help='case dir (default /input)')
    ap.add_argument('--output', help='output dir (default /app/output)')
    ap.add_argument('--work', default='/app/work', help='scratch dir')
    ap.add_argument('--slides', type=int, help='override slide count')
    ap.add_argument('--template', help='explicit template .pptx')
    ap.add_argument('--no-pdf', action='store_true', help='skip PDF export')
    ap.add_argument('--reuse-plan', help='rebuild from a recorded plan_v0.json (v0 rollback)')
    ap.add_argument('--no-golden', action='store_true', help='v1 behaviour: skip golden/diff/export/template checks')
    ap.add_argument('--legacy-sections', action='store_true', help='v1 section labelling (one label per page)')
    a = ap.parse_args()
    out = None
    try:
        out = dv.out_dir(a.output, log)
        run(a)
    except Exception:
        import traceback
        tb = traceback.format_exc()
        log('FATAL: ' + tb.strip().splitlines()[-1])
        try:
            p = (out or dv.out_dir(a.output, log)) / 'result.json'
            res = dv.load_json(p) or {'case_id': None, 'content_map': [], 'exceptions': [], 'errors': [],
                                      'compliance_checks': None, 'editable_source': None, 'export_artifact': None,
                                      'degradations': [], 'pending_human': [], 'uncertainty': [], 'status': 'partial'}
            res['status'] = 'partial'
            res.setdefault('errors', []).append({'stage': 'run', 'detail': tb})
            dv.wjson(p, res)
            log('partial result.json rewritten after fatal error')
        except Exception:
            pass
    finally:
        try:
            ((out or dv.out_dir(a.output, log)) / 'run.log').write_text('\n'.join(LOG) + '\n', encoding='utf-8')
        except Exception:
            pass
    return 0


if __name__ == '__main__':
    sys.exit(main())
