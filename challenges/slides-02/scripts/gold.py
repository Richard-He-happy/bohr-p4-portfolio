"""gold.py: page-level golden standard, page diff, version-history writer.

Every section, number and citation below is harvested from the extracted source text;
nothing is typed in from memory. The golden standard is built from the page plan
*before* the deck is written, so the diff compares a pre-registered expectation
against the deck that was actually delivered.
"""
import hashlib
import re

RULES_VERSION = 'goldenv1'
PKG_VERSION = '2.0.0'
SECS = ('abstract', 'intro', 'related', 'methods', 'results', 'discussion', 'conclusion', 'limits', 'body')

# role -> narrative job, source sections it must draw from, allowed bullet count,
# minimum verbatim numbers, figure/reference expectation
ROLE_SPEC = {
    'title': dict(job='paper identity + audience framing', secs=[], rng=(1, 3), nums=0, fig='n/a',
                  claim='title verbatim from the source title line; subtitle carries audience and source'),
    'notice': dict(job='input incomplete: name what is missing', secs=[], rng=(1, 4), nums=0, fig='n/a',
                   claim='a notice page makes no scientific claim'),
    'outline': dict(job='navigation only, no data', secs=[], rng=(3, 12), nums=0, fig='n/a',
                    claim='one line per section that actually follows'),
    'background': dict(job='why the problem matters', secs=['abstract', 'intro', 'related'], rng=(1, 4),
                       nums=0, fig='optional', claim='state the gap with a source sentence, no invented context'),
    'question': dict(job='the single question answered', secs=['abstract', 'intro'], rng=(1, 3), nums=0,
                     fig='n/a', claim='phrase the studied question, not the result'),
    'methods': dict(job='design, data, analysis window', secs=['methods'], rng=(1, 4), nums=1,
                    fig='optional', claim='report design and measurement, numbers verbatim'),
    'results': dict(job='one measured claim per page, with its number', secs=['results', 'abstract'],
                    rng=(1, 4), nums=1, fig='required_if_available',
                    claim='each results page carries at least one verbatim number'),
    'discussion': dict(job='what the results mean', secs=['discussion', 'results'], rng=(1, 4), nums=0,
                       fig='optional', claim='interpretation must be attributed, not asserted'),
    'limitations': dict(job='scope and boundary', secs=['limits', 'discussion'], rng=(1, 4), nums=0,
                        fig='n/a', claim='name the boundary the source itself names'),
    'conclusion': dict(job='what to remember', secs=['conclusion', 'abstract'], rng=(1, 4), nums=1,
                       fig='n/a', claim='take-away restates measured effects, adds no new number'),
    'thanks': dict(job='close', secs=[], rng=(0, 2), nums=0, fig='n/a', claim='fixed credit line'),
}

NUMPATS = [
    ('pvalue', r'p\s*[<>=]\s*0?\.\d+', 3.0),
    ('ci', r'95\s*%\s*CI\s*[\d.]+\s*to\s*[\d.]+', 3.0),
    ('percent', r'\d+(?:\.\d+)?\s*(?:%|percent)', 3.0),
    ('temperature', r'\d+(?:\.\d+)?\s*degrees?\s*Celsius', 2.0),
    ('quantity', r'\d+(?:\.\d+)?\s*(?:kilowatt hours?|weeks?|days?|months?|years?|buildings?|'
                 r'dwellings?|participants?|samples?|sites?)', 1.5),
    ('decimal', r'(?<![\d.])\d+\.\d+(?![\d.])', 1.0),
]
FIG_RE = re.compile(r'\b(?:fig(?:ure)?s?\.?)\s*(\d+)|\b图\s*(\d+)', re.I)
TAB_RE = re.compile(r'\b(?:table)s?\s*(\d+)|\b表\s*(\d+)', re.I)


def sha(b):
    if isinstance(b, str):
        b = b.encode('utf-8')
    return hashlib.sha256(b or b'').hexdigest()


def clip(s, n=160):
    s = re.sub(r'\s+', ' ', str(s or '')).strip()
    return s if len(s) <= n else s[:n - 1].rstrip() + '…'


