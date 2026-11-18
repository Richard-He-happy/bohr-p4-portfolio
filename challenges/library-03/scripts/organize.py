#!/usr/bin/env python3
"""library-auto-organizer: inventory, classify, tag, rename, dedupe, version and stage a research file library (stdlib only)."""
import argparse, json, os, re, shutil, sys, time, zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify as X

T0, S, V = time.time(), X.S, X.V
REF = Path(__file__).resolve().parent.parent / 'references'
FBD = {'journal_article': '10_papers', 'preprint': '11_preprints', 'dataset': '20_datasets', 'scan': '30_scans',
       'note': '40_notes', 'code': '50_code', 'unknown': '00_inbox'}
FB = {'dirs': FBD, 'special': {'quarantine': '90_quarantine', 'duplicates': '91_duplicates', 'superseded': '92_superseded'},
      'naming': {'template': '{year}-{author}-{title}-{doctype}', 'max_length': 150, 'title_chars': 70,
                 'missing': {'year': 'nd', 'author': 'anon', 'title': 'untitled'}}, 'limits': {}, 'vocab': [], 'aliases': []}
PUB = ('journal_article', 'conference_paper', 'thesis')


def sniff(p, h):
    for pre, k in ((b'%PDF', 'pdf'), (b'\xff\xd8\xff', 'jpeg'), (b'\x89PNG', 'png')):
        if h.startswith(pre):
            return k, 'application/pdf' if k == 'pdf' else 'image/' + k
    if h[:2] == b'PK':
        try:
            n = '|'.join(zipfile.ZipFile(p).namelist())
        except Exception:
            return 'zip', 'application/zip'
        k = 'docx' if 'word/' in n else 'xlsx' if 'xl/' in n else 'pptx' if 'ppt/' in n else 'zip'
        return k, 'application/' + k
    try:
        h[:2048].decode('utf-8')
        return 'text', 'text/plain'
    except UnicodeDecodeError:
        return (p.suffix.lower().lstrip('.') or 'unknown'), 'application/octet-stream'


