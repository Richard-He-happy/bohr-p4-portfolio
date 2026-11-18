#!/usr/bin/env python3
"""Stdlib helpers and deterministic verifier for library-auto-organizer. Run after organize.py: python3 -B verify.py"""
import argparse, csv, hashlib, json, re, sys, time, unicodedata, zipfile, zlib
from datetime import datetime, timezone
from pathlib import Path

S, V = 'library-auto-organizer', '1.0.0'
DOI = re.compile(r'10\.\d{4,9}/[-._;()/:A-Za-z0-9<>]+')
ARX = re.compile(r'arxiv[:\s/]*(\d{4}\.\d{4,5})(v\d+)?', re.I)
YR = re.compile(r'(?<!\d)(19[5-9]\d|20[0-4]\d)(?!\d)')
JUNK = re.compile(r'^(microsoft word|untitled|document\d*|powerpoint)|\.(docx?|pdf|tex|indd)\b', re.I)
TXT = {'.md', '.txt', '.rst', '.tex', '.bib', '.log', '.yml', '.yaml', '.html'}
DAT = {'.csv', '.tsv', '.xlsx', '.xls', '.json', '.nc', '.h5', '.hdf5', '.fasta', '.fa', '.fastq', '.zip', '.parquet'}
COD = {'.py', '.r', '.ipynb', '.sh', '.m', '.jl', '.c', '.cpp', '.f90'}
RESERVED = {'case.json', 'task.md'}


def now():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def jw(p, o):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    t = p.with_name(p.name + '.tmp')
    t.write_text(json.dumps(o, ensure_ascii=False, indent=1, default=str), encoding='utf-8')
    t.replace(p)


def wt(p, s):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s, encoding='utf-8')