def inventory(pool):
    """Harvest numbers and figure/table citations from the extracted sentences."""
    nums, figs, tabs, secs = {}, {}, {}, {}
    for i, s in enumerate(pool):
        sec = s.get('sec') or 'body'
        secs[sec] = secs.get(sec, 0) + 1
        for kind, pat, w in NUMPATS:
            for m in re.finditer(pat, s['text'], re.I):
                tok = m.group(0).strip()
                if len(tok) < 2:
                    continue
                key = (tok.lower(), sec)
                if key not in nums or w > nums[key]['weight']:
                    nums[key] = dict(token=tok, kind=kind, sec=sec, page=s.get('page'), weight=w,
                                     sentence=clip(s['text'], 110), order=i)
        for m in FIG_RE.finditer(s['text']):
            figs.setdefault(int(m.group(1) or m.group(2)),
                            dict(n=int(m.group(1) or m.group(2)), sec=sec, page=s.get('page')))
        for m in TAB_RE.finditer(s['text']):
            tabs.setdefault(int(m.group(1) or m.group(2)),
                            dict(n=int(m.group(1) or m.group(2)), sec=sec, page=s.get('page')))
    return dict(numbers=sorted(nums.values(), key=lambda r: (-r['weight'], r['order'])),
                figures=sorted(figs.values(), key=lambda r: r['n']),
                tables=sorted(tabs.values(), key=lambda r: r['n']),
                sections=dict(sorted((k, v) for k, v in secs.items() if k in SECS)),
                sentences=len(pool), fingerprint=sha('\n'.join(s['text'] for s in pool)))


def _loc(meta, rec):
    return '%s p.%s %s' % (meta.get('label'), rec.get('page'), rec.get('sec'))


def build_golden(pages, inv, meta, requested=None):
    """Pre-register, per planned page, the sections/numbers/citations it must carry."""
    present = set(inv['sections'])
    out, cited = [], {}
    for i, p in enumerate(pages, 1):
        role = p['role']
        spec = ROLE_SPEC.get(role) or ROLE_SPEC['background']
        declared = list(spec['secs'])
        exp = [s for s in declared if s in present]
        collapsed = bool(declared) and len(present) <= 1
        req, seen = [], set()
        for n in ([x for x in inv['numbers'] if x['sec'] in exp] if exp else []):
            if n['token'].lower() in seen:
                continue
            seen.add(n['token'].lower())
            req.append(dict(token=n['token'], kind=n['kind'], locator=_loc(meta, n)))
            if len(req) >= 3:
                break
        prim = exp[:1]     # the role's primary section owns the citation duty ...
        duty = prim[0] if prim else ''
        if duty in cited:  # ... but each figure/table is owed by one page only
            cites, duty = [], 'covered_by_page_%d' % cited[duty]
        else:
            cites = [dict(kind='figure', n=f['n'], locator=_loc(meta, f))
                     for f in inv['figures'] if f['sec'] in prim][:2]
            cites += [dict(kind='table', n=t['n'], locator=_loc(meta, t))
                      for t in inv['tables'] if t['sec'] in prim][:2]
            if cites:
                cited[duty] = i
        fig = spec['fig']
        if fig == 'required_if_available':
            fig = 'required' if meta.get('has_figure') else 'not_available_in_source'
        out.append(dict(page=i, role=role, title=clip(p['title'], 110), narrative_job=spec['job'],
                        expected_sections=exp or ['<none: role has no section contract>'],
                        declared_sections=declared, section_contract_available=bool(exp),
                        labels_collapsed=collapsed, bullet_range=list(spec['rng']), numbers_required=req,
                        min_numbers=(spec['nums'] if exp else 0), citations_required=cites,
                        figure_placement=fig, citation_duty=(duty or 'none'),
                        claim_expectation=spec['claim'],
                        planned_quotes=[clip(s['text'], 90) for s in (p.get('src') or [])]))
    heads = [n for n in inv['numbers'] if n['sec'] in ('abstract', 'conclusion')][:6]
    deck = dict(headline_numbers=[dict(token=n['token'], kind=n['kind'], locator=_loc(meta, n)) for n in heads],
                figure_numbers=[f['n'] for f in inv['figures']], table_numbers=[t['n'] for t in inv['tables']],
                sections_available=inv['sections'], pages=len(pages), requested=requested,
                roles=[p['role'] for p in pages], extraction=meta.get('extraction'),
                figure_in_source=bool(meta.get('has_figure')))
    return dict(rules_version=RULES_VERSION, generated_at=meta.get('stamp'), case_id=meta.get('case_id'),
                source=dict(label=meta.get('label'), fingerprint=inv['fingerprint'], sentences=inv['sentences']),
                deck=deck, pages=out)