class R:
    def __init__(s, a):
        s.a, s.i, s.o = a, Path(a.input).resolve(), Path(a.output).resolve()
        s.L, s.T, s.st, s.U = s.o / 'library', [], 'partial', json.loads(json.dumps(FB))
        s.E, s.G, s.PH, s.FL, s.OP, s.ME = [], [], [], [], [], []
        s.rec, s.case, s.ct, s.ck, s.wo, s.files, s.df, s.bs, s.PT, s.ZM = [], {}, None, None, [], [], [], False, [], {}
        s.DD = {'exact': [], 'chains': [], 'dupfiles': 0, 'method': 'sha256 for duplicates; doi > arxiv_id > title+author+year for versions; nothing deleted'}

    def ad(s, b, k, d, w=None):
        b.append({'kind': k, 'detail': d, 'where': w})


    def mats(s):
        return [r for r in s.rec if r['role'] == 'material']

    def rules(s):
        try:
            u = json.loads((REF / 'rules.json').read_text('utf-8'))
            [u[k] for k in ('naming', 'dirs', 'special', 'taxonomy')]
            u.setdefault('vocab', []), u.setdefault('aliases', [])
            s.U, s.T, s.PT, s.ZM = dict(FB, **u), u['taxonomy'], u.get('patterns') or [], u.get('doc_types') or {}
        except Exception as e:
            s.T = [{'dir': v, 'key': k} for k, v in FBD.items()]
            s.ad(s.G, 'rules_unusable', '%s: %s; builtin taxonomy' % (type(e).__name__, e), 'references/rules.json')

    def disc(s):
        if not s.i.is_dir():
            return s.ad(s.E, 'input_missing', 'input root not found: %s' % s.i, '/input')
        cp = s.i / 'case.json'
        cp = cp if cp.exists() else (sorted(s.i.rglob('case*.json')) or [None])[0]
        if cp:
            try:
                s.case = json.loads(cp.read_text('utf-8', 'ignore'))
                s.case = s.case if isinstance(s.case, dict) else {}
            except Exception as e:
                s.ad(s.E, 'case_json_invalid', '%s: %s' % (type(e).__name__, e), cp.name)
                s.ad(s.PH, 'case_json_repair', 'unparsable: scan-only, case_id null', cp.name)
        s.ck = next((k for k in ('output_contract', 'output_spec', 'result_contract') if isinstance(s.case.get(k), (dict, list))), None)
        s.ct = s.case.get(s.ck) if s.ck else None
        s.ct is None and s.ad(s.PH, 'contract_absent', 'no output_contract: generic schema only', 'case.json')
    def scan(s):
        for p in sorted(s.i.rglob('*')) if s.i.is_dir() else []:
            try:
                p.is_symlink() and s.ad(s.G, 'symlink_skipped', 'not followed', str(p))
                p.is_file() and not p.is_symlink() and '__MACOSX' not in p.as_posix() and s.files.append(p)
            except Exception as e:
                s.ad(s.G, 'scan_failed', str(e), str(p))

    def inv(s):
        for n, p in enumerate(s.files, 1):
            rel = p.relative_to(s.i).as_posix()
            r = dict(file_id='F%04d' % n, rel_path=rel, abs_path=str(p), name=p.name, ext=p.suffix.lower(), kind=None, mime=None,
                     role='reserved' if rel.lower() in X.RESERVED else 'material', read_status='ok', permissions={'mode': None, 'readable': None})
            try:
                q = p.stat()
                r.update(size=q.st_size, sha256=X.shaf(p), mtime=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(q.st_mtime)),
                         permissions={'mode': oct(q.st_mode & 0o777), 'readable': os.access(p, os.R_OK)})
                if q.st_size:
                    with open(p, 'rb') as fh:
                        r['kind'], r['mime'] = sniff(p, fh.read(4096))
                else:
                    r['read_status'] = 'empty'
                    s.ad(s.G, 'empty_file', 'zero-byte: no content signal', rel)
            except Exception as e:
                pe = isinstance(e, PermissionError)
                r['read_status'] = 'unreadable' if pe else 'error'
                s.ad(s.E if pe else s.G, 'denied' if pe else 'stat', str(e), rel)
            s.rec.append(r)
    def meta(s, r):
        p, f, tx = Path(r['abs_path']), {}, ''

        def P(k, v, src, loc, cf):
            v not in (None, '', [], {}) and k not in f and f.update({k: {'value': v, 'source': src, 'locator': loc, 'confidence': cf}})

        try:
            if r['kind'] == 'pdf':
                d = X.pdf(p.read_bytes(), s.U['limits'].get('pdf_cap', 6000000))
                i, tx = d['info'], d['text']
                r['pdf'] = {'encrypted': d['encrypted'], 'text_layer': d['layer'], 'chars': d['chars']}
                i.get('title') and not X.JUNK.search(i['title']) and len(i['title']) > 11 and P('title', i['title'], 'pdf_info', '/Info /Title', 'high')
                i.get('author') and P('authors', [x.strip() for x in re.split(r'[;,]| and ', i['author']) if x.strip()], 'pdf_info', '/Info /Author', 'medium')
                tx and X.pick(tx) and P('title', X.pick(tx)[0], 'pdf_text', 'page 1 line %d' % X.pick(tx)[1], 'medium')
                d['encrypted'] and s.ad(s.E, 'encrypted_pdf', 'no text layer: quarantined', r['rel_path'])
            elif r['ext'] != '.xlsx' and (r['ext'] in X.DAT or r['ext'] in X.TXT or r['kind'] == 'text'):
                tx, _, note = X.dec(p.read_bytes()[:s.U['limits'].get('head', 200000)])
                note and s.ad(s.G, 'encoding', note, r['rel_path'])
                m = re.search(r'^#\s+(.{3,200})$', tx, re.M) if r['ext'] in X.TXT else None
                m and P('title', m[1].strip(), 'file_text', 'first heading', 'medium')
            m = X.DOI.search(tx)
            m and X.cdoi(m[0]) and P('doi', X.cdoi(m[0]), 'content_scan' if tx else 'filename', 'DOI pattern', 'high' if tx else 'low')
            m = X.ARX.search(tx)
            m and P('arxiv_id', (m[1] or '') + (m[2] or ''), 'content_scan' if tx else 'filename', 'arXiv id', 'high' if tx else 'low')
            tx and X.YR.search(tx[:4000]) and P('year', X.YR.search(tx[:4000])[0], 'content_scan', 'year token', 'low')
        except Exception as e:
            pe = isinstance(e, PermissionError)
            r['read_status'] = 'unreadable' if pe else r['read_status']
            s.ad(s.E if pe else s.G, 'denied' if pe else 'meta', str(e), r['rel_path'])
        'title' not in f and X.tfromname(r['name']) and P('title', X.tfromname(r['name']), 'filename', 'filename stem', 'low')
        'year' not in f and X.YR.search(r['name']) and P('year', X.YR.search(r['name'])[0], 'filename', 'year token', 'low')
        r['fields'] = {k: v['value'] for k, v in f.items()}
        s.ME.append({'file_id': r['file_id'], 'rel_path': r['rel_path'], 'fields': f})
    def classify(s, r):
        f, sg = r.get('fields', {}), []
        A = lambda n, v, src: sg.append({'signal': n, 'value': v, 'source': src})
        dt = s.ZM.get(re.sub(r'[^a-z]', '', str(f.get('doc_type') or '').lower()))
        pr = ' '.join([r['name'].lower(), str(f.get('title') or '').lower(), (r.get('text_head') or '')[:1500].lower()])
        h = next((n for n, p in s.PT if re.search(p, pr)), None) if not dt else None
        dt = dt or h
        h and A(h, re.search(dict(s.PT)[h], pr)[0][:50], 'filename_or_content')
        f.get('doi') and not dt and (dt := 'journal_article') and A('doi', f['doi'], 'content_scan')
        e, k, pdfd = r['ext'], r['kind'], r.get('pdf') or {}
        for cond, d2, n2, src in ((k in ('png', 'jpeg', 'tiff', 'webp', 'gif'), 'scan', 'image', 'magic'),
                                  (k == 'pdf' and not pdfd.get('text_layer') and pdfd.get('chars', 0) < 40, 'scan', 'pdf_no_text', 'content_stream'),
                                  (e in X.COD, 'code', 'code_ext', 'filename'), (e == '.bib', 'metadata_table', 'bib_ext', 'filename'),
                                  (e in X.DAT, 'dataset', 'data_ext', 'filename'),
                                  (e in X.TXT or e in ('.docx', '.tex'), 'note', 'prose_ext', 'filename')):
            if not dt and cond:
                dt = d2
                A(n2, e or k, src)
        r['read_status'] in ('unreadable', 'corrupt', 'error') and A('read_status', r['read_status'], 'io')
        if pdfd.get('encrypted'):
            A('encrypted', 'content not parseable', 'pdf_trailer')
            dt = None
        dt = dt or 'unknown'
        dt == 'unknown' and not sg and A('no_signal', 'no metadata/text signal', 'none')
        n = len([x for x in sg if x['source'] in ('content_scan', 'magic', 'content_stream', 'filename_or_content')])
        yr, d = str(f.get('year') or ''), s.U['dirs'].get(dt, '00_inbox')
        dt in PUB + ('preprint', 'supplementary') and (d := d + '/' + (yr if re.fullmatch(r'(19|20)\d\d', yr) else 'undated'))
        r['cls'] = {'file_id': r['file_id'], 'rel_path': r['rel_path'], 'doctype': dt, 'dir': d,
                    'confidence': 'high' if n > 1 else ('medium' if n == 1 else 'low'), 'signals': sg}
    def tag(s, r):
        f = r.get('fields', {})
        blob = ' '.join([str(f.get('title') or ''), (r.get('text_head') or '')[:2500], r['name']]).lower()
        got = {}
        for e in s.U.get('vocab', []):
            m = next((t for t in [e.get('tag', '')] + list(e.get('synonyms', []))
                      if t and re.search(r'(?<![a-z0-9])' + re.escape(t.lower()) + r'(?![a-z0-9])', blob)), None)
            m and got.setdefault(e['tag'], m)
        c = int(s.U['limits'].get('tag_max', 8))
        tags = list(got)[:c]
        r['tag'] = {'file_id': r['file_id'], 'rel_path': r['rel_path'], 'tags': tags,
                    'evidence': [{'tag': t, 'matched_term': got[t]} for t in tags],
                    'status': 'ok' if tags else 'no_vocab_match'}
    def name(s, r):
        f, nm, mi = r.get('fields', {}), s.U['naming'], s.U['naming']['missing']
        au = f.get('authors') or []
        tk = {'year': f.get('year') if re.fullmatch(r'(19|20)\d\d', str(f.get('year') or '')) else mi['year'],
              'author': X.slug(re.sub(r'(?i)^(van|von|de|der|da)\s+', '', re.split(r'[;,]', str(au[0]))[0].strip() if au else '') or mi['author'], 24),
              'title': X.slug(str(f.get('title') or X.tfromname(r['name']) or mi['title']), int(nm['title_chars'])),
              'doctype': r['cls']['doctype'][:3]}
        try:
            base = nm['template'].format(**tk)
        except KeyError:
            base = X.slug('-'.join(map(str, tk.values())), nm['max_length'])
        dg = [k for k, v in (('year', mi['year']), ('author', mi['author']), ('title', mi['title'])) if tk[k] == v]
        r['naming'] = {'file_id': r['file_id'], 'original': r['rel_path'], 'template': nm['template'],
                       'proposed_name': base[:int(nm['max_length'])].strip('-._ ') + r['ext'], 'degraded_fields': dg}
    def dedup(s):
        by = {}
        for r in s.mats():
            r.get('sha256') and by.setdefault(r['sha256'], []).append(r)
        for sha, rs in sorted(by.items()):
            if len(rs) < 2:
                continue
            rs.sort(key=lambda r: (r['rel_path'].count('/'), str(r['mtime']), r['rel_path']))
            rs[0]['dup_role'] = 'keeper'
            for dd in rs[1:]:
                dd.update(dup_role='exact_duplicate', dup_group='D%03d' % (len(s.DD['exact']) + 1))
            s.DD['exact'].append({'group_id': 'D%03d' % (len(s.DD['exact']) + 1), 'sha256': sha, 'keeper': rs[0]['rel_path'],
                                  'reason': 'identical sha256; keeper = shallowest path, then mtime', 'duplicates': [d['rel_path'] for d in rs[1:]]})
        s.DD['dupfiles'] = sum(len(g['duplicates']) for g in s.DD['exact'])
        idx = {}
        for r in s.mats():
            f = r.get('fields', {})
            kt = 'doi' if f.get('doi') else 'arxiv_id' if f.get('arxiv_id') else 'title_author_year'
            k = ('doi:' + str(X.cdoi(str(f['doi'])) or f['doi']).lower() if kt == 'doi' else
                 'arxiv:' + str(f['arxiv_id']).split('v')[0].lower() if kt == 'arxiv_id' else
                 'tay:%s|%s' % (X.ntitle(f.get('title'))[:70], f.get('year')) if f.get('year') and len(X.ntitle(f.get('title'))) > 18 else None)
            k and idx.setdefault(k, [kt, []])[1].append(r)
        for k, (kt, rs) in sorted(idx.items()):
            if len(rs) < 2 or len({r.get('sha256') for r in rs}) < 2:
                continue
            rl = {r['file_id']: ('published' if r['cls']['doctype'] in PUB else r['cls']['doctype']) for r in rs}
            nd = sorted(rs, key=lambda r: (rl[r['file_id']] != 'published', str(r['mtime'])))
            kp, cid = next((r for r in nd if rl[r['file_id']] == 'published'), nd[-1]), 'V%03d' % (len(s.DD['chains']) + 1)
            kp['version_role'] = 'keep'
            for r in nd:
                r['file_id'] != kp['file_id'] and rl[r['file_id']] != 'supplementary' and r.update(version_role='superseded', chain=cid)
            s.DD['chains'].append({'chain_id': cid, 'identity_key': k, 'key_type': kt, 'status': 'resolved' if kt != 'title_author_year' else 'needs_human',
                                   'nodes': [[r['rel_path'], rl[r['file_id']]] for r in nd], 'keep': kp['rel_path'],
                                   'superseded': [r['rel_path'] for r in nd if r.get('chain') == cid],
                                   'decision': 'version of record kept' if kp['file_id'] != nd[-1]['file_id'] else 'latest kept'})
    def stage(s, r):
        sp = s.U['special']
        d, w = ((sp['quarantine'], 'quarantine') if r['read_status'] in ('unreadable', 'corrupt', 'error') or (r.get('pdf') or {}).get('encrypted') else
                (sp['duplicates'] + '/' + r['sha256'][:8], 'archive duplicate') if r.get('dup_role') == 'exact_duplicate' else
                (sp['superseded'] + '/' + str(r.get('chain')), 'archive superseded') if r.get('version_role') == 'superseded' else
                (r['cls']['dir'], 'classify'))
        dst = s.L / d / r['naming']['proposed_name']
        if dst.exists() and X.shaf(dst) == r['sha256']:
            r['staged_path'] = dst.relative_to(s.o).as_posix()
            return s.op(r, 'skipped_exists', dst, w + '; identical copy staged (rerun)')
        dst.exists() and (dst := dst.with_name('%s-%s%s' % (dst.stem, r['sha256'][:8], r['ext'])))
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(r['abs_path'], dst)
            aft = X.shaf(dst)
            if aft != r['sha256']:
                dst.unlink()
                s.ad(s.E, 'hash_mismatch', 'staged copy differs: removed', r['rel_path'])
                return s.op(r, 'failed', dst, w + '; sha mismatch')
            r['staged_path'], r['staged_sha256'] = dst.relative_to(s.o).as_posix(), aft
            s.op(r, 'done', dst, w)
        except Exception as e:
            s.ad(s.E, 'copy_failed', '%s: %s' % (type(e).__name__, e), r['rel_path'])
            s.op(r, 'failed', dst, w + '; ' + str(e))
    def op(s, r, st, dst, w):
        s.OP.append({'seq': len(s.OP) + 1, 'ts': X.now(), 'op': 'copy', 'status': st, 'src': r.get('rel_path'), 'dst': dst.as_posix(),
                     'sha256': r.get('sha256'), 'bytes': r.get('size'), 'reason': w})

    def doc(s, st):
        return X.assemble({'st': st, 'rec': s.rec, 'met': s.ME, 'dd': s.DD, 'ops': s.OP, 'err': s.E, 'deg': s.G, 'pend': s.PH,
                           'case': s.case, 'ct': s.ct, 'ck': s.ck, 'al': s.U.get('aliases') or [], 'inp': s.i, 'lib': s.L,
                           'dirs': s.U['dirs'], 'tax': s.T, 'wo': [], 'fl': s.FL, 't0': T0, 'budget': s.a.time_budget,
                           'bs': s.bs, 'dry': False, 'ev_cap': s.U['limits'].get('ev_cap', 200)})
    def write(s, st):
        s.st = st
        X.jw(s.o / 'result.json', s.doc(st))