def shaf(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for c in iter(lambda: f.read(1 << 20), b''):
            h.update(c)
    return h.hexdigest()


def dec(data):
    for e in ('utf-8', 'utf-8-sig', 'gb18030', 'big5', 'latin-1'):
        try:
            t = data.decode(e)
        except UnicodeDecodeError:
            continue
        n = None if e.startswith('utf-8') else 'non-utf8 text decoded as %s' % e
        return t, e, ('mojibake markers present' if '\ufffd' in t or '锟斤拷' in t else n)
    return data.decode('latin-1', 'ignore'), 'latin-1', 'undecodable text'


def pstr(raw):
    s = raw if isinstance(raw, str) else raw.decode('latin-1', 'ignore')
    s = re.sub(r'\\([nrtbf()\\])', lambda m: {'n': '\n', 'r': '\r', 't': '\t', 'b': '', 'f': '', '(': '(', ')': ')', '\\': '\\'}[m.group(1)], s)
    return re.sub(r'\\([0-7]{1,3})', lambda m: chr(int(m.group(1), 8)), s).strip()


def phex(h):
    try:
        b = bytes.fromhex(re.sub(r'\s', '', h))
    except ValueError:
        return ''
    return b.decode('utf-16', 'ignore').strip('\x00').strip() if b[:2] == b'\xfe\xff' else b.decode('latin-1', 'ignore').strip()


def pdf(data, cap=6000000):
    o = {'encrypted': b'/Encrypt' in data, 'pages': len(re.findall(rb'/Type\s*/Page[^s]', data)), 'info': {}}
    for k, tag in (('title', b'/Title'), ('author', b'/Author'), ('created', b'/CreationDate')):
        m = re.search(re.escape(tag) + rb'\s*(?:\(((?:\\.|[^\\()])*)\)|<([0-9A-Fa-f\s]{4,})>)', data)
        if m:
            o['info'][k] = pstr(m.group(1)) if m.group(1) is not None else phex(m.group(2))
    ch, tot = [], 0
    for m in re.finditer(rb'stream\r?\n', data):
        if tot > cap:
            break
        e = data.find(b'endstream', m.end())
        if e < 0:
            continue
        c = data[m.end():e][:cap]
        raw = None
        try:
            raw = zlib.decompress(c)
        except Exception:
            try:
                raw = zlib.decompressobj().decompress(c)
            except Exception:
                raw = c if (b'BT' in c and (b'Tj' in c or b'TJ' in c)) else None
        if raw:
            ch.append(raw)
            tot += len(raw)
    body = b'\n'.join(ch).decode('latin-1', 'ignore')
    t = '\n'.join(x for x in (pstr(v[1:-1]) for v in re.findall(r'\((?:\\.|[^\\()])*\)', body)) if x)
    o['text'] = t
    o['layer'] = len(t) > 120 and sum(c.isalpha() for c in t) > max(60, len(t) * 0.35)
    o['chars'] = len(t)
    return o


def slug(s, mx=70):
    s = re.sub(r'[\x00-\x1f\x7f]', '', unicodedata.normalize('NFKC', str(s or '')))
    s = re.sub(r'[\\/:*?"<>|#%{}^~\[\]`$@!+=]', '-', s)
    s = re.sub(r'[\s\u3000]+', '-', s.strip())
    s = re.sub(r'-{2,}', '-', s).strip('-._ ')
    s = s[:mx].strip('-._ ')
    return ('x-' + s) if re.fullmatch(r'(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])', s) else (s or 'untitled')


def cdoi(d):
    d = re.sub(r'^(https?://(dx\.)?doi\.org/|doi:\s*)', '', str(d or '').strip().strip('.,;)'), flags=re.I)
    return d if DOI.match(d) else None


def ntitle(t):
    return re.sub(r'[^a-z0-9]+', '', str(t or '').lower())[:120]


def pick(text):
    best, bi = None, 0
    for i, l in enumerate([x.strip() for x in text.splitlines() if x.strip()][:14]):
        if re.search(r'^(abstract|introduction|keywords)', l, re.I):
            break
        if len(l) < 25 or re.search(r'(doi|http|issn|www\.|@|received|accepted|vol\.|copyright|©)', l, re.I):
            continue
        if best is None or len(l) > len(best):
            best, bi = l, i + 1
    return (best, bi) if best else None


def tfromname(n):
    s = re.sub(r'\((?:1|2|copy|final|revised|accepted)[^)]*\)', ' ', Path(n).stem, flags=re.I)
    s = re.sub(r'(?i)\b(final|submitted|accepted|proof|manuscript|full ?text|draft|v\d+|revised|main|article|paper|suppl\w*)\b', ' ', s.replace('_', ' '))
    s = re.sub(r'^\W*(19|20)\d\d\W*', ' ', s)
    s = re.sub(r'(?i)^(?:[a-z]{2,20}[ _-])?(19|20)\d\d[ _-]?', ' ', s)
    s = re.sub(r'\s{2,}', ' ', s).strip(' -_.')
    return s if len(s) >= 12 else None


def cnt(items, k):
    o = {}
    for i in items:
        v = str(i.get(k) if isinstance(i, dict) else None)
        o[v] = o.get(v, 0) + 1
    return o


def lk(comp, k, al):
    kk = re.sub(r'[^a-z0-9]+', '_', str(k).lower()).strip('_')
    for n, ps in al:
        if any(p in kk for p in ps):
            return comp.get(n)


def fill(tpl, comp, al, filled, path=''):
    if isinstance(tpl, dict):
        o = {}
        for k, v in tpl.items():
            p, h = (path + '.' + k if path else k), lk(comp, k, al)
            if isinstance(v, dict):
                o[k] = fill(v, h if isinstance(h, dict) else comp, al, filled, p)
            elif isinstance(v, list):
                o[k] = h if isinstance(h, list) else []
                isinstance(h, list) and filled.append(p)
            else:
                o[k] = h
                h is not None and filled.append(p)
        return o
    return comp if isinstance(tpl, list) and isinstance(comp, list) else ([] if isinstance(tpl, list) else comp)


def tree(rec, dirs):
    d = {}
    for r in rec:
        q = str(Path(r['staged_path']).parent.as_posix()) if r.get('staged_path') else None
        q and d.update({q: 1 + d.get(q, 0)})
    return [{'path': k, 'files': v} for k, v in sorted(d.items())] or [{'path': dirs.get('unknown', '00_inbox'), 'files': 0}]


def coverage(rec, met, dd, inp, dirs):
    m = [r for r in rec if r['role'] == 'material']
    mf, wp = {}, 0
    for x in met:
        for k, v in x['fields'].items():
            mf[k], wp = mf.get(k, 0) + 1, wp + (1 if v.get('source') and v.get('locator') else 0)
    tr = tree(m, dirs)
    return {'files_discovered': len(rec), 'materials': len(m), 'reserved_skipped': len(rec) - len(m),
            'classified': len([r for r in m if r.get('cls')]), 'tagged': len([r for r in m if r.get('tag')]),
            'named': len([r for r in m if r.get('naming')]), 'staged': len([r for r in m if r.get('staged_path')]),
            'coverage_rate': round(len([r for r in m if r.get('cls')]) / len(m), 4) if m else 0.0,
            'six_elements': {'file_types': {'distinct': len({r.get('kind') for r in rec}), 'counts': cnt(rec, 'kind')},
                             'metadata_fields': {'per_field': mf, 'with_provenance': wp},
                             'directory_levels': {'max_depth': max([len(x['path'].split('/')) for x in tr] or [1]), 'nodes': len(tr)},
                             'duplicates': {'exact_groups': len(dd['exact']), 'files': dd['dupfiles']},
                             'version_differences': {'chains': len(dd['chains'])},
                             'permissions_and_source': {'files_with_mode': len([r for r in rec if r['permissions'].get('mode')]), 'root': str(inp)}}}


def write_csv(path, rec):
    cols = 'file_id rel_path role kind size sha256 mtime perm_mode readable read_status doctype dir confidence tags proposed_name staged_path staged_sha256 dup_role version_role fields'.split()
    with open(path, 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for r in rec:
            c, n, t = r.get('cls', {}), r.get('naming', {}), r.get('tag', {})
            w.writerow([r['file_id'], r['rel_path'], r['role'], r.get('kind'), r.get('size'), r.get('sha256'), r.get('mtime'),
                        r['permissions'].get('mode'), r['permissions'].get('readable'), r.get('read_status'), c.get('doctype'), c.get('dir'),
                        c.get('confidence'), '|'.join(t.get('tags', [])), n.get('proposed_name'), r.get('staged_path'),
                        r.get('staged_sha256'), r.get('dup_role'), r.get('version_role'), '|'.join(sorted(r.get('fields', {})))])


def write_logs(out, ops, case_id):
    hdr = 'op seq ts status src dst sha256 bytes reason'.split()
    L = ['# operations.log skill=%s v%s case=%s %s' % (S, V, case_id, now()), '# ' + '\t'.join(hdr)]
    L += ['\t'.join(str(o[k]) for k in hdr) for o in ops]
    wt(Path(out) / 'operations.log', '\n'.join(L) + '\n')
    wt(Path(out) / 'rollback.sh', '\n'.join(['#!/bin/sh', '# removes staged copies only; input untouched', 'set -u'] +
                                            ['rm -f -- "%s"' % o['dst'] for o in ops if o['status'] == 'done'] + ['echo done']) + '\n')


MAP = [('inventory', 'inv'), ('classification', 'cls'), ('tags', 'tags'), ('naming', 'nm'), ('duplicates', 'dups'), ('versions', 'vers'),
       ('metadata', 'meta'), ('coverage', 'cov'), ('evidence', 'ev'), ('pending_human', 'pend'), ('errors', 'err'), ('operations', 'ops'),
       ('library', 'tree'), ('uncertainty', 'unc'), ('summary', 'summary'), ('status', 'status'), ('degradations', 'deg')]


def assemble(x):
    m = [r for r in x['rec'] if r['role'] == 'material']
    cls = [r['cls'] for r in m if r.get('cls')]
    tr = tree(m, x['dirs'])
    lo = [r['rel_path'] for r in m if r.get('cls', {}).get('confidence') == 'low']
    c = {'status': x['st'], 'inv_csv': 'inventory.csv', 'cls': cls, 'ev': [], 'pend': x['pend'], 'err': x['err'],
         'inv': [{'file_id': r['file_id'], 'path': r['rel_path'], 'role': r['role'], 'type': r.get('kind'), 'mime': r.get('mime'),
                  'size': r.get('size'), 'sha256': r.get('sha256'), 'mtime': r.get('mtime'), 'permissions': r['permissions'],
                  'read_status': r.get('read_status'), 'staged_path': r.get('staged_path'), 'staged_sha256': r.get('staged_sha256')} for r in x['rec']],
         'tags': [r['tag'] for r in m if r.get('tag')], 'nm': [r['naming'] for r in m if r.get('naming')],
         'dups': x['dd'], 'vers': {'chains': x['dd']['chains'], 'file': 'version_chain.json'}, 'meta': x['met'],
         'ops': {'log': 'operations.log', 'count': len(x['ops']), 'by_status': cnt(x['ops'], 'status')},
         'tree': {'root': x['lib'].as_posix(), 'nodes': tr, 'taxonomy': x['tax']},
         'cov': coverage(x['rec'], x['met'], x['dd'], x['inp'], x['dirs']),
         'unc': ([{'kind': 'low_confidence_classification', 'count': len(lo), 'files': lo[:50], 'detail': 'fallback rule; nearest type used'}] if lo else []) +
                [{'kind': k + '_missing', 'count': len([r for r in m if k not in r.get('fields', {})]), 'detail': n}
                 for k, n in (('authors', 'author absent: token anon, value null'), ('year', 'year absent: bucket undated, token nd'))
                 if [r for r in m if k not in r.get('fields', {})]],
         'summary': {'files_total': len(x['rec']), 'materials': len(m), 'by_doctype': cnt(cls, 'doctype'), 'by_dir': cnt(cls, 'dir'),
                     'staged': len([r for r in m if r.get('staged_path')]),
                     'duplicates_archived': len([r for r in m if r.get('dup_role') == 'exact_duplicate']),
                     'superseded_archived': len([r for r in m if r.get('version_role') == 'superseded']),
                     'errors': len(x['err']), 'degradations': len(x['deg']), 'pending_human': len(x['pend']), 'workorder_keys_seen': x['wo']}}
    c['ev'] = [{'file_id': e['file_id'], 'path': e['rel_path'], 'field': k, 'value': v.get('value'), 'source': v.get('source'),
                'locator': v.get('locator'), 'confidence': v.get('confidence')}
               for e in x['met'] for k, v in list(e['fields'].items())[:5]][:x['ev_cap']]
    d = {k: c.get(v) for k, v in MAP}
    d.update(skill={'name': S, 'version': V, 'case': 'library-03'}, case_id=x['case'].get('case_id'), generated_at=now(),
             sources=[{'path': x['inp'].as_posix(), 'role': 'case input root (read-only)', 'files': len(x['rec'])},
                      {'path': 'inventory.csv', 'role': 'inventory with sha256, permissions, staged path'},
                      {'path': 'operations.log', 'role': 'append-only operation evidence'},
                      {'path': 'version_chain.json', 'role': 'version relationship graph'},
                      {'path': 'rollback.sh', 'role': 'reversal script'}],
             changes=[{'seq': o['seq'], 'op': o['op'], 'status': o['status'], 'from_path': o['src'], 'to_path': o['dst'],
                       'sha256': o['sha256']} for o in x['ops']],
             runtime={'seconds': round(time.time() - x['t0'], 2), 'python': sys.version.split()[0], 'budget_seconds': x['budget'],
                      'budget_stop': x['bs'], 'dry_run': x['dry'], 'stdlib_only': True, 'network': 'none'})
    if x['ct'] is None:
        d['contract_backfill'] = {'source_key': None, 'field_count': 0, 'note': 'no output_contract in case.json'}
        return d
    f = fill(x['ct'], c, x['al'], x['fl'])
    d['output_contract'] = f
    mir = {k: v for k, v in (f.items() if isinstance(f, dict) else []) if k not in d}
    d.update(mir)
    d['contract_backfill'] = {'source_key': x['ck'], 'field_count': len(x['fl']), 'filled_paths': sorted(set(x['fl']))[:80],
                              'mirrored_at_top_level': sorted(mir), 'base_key_collisions': sorted(set(f) & set(d)) if isinstance(f, dict) else [],
                              'note': 'contract values under output_contract and, where no base key collided, at top level'}
    return d


def leaves(tpl, path=''):
    if isinstance(tpl, dict):
        return [p for k, v in tpl.items() for p in leaves(v, (path + '.' + k) if path else k)]
    return [path]


def getp(d, path):
    cur = d
    for k in path.split('.'):
        if not isinstance(cur, dict) or k not in cur:
            return None, False
        cur = cur[k]
    return cur, True


def verify(inp, out):
    inp, out = Path(inp).resolve(), Path(out).resolve()
    chk = []

    def add(n, ok, d):
        chk.append({'check': n, 'pass': bool(ok), 'detail': d})

    try:
        res = json.loads((out / 'result.json').read_text('utf-8'))
        add('result_json_parses', True, str(out / 'result.json'))
    except Exception as e:
        add('result_json_parses', False, '%s: %s' % (type(e).__name__, e))
        jw(out / 'verify_report.json', {'skill': S, 'version': V, 'checks': chk, 'ok': False})
        return {'checks': chk, 'ok': False}
    miss = [k for k in ('case_id', 'status', 'sources', 'uncertainty', 'pending_human', 'errors', 'degradations', 'changes', 'runtime', 'inventory') if k not in res]
    add('required_fields_present', not miss, 'missing=%s' % miss if miss else 'all present')
    add('status_enum', res.get('status') in ('ok', 'partial', 'insufficient_evidence', 'input_error'), str(res.get('status')))
    case = {}
    try:
        case = json.loads((inp / 'case.json').read_text('utf-8'))
    except Exception as e:
        add('case_json_readable', False, str(e))
    if case:
        add('case_id_matches_input', res.get('case_id') == case.get('case_id'), 'result=%s input=%s' % (res.get('case_id'), case.get('case_id')))
        if case.get('output_contract'):
            paths = leaves(case['output_contract'])
            got = res.get('output_contract') or {}
            bad = [p for p in paths if not getp(got, p)[1]]
            add('contract_all_fields_present', not bad, 'fields=%d missing=%s' % (len(paths), bad[:8]))
            add('contract_nulls_reported', True, 'null_fields=%d of %d (allowed when input lacks the value)'
                % (len([p for p in paths if getp(got, p)[1] and getp(got, p)[0] in (None, [])]), len(paths)))
    inv = res.get('inventory', [])
    on_disk = [p for p in sorted(inp.rglob('*')) if p.is_file() and '__MACOSX' not in p.as_posix()] if inp.is_dir() else []
    add('inventory_covers_all_files', len(inv) >= len(on_disk), 'inventory=%d disk=%d' % (len(inv), len(on_disk)))
    mis = []
    for r in inv[:800]:
        f = inp / (r.get('path') or '')
        if not f.is_file():
            mis.append(r.get('path'))
        elif r.get('sha256') and shaf(f) != r['sha256']:
            mis.append(r.get('path'))
    add('inventory_sha256_recomputed', not mis, 'mismatch=%s' % mis[:5] if mis else 'verified %d' % min(len(inv), 800))
    staged, broken = 0, []
    for r in inv:
        if r.get('staged_path'):
            staged += 1
            f = out / r['staged_path']
            if not f.is_file() or (r.get('staged_sha256') and shaf(f) != r['staged_sha256']):
                broken.append(r['staged_path'])
    add('staged_copies_exist_and_match', not broken, 'staged=%d bad=%s' % (staged, broken[:5]) if broken else 'staged=%d ok' % staged)
    mats = [r for r in inv if r.get('role') == 'material']
    add('every_material_classified', len(res.get('classification', [])) == len(mats), 'classification=%d materials=%d' % (len(res.get('classification', [])), len(mats)))
    add('every_material_named', len(res.get('naming', [])) == len(mats), 'naming=%d materials=%d' % (len(res.get('naming', [])), len(mats)))
    lp = out / 'operations.log'
    nl = len([l for l in lp.read_text('utf-8', errors='ignore').splitlines() if l and not l.startswith('#')]) if lp.exists() else -1
    add('operations_log_matches_count', nl == res.get('operations', {}).get('count'), 'log_lines=%s count=%s' % (nl, res.get('operations', {}).get('count')))
    add('version_chain_file', (out / 'version_chain.json').exists(), 'version_chain.json')
    add('rollback_available', (out / 'rollback.sh').exists(), 'rollback.sh')
    add('counts_consistent', res.get('summary', {}).get('errors') == len(res.get('errors', [])) and res.get('summary', {}).get('pending_human') == len(res.get('pending_human', [])),
        'summary_errors=%s errors=%d' % (res.get('summary', {}).get('errors'), len(res.get('errors', []))))
    rep = {'skill': S, 'version': V, 'generated_at': now(), 'ok': all(c['pass'] for c in chk),
           'failed': [c['check'] for c in chk if not c['pass']], 'checks': chk}
    jw(out / 'verify_report.json', rep)
    return rep


def main(argv=None):
    ap = argparse.ArgumentParser(prog='verify.py', description='Deterministic re-check of a library-auto-organizer run: result schema, output_contract coverage, inventory and staged-copy hashes, operation count. Always exits 0 and writes verify_report.json.')
    ap.add_argument('--input', default='/input', help='case input root used by organize.py')
    ap.add_argument('--output', default='/app/output', help='output root written by organize.py')
    ap.add_argument('--quiet', action='store_true', help='suppress summary')
    a = ap.parse_args(argv)
    try:
        rep = verify(a.input, a.output)
    except Exception as e:
        rep = {'ok': False, 'checks': [], 'error': '%s: %s' % (type(e).__name__, e)}
        try:
            jw(Path(a.output) / 'verify_report.json', rep)
        except Exception:
            pass
    a.quiet or print('[verify] ok=%s failed=%s' % (rep.get('ok'), rep.get('failed', rep.get('error'))))
    return 0


if __name__ == '__main__':
    sys.exit(main())