def _sec_of(loc):
    t = str(loc or '').split()
    return t[-1] if t and t[-1] in SECS else ('unknown' if loc else '')


HARD = ('role', 'bullets', 'evidence', 'overflow')


def diff_golden(golden, cmap, fits, checks):
    rows, gaps = [], []
    util = {f['i']: f['util'] for f in fits}
    for g, c in zip(golden['pages'], cmap):
        text = ' '.join([b.get('text') or '' for b in c['bullets']] +
                        [b.get('quote') or '' for b in c['bullets']])
        low = text.lower()
        body = [b for b in c['bullets'] if b.get('kind') != 'front_matter']
        secs = sorted({_sec_of(b.get('locator')) for b in body if b.get('locator')})
        exp = [s for s in g['expected_sections'] if s in SECS]
        ch = {'role': dict(ok=c['role'] == g['role'], expected=g['role'], actual=c['role'],
                           evidence='content_map[%d].role' % (g['page'] - 1))}
        if not exp and g.get('labels_collapsed'):
            ch['sections'] = dict(ok=False, na=False, expected=g.get('declared_sections'), actual=secs,
                                  evidence='expected %s, but extraction exposed only %d section label(s) (%s): the '
                                           'page cannot be shown to draw from its declared section' % (
                                               g.get('declared_sections'),
                                               len(golden['deck']['sections_available']),
                                               ','.join(golden['deck']['sections_available']) or 'none'))
        elif not exp:
            ch['sections'] = dict(ok=True, na=True, expected=g['expected_sections'], actual=secs,
                                  evidence='role has no section contract here; source sections: %s' %
                                           (','.join(golden['deck']['sections_available']) or 'none'))
        else:
            hit = [s for s in exp if s in secs]
            ch['sections'] = dict(ok=bool(hit), na=False, expected=exp, actual=secs, hit=hit,
                                  evidence='locators of %d body bullet(s) resolve to %s' % (len(body), secs))
        req = g['numbers_required']
        cov = [n['token'] for n in req if n['token'].lower() in low]
        ch['numbers'] = dict(ok=(len(cov) >= g['min_numbers']), na=(not req),
                             expected=[n['token'] for n in req], actual=cov,
                             missing=[n['token'] for n in req if n['token'].lower() not in low],
                             need=g['min_numbers'],
                             evidence=('page text carries %d/%d expected numeric token(s), need %d' %
                                       (len(cov), len(req), g['min_numbers'])) if req else
                                      'no numeric token in this role section contract of this source')
        creq = g['citations_required']
        if not creq:
            ch['citations'] = dict(ok=True, na=True, expected=[], actual=[],
                                   evidence='no figure/table number inside this role section contract')
        else:
            got = ['%s %d' % (k['kind'], k['n']) for k in creq
                   if any(int(m.group(1) or m.group(2)) == k['n']
                          for m in (FIG_RE if k['kind'] == 'figure' else TAB_RE).finditer(text))]
            ch['citations'] = dict(ok=len(got) == len(creq), na=False,
                                   expected=['%s %d' % (k['kind'], k['n']) for k in creq], actual=got,
                                   evidence='page text cites %s' % (got or 'no figure/table number'))
        lo, hi = g['bullet_range']
        nb = len(c['bullets'])
        ch['bullets'] = dict(ok=(lo <= nb <= hi), expected=[lo, hi], actual=nb,
                             evidence='%d bullet/subtitle line(s) recorded, allowed %d-%d' % (nb, lo, hi))
        src = [b for b in body if b.get('quote')]
        if not src:
            ch['evidence'] = dict(ok=True, na=True, expected='verbatim when a quote exists', actual=[],
                                  evidence='page carries no source quote (front matter only)')
        else:
            bad = [clip(b['text'], 50) for b in src if not b.get('verified')]
            ch['evidence'] = dict(ok=not bad, na=False, expected='all quotes verbatim',
                                  actual='%d/%d' % (len(src) - len(bad), len(src)),
                                  evidence=('unverified: %s' % '; '.join(bad[:3])) if bad else
                                           'every quote occurs as a substring of the extracted source')
        u = util.get(g['page'], 0.0)
        ch['overflow'] = dict(ok=(u <= 1.0), expected='<=1.0', actual=u,
                              evidence='line-fit model utilization %.2f (rendered check in export_check.json)' % u)
        hard = [k for k in ch if not ch[k]['ok'] and k in HARD]
        soft = [k for k in ch if not ch[k]['ok'] and k not in HARD]
        verdict = 'FAIL' if hard else ('PARTIAL' if soft else 'PASS')
        for k in hard + soft:
            gaps.append(dict(page=g['page'], role=g['role'], check=k,
                             severity='hard' if k in hard else 'soft', detail=ch[k].get('evidence')))
        rows.append(dict(page=g['page'], role=g['role'], title=c['title'], narrative_job=g['narrative_job'],
                         verdict=verdict, checks=ch, hard_fail=hard, soft_fail=soft))
    decktext = ' '.join([b.get('text') or '' for c in cmap for b in c['bullets']] +
                        [b.get('quote') or '' for c in cmap for b in c['bullets']]).lower()
    hn = golden['deck']['headline_numbers']
    cov = [n['token'] for n in hn if n['token'].lower() in decktext]
    fc = [('figure', n) for n in golden['deck']['figure_numbers']] + \
         [('table', n) for n in golden['deck']['table_numbers']]
    fgot = ['%s %d' % (k, n) for k, n in fc
            if any(int(m.group(1) or m.group(2)) == n
                   for m in (FIG_RE if k == 'figure' else TAB_RE).finditer(decktext))]
    summary = dict(pages=len(rows), passed=sum(r['verdict'] == 'PASS' for r in rows),
                   partial=sum(r['verdict'] == 'PARTIAL' for r in rows),
                   failed=sum(r['verdict'] == 'FAIL' for r in rows),
                   hard_gaps=sum(1 for g in gaps if g['severity'] == 'hard'),
                   soft_gaps=sum(1 for g in gaps if g['severity'] == 'soft'),
                   headline=dict(covered=len(cov), required=len(hn), tokens=[n['token'] for n in hn],
                                 missing=[n['token'] for n in hn if n['token'].lower() not in decktext],
                                 ok=len(cov) == len(hn) if hn else True),
                   citations=dict(covered=fgot, required=['%s %d' % (k, n) for k, n in fc],
                                  missing=['%s %d' % (k, n) for k, n in fc if '%s %d' % (k, n) not in fgot],
                                  ok=len(fgot) == len(fc)))
    return dict(rules_version=RULES_VERSION, case_id=golden.get('case_id'), pages=rows, gaps=gaps,
                summary=summary, export=dict(overall_pass=checks.get('export', {}).get('matches_slides'),
                                             method=checks.get('export', {}).get('method')),
                overall='PASS' if not gaps else ('FAIL' if summary['hard_gaps'] else 'PARTIAL'))