def main(argv=None):
    ap = argparse.ArgumentParser(prog='organize.py', description='Inventory, classify, tag, rename, dedupe, version and stage a research file library; writes result.json (output_contract backfill), inventory.csv, operations.log, version_chain.json, rollback.sh, library/.',
                                 epilog='example: python3 -B organize.py --input /input --output /app/output (illustrative, not a formal case result)')
    ap.add_argument('--input', default=os.environ.get('INPUT_DIR', '/input' if Path('/input').is_dir() else str(Path.cwd() / 'input')), help='case root')
    ap.add_argument('--output', default=os.environ.get('OUTPUT_DIR', '/app/output' if Path('/app').is_dir() else str(Path.cwd() / 'output')), help='output root')
    ap.add_argument('--time-budget', type=float, default=780.0, help='soft seconds')
    a = ap.parse_args(argv)
    r = None
    try:
        r = R(a)
        r.o.mkdir(parents=True, exist_ok=True)
        r.write('partial')
        r.rules(); r.disc(); r.scan(); r.inv(); r.write('partial')
        for x in r.mats():
            time.time() - T0 < a.time_budget and r.meta(x)
        r.write('partial')
        for x in r.mats():
            r.classify(x); r.tag(x)
        r.dedup()
        for x in r.mats():
            r.name(x)
        r.write('partial')
        for x in r.mats():
            time.time() - T0 < a.time_budget + 60 and r.stage(x)
        X.write_csv(r.o / 'inventory.csv', r.rec)
        X.write_logs(r.o, r.OP, r.case.get('case_id'))
        X.jw(r.o / 'version_chain.json', {'chains': r.DD['chains'], 'exact_duplicate_groups': r.DD['exact'], 'method': r.DD['method']})
        m, bad = r.mats(), [x for x in r.mats() if x.get('read_status') in ('unreadable', 'corrupt', 'error') or not x.get('staged_path')]
        st = 'input_error' if not r.rec else 'insufficient_evidence' if (not m or not any(x.get('cls') for x in m)) else \
            ('partial' if (r.E or bad or r.df or r.ct is None or r.bs) else 'ok')
        r.write(st)
        print('[%s] %s files=%s materials=%s staged=%s groups=%s chains=%s errors=%s pending=%s out=%s' % (
            S, r.st, len(r.rec), len(r.mats()), len([x for x in r.mats() if x.get('staged_path')]), len(r.DD['exact']),
            len(r.DD['chains']), len(r.E), len(r.PH), r.o))
    except BaseException as e:
        import traceback
        tb = traceback.format_exc()
        try:
            if r is None:
                X.jw(Path(a.output) / 'result.json', {'skill': {'name': S, 'version': V}, 'case_id': None, 'status': 'input_error',
                                                      'errors': [{'kind': 'fatal_bootstrap', 'detail': '%s: %s' % (type(e).__name__, e)}],
                                                      'degradations': [], 'pending_human': [], 'uncertainty': [], 'changes': [], 'inventory': [],
                                                      'runtime': {'seconds': round(time.time() - T0, 2)}})
            else:
                r.ad(r.E, 'fatal', '%s: %s' % (type(e).__name__, e))
                r.ad(r.G, 'traceback_tail', tb.strip().splitlines()[-1])
                r.write('partial')
        except Exception:
            pass
    return 0


if __name__ == '__main__':
    sys.exit(main())