def render_diff_md(diff, golden):
    s, h = diff['summary'], diff['summary']['headline']
    L = ['# Page diff — delivered deck vs page-level golden standard', '']
    L.append('- case: `%s` · source: `%s` · rules: `%s`' % (diff.get('case_id'), golden['source']['label'],
                                                           RULES_VERSION))
    L.append('- source fingerprint (sha256 of the extracted sentence pool): `%s…`' % golden['source']['fingerprint'][:16])
    L.append('- golden written **before** the deck was built (`page_golden.json`); this diff compares it with '
             '`result.json.content_map`, so a page can and does fail.')
    L.append('- generated: %s · pages: %d (requested %s) · sources: %d sentence(s)' % (
        golden.get('generated_at'), s['pages'], golden['deck'].get('requested'), golden['source']['sentences']))
    L += ['', '## 1. Summary', '', '| metric | value |', '|-|-|']
    L.append('| pages PASS / PARTIAL / FAIL | %d / %d / %d |' % (s['passed'], s['partial'], s['failed']))
    L.append('| gaps (hard / soft) | %d / %d |' % (s['hard_gaps'], s['soft_gaps']))
    L.append('| headline numbers surfaced | %d/%d%s |' % (h['covered'], h['required'],
                                                          '' if h['ok'] else ' → missing ' + ', '.join(h['missing'])))
    ci = s['citations']
    L.append('| figure/table numbers cited in the deck | %d/%d%s |' % (len(ci['covered']), len(ci['required']),
                                                                       '' if ci['ok'] else ' → missing ' + ', '.join(ci['missing'])))
    L.append('| export rendered | %s |' % ('yes (%s)' % diff['export']['method'] if diff['export']['overall_pass']
                                           else 'no / degraded'))
    L.append('| overall | **%s** |' % diff['overall'])
    L += ['', '| # | role | title | verdict | hard gaps | soft gaps |', '|-|-|-|-|-|-|']
    for r in diff['pages']:
        L.append('| %d | %s | %s | %s | %s | %s |' % (r['page'], r['role'], clip(r['title'], 46), r['verdict'],
                                                      ', '.join(r['hard_fail']) or '-',
                                                      ', '.join(r['soft_fail']) or '-'))
    L += ['', '## 2. Per-page detail', '']
    for r in diff['pages']:
        L += ['### p%d · %s · %s — %s' % (r['page'], r['role'], clip(r['title'], 70), r['verdict']), '']
        L.append('| check | expected | actual | verdict | evidence |')
        L.append('|-|-|-|-|-|')
        for k in ('role', 'sections', 'numbers', 'citations', 'bullets', 'evidence', 'overflow'):
            c = r['checks'][k]
            vd = 'n/a' if c.get('na') else ('pass' if c['ok'] else 'fail')
            exp = c['expected']
            exp = ', '.join(str(x) for x in exp) if isinstance(exp, list) else str(exp)
            act = c['actual']
            act = ', '.join(str(x) for x in act) if isinstance(act, list) else str(act)
            L.append('| %s | %s | %s | %s | %s |' % (k, clip(exp, 70), clip(act, 70), vd, clip(c['evidence'], 110)))
        L.append('')
    L += ['## 3. Gap index (what the deck is missing)', '']
    if not diff['gaps']:
        L.append('No gap: every page satisfies its pre-registered expectation.')
    else:
        L += ['| # | page | role | check | severity | detail |', '|-|-|-|-|-|-|']
        for i, g in enumerate(diff['gaps'], 1):
            L.append('| %d | p%d | %s | %s | %s | %s |' % (i, g['page'], g['role'], g['check'], g['severity'],
                                                           clip(g['detail'], 120)))
    L += ['', '## 4. Reproduction', '', '```',
          'python3 scripts/main.py --input <case dir> --output <out dir>',
          'python3 scripts/main.py --input <case dir> --output <out dir> --reuse-plan <out>/plan_v0.json',
          '```', 'Timestamps are the only non-deterministic fields: the golden standard and this diff are '
          'deterministic in the source text plus the workorder.']
    return '\n'.join(L) + '\n'


def version_history(records, case_id, pkg_notes):
    L = ['# Version history — %s' % case_id, '']
    L.append('Two layers: the **package lineage** (what changed between skill versions, why, and how to roll '
             'back) and the **run record** (what this execution did, in order, with hashes).')
    L += ['', '## 1. Package lineage', '', '| version | date | change | why | rollback |', '|-|-|-|-|-|']
    for n in pkg_notes:
        L.append('| %s | %s | %s | %s | %s |' % (n['version'], n['date'], n['change'], n['why'], n['rollback']))
    L += ['', '## 2. Run record (this execution)', '', '| step | time | version | artifact | detail |',
          '|-|-|-|-|-|']
    for r in records:
        L.append('| %s | %s | %s | %s | %s |' % (r.get('step'), r.get('time'), r.get('version'),
                                                 r.get('artifact') or '-', clip(r.get('detail'), 150)))
    L += ['', '### v0 skeleton → v1 deck: what changed and why', '']
    for r in records:
        if r.get('note'):
            L.append('- **%s** · %s: %s' % (r.get('version'), r.get('step'), r['note']))
    L += ['', '## 3. How to roll back', '', '| target | command | effect |', '|-|-|-|']
    L.append('| v0 page skeleton | `--reuse-plan <out>/plan_v0.json` | rebuild the deck from the recorded plan '
             '(roles, titles, quote texts) instead of re-planning; the plan hash is printed in `run.log` |')
    L.append('| v1 behaviour | `--no-golden` | skip golden/diff/export/template checks; only v1 result fields and '
             'files are written |')
    L.append('| v1 section labels | `--legacy-sections` | restore the pre-v2 flat section detection (a one-page '
             'source labels every sentence with the last heading it saw) |')
    L.append('| v1 package files | restore `scripts/main.py` + `scripts/deckkit.py` from the parent '
             '`baseline_v1.zip`, delete `scripts/gold.py` and `scripts/checks.py` | byte-level rollback; v1 hashes '
             'are listed in `references/golden-and-checks.md` |')
    L += ['', 'Rollback never deletes a produced artifact: the flags only change what the current run writes, so an '
          'older `presentation.pptx` in the output directory survives unless the run rewrites it.']
    return '\n'.join(L) + '\n'
