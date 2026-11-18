STOP = set('a an the of and or in on for to with by from as at is are was were be this that these it its we our their also than then which such can may must should not no more most less very using used use studies paper result results data show shows report reported find found suggest suggests however between among into over while when where what who how why all any each other others new same value values table fig et al vs etc'.split())
"""research_core: extraction/indexing/retrieval primitives, report template
renderer and sub-question template loader. Stdlib only, offline, no CWD deps."""
import csv, html, json, re, shutil, subprocess, time, zlib, zipfile
from pathlib import Path
H = Path(__file__).resolve().parent
REF = H.parent / 'references'
T0 = time.time()
KIND = dict([('.pdf', 'pdf'), ('.docx', 'docx'), ('.xlsx', 'xlsx'), ('.csv', 'csv'), ('.tsv', 'tsv'), ('.json', 'json'), ('.md', 'text'), ('.txt', 'text'), ('.png', 'image'), ('.jpg', 'image')])
CALLS, ERRS, DEGS, CHGS, PEND = ([], [], [], [], [])

def nu(s):
    return re.sub('\\s+', ' ', (s or '').replace('\xad', '').replace('\xa0', ' ')).strip()

def cut(s, n):
    s = nu(s)
    return s if len(s) <= n else s[:n]

def rd(p, d=None):
    try:
        return json.loads(Path(p).read_text(encoding='utf-8', errors='replace'))
    except Exception:
        return d

def wj(p, o):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(o, ensure_ascii=False, indent=2), encoding='utf-8')

def call(tool, args, st, res, t):
    CALLS.append({'step': len(CALLS) + 1, 'tool': tool, 'args': {k: str(v)[:250] for k, v in args.items()}, 'status': st, 'elapsed_ms': int((time.time() - t) * 1000), 'result': res})

def tb(hd, rows):
    es = lambda c: str('' if c is None else c).replace('|', '\\|').replace('\n', ' ')
    return '\n'.join(['| ' + ' | '.join(hd) + ' |', '|' + '---|' * len(hd)] + ['| ' + ' | '.join(es(c) for c in r) + ' |' for r in rows])


def kind(p):
    k = KIND.get(p.suffix.lower(), '')
    try:
        h = p.open('rb').read(8)
    except Exception:
        return k or 'unknown'
    if h.startswith(b'%PDF'):
        return 'pdf'
    if h.startswith(b'\x89PNG') or h.startswith(b'\xff\xd8') or h[:4] in (b'II*\x00', b'MM\x00*'):
        return 'image'
    if h.startswith(b'PK'):
        return k if k in ('docx',) else 'zip'
    return k or 'unknown'

def disc(inp):
    t, b, out = (time.time(), Path(inp), [])
    for p in sorted(b.rglob('*')):
        try:
            if p.is_file() and (not p.name.startswith('.')):
                out.append({'path': str(p), 'rel': str(p.relative_to(b)), 'kind': kind(p), 'bytes': p.stat().st_size})
        except Exception as ex:
            ERRS.append({'stage': 'discover', 'error': '%s: %s' % (p.name, ex)})
    call('discover_inputs', {'input': str(b)}, 'ok', {'n_files': len(out)}, t)
    return out

def _un(b):
    s = re.sub('\\\\([nrtbf()\\\\])', lambda m: {'n': '\n', 't': ' ', 'r': '\r'}.get(m.group(1), m.group(1)), b.decode('latin-1'))
    return re.sub('\\\\([0-7]{1,3})', lambda m: chr(int(m.group(1), 8)), s)

def _ops(d):
    o = []
    for m in re.finditer(b'\\((?:\\\\.|[^\\\\()])*\\)\\s*Tj|\\[((?:[^\\[\\]]|\\\\.)*)\\]\\s*TJ|(T\\*|Td|TD|ET)', d):
        g = m.group(0)
        if g.rstrip().endswith(b'Tj'):
            o.append(_un(g[g.find(b'(') + 1:g.rfind(b')')]))
        elif g.rstrip().endswith(b'TJ'):
            o.append(''.join((_un(x[1:-1]) for x in re.findall(b'\\((?:\\\\.|[^\\\\()])*\\)', m.group(1) or b''))))
        else:
            o.append('\n')
    return ''.join(o)

def pdfu(p):
    exe = shutil.which('pdftotext')
    if exe:
        t = time.time()
        try:
            r = subprocess.run([exe, '-layout', str(p), '-'], capture_output=True, timeout=90)
            x = r.stdout.decode('utf-8', 'replace')
            if r.returncode == 0 and nu(x):
                u = [('p.%d' % (i + 1), s) for i, s in enumerate(x.split('\x0c')) if nu(s)]
                call('parse_pdf', {'path': p.name, 'engine': 'pdftotext'}, 'ok', {'pages': len(u)}, t)
                return (u, 'ok', 'pdftotext -layout')
        except Exception as ex:
            ERRS.append({'stage': 'parse_pdf', 'error': 'pdftotext: %s' % ex})
    t, u = (time.time(), [])
    try:
        data = p.read_bytes()
    except Exception as ex:
        call('parse_pdf', {'path': p.name}, 'failed', {'error': str(ex)}, t)
        return (u, 'failed', str(ex))
    for m in re.finditer(b'stream\\r?\\n', data):
        e = data.find(b'endstream', m.end())
        if e < 0:
            continue
        d = None
        for cand in (data[m.end():e], data[m.end():e].rstrip(b'\r\n')):
            for f in (zlib.decompress, lambda y: zlib.decompressobj().decompress(y)):
                try:
                    d = f(cand)
                    break
                except Exception:
                    continue
            if d:
                break
        if not d or (b'Tj' not in d and b'TJ' not in d):
            continue
        x = _ops(d)
        if nu(x) and sum((c.isalnum() or c.isspace() or c in '.,;:()%-' for c in x)) / max(1, len(x)) > 0.25:
            u.append(('stream:%d' % (len(u) + 1), x))
    if u:
        DEGS.append({'stage': 'parse_pdf', 'degradation': '%s: locators are stream indices' % p.name})
        call('parse_pdf', {'path': p.name, 'engine': 'stdlib-zlib'}, 'degraded', {'streams': len(u)}, t)
    else:
        call('parse_pdf', {'path': p.name, 'engine': 'stdlib-zlib'}, 'failed', {'reason': 'no text stream'}, t)
    return (u, 'ok' if u else 'failed', 'stdlib-zlib')

def parse(f):
    p, k, t = (Path(f['path']), f['kind'], time.time())
    try:
        if k == 'pdf':
            u, st, note = pdfu(p)
        elif k == 'docx':
            x = re.sub('</w:p>', '\n\n', zipfile.ZipFile(p).read('word/document.xml').decode('utf-8', 'replace'))
            u, st, note = ([('doc', html.unescape(re.sub('<[^>]+>', '', x)))], 'ok', 'docx-xml')
        elif k in ('csv', 'tsv'):
            rows = list(csv.reader(p.read_text(encoding='utf-8', errors='replace').splitlines(), delimiter='\t' if k == 'tsv' else ','))
            hd = rows[0] if rows else []
            u = [('row=%d' % i, ' ; '.join(('%s=%s' % (hd[j] if j < len(hd) else 'c%d' % j, c) for j, c in enumerate(r) if nu(c)))) for i, r in enumerate(rows[1:], 2) if any((nu(c) for c in r))]
            st, note = ('ok' if u else 'failed', 'csv-rows')
        elif k == 'json':
            o = rd(p)
            if o is None:
                return ([], 'failed', 'invalid json')
            u = [('$[%d]' % i, json.dumps(x, ensure_ascii=False)) for i, x in enumerate(o if isinstance(o, list) else [o])]
            st, note = ('ok', 'json-records')
        elif k == 'text':
            raw, x = (p.read_bytes(), None)
            for enc in ('utf-8', 'utf-8-sig', 'gb18030', 'latin-1'):
                try:
                    x = x or raw.decode(enc)
                except Exception:
                    pass
            u, st, note = ([('doc', x or '')], 'ok' if x else 'failed', 'text')
        else:
            return ([], 'unsupported', 'unsupported')
        call('parse_' + k, {'path': f['rel']}, st, {'units': len(u)}, t)
        return (u, st, note)
    except Exception as ex:
        call('parse_' + k, {'path': f['rel']}, 'failed', {'error': str(ex)[:160]}, t)
        ERRS.append({'stage': 'parse', 'error': '%s: %s' % (f['rel'], ex)})
        return ([], 'failed', str(ex)[:160])
SENT = re.compile('(?<=[。！？；!?;])\\s*|(?<=[.])\\s+')

def sents(x):
    return [s.strip() for s in SENT.split(x or '') if len(nu(s)) >= 15]

def tk(s):
    s = (s or '').lower()
    c = re.findall('[\\u4e00-\\u9fff]', s)
    return re.findall('[a-z][a-z0-9\\-]{1,}', s) + [''.join(c[i:i + 2]) for i in range(len(c) - 1)]

def index(files, budget=None):
    srcs, pas = [], []
    for i, f in enumerate(files, 1):
        if budget and time.time() - T0 > budget:
            DEGS.append({'stage': 'index', 'degradation': 'budget reached; rest unparsed'})
            break
        sid = 's%d' % i
        u, st, note = parse(f)
        s = dict(f, source_id=sid, parse_status=st, parse_note=note, n_passages=0)
        srcs.append(s)
        units = []
        for loc, text in u:
            paras = [x for x in re.split('\\n\\s*\\n', text) if nu(x)]
            units += [('%s~p%d' % (loc, k + 1), x) for k, x in enumerate(paras)] if len(paras) > 1 else [(loc, text)]
        for loc, text in units:
            buf, ch = '', []
            for x in (sents(text) or [text]) if len(text) > 1200 else [text]:
                while len(x) > 1200:
                    ch.append(x[:1200])
                    x = x[1200:]
                if len(buf) + len(x) > 1100:
                    ch.append(buf)
                    buf = ''
                buf += x
            if buf.strip():
                ch.append(buf)
            for ci, c in enumerate(ch):
                if nu(c):
                    pas.append({'pid': '%s:p%d' % (sid, len(pas) + 1), 'sid': sid, 'src': f['rel'],
                                'locator': loc if len(ch) == 1 else '%s~c%d' % (loc, ci + 1),
                                'text': nu(c), 'tokens': tk(c)})
                    s['n_passages'] += 1
    df = {}
    for p in pas:
        p['ntok'] = max(1, len(p['tokens']))
        for x in set(p['tokens']):
            df[x] = df.get(x, 0) + 1
    n = max(1, len(pas))
    return (srcs, pas, {k: 1.0 + (n / (1.0 + c)) ** 0.5 for k, c in df.items()})

def ret(pas, idf, terms, k=6):
    q = []
    for t in terms:
        for x in tk(t):
            if x not in STOP and x not in q:
                q.append(x)
    q = sorted(q, key=lambda x: -idf.get(x, 0))[:14]
    sc = [(sum((idf[x] for x in [y for y in q if y in p['tokens']])) / p['ntok'] ** 0.5, p, [y for y in q if y in p['tokens']]) for p in pas]
    return (sorted([s for s in sc if s[2]], key=lambda x: -x[0])[:k], q)

def bq(p, hit):
    hs, best, bs = set(hit), '', -1.0
    for s in sents(p['text']) or [p['text']]:
        v = sum((1 for t in tk(s) if t in hs)) / (1 + abs(len(s) - 180) / 400.0)
        v += 0.6 * bool(re.search('\\d', s)) + 0.4 * bool(re.search('[%‰]|p\\s*[<=]', s))
        if v > bs:
            best, bs = s, v
    return cut(best or p['text'], 420)


def quote_tier(q, texts):
    """Return (tier, locator) for a verbatim quote against [(locator, text)]."""
    q = nu(q)
    if not q:
        return ('none', None)
    for loc, t in texts:
        if q in nu(t):
            return ('strict', loc)
    nq = re.sub('\\s+', '', q)
    for loc, t in texts:
        if nq and nq in re.sub('\\s+', '', t):
            return ('whitespace_insensitive', loc)
    return ('none', None)

def sqtpl():
    try:
        blk = re.search('(?s)<!--\\s*SQ_TEMPLATES\\s*-->(.*?)<!--\\s*/SQ_TEMPLATES\\s*-->', (REF / 'protocol.md').read_text(encoding='utf-8', errors='replace')).group(1)
        rows = []
        for ln in blk.splitlines():
            p = [x.strip() for x in ln.strip().split('|')]
            if len(p) >= 5 and (not ln.strip().startswith('|')):
                rows.append({'id': p[0], 'type': p[1], 'deps': [d for d in p[2].split(',') if d], 'question': p[3], 'evidence_req': p[4], 'when': p[5] if len(p) > 5 else ''})
        if rows:
            return rows
    except Exception as ex:
        ERRS.append({'stage': 'sqtpl', 'error': 'protocol.md templates unavailable: %s' % ex})
    return [{'id': 'SQ1', 'type': 'scope', 'deps': [], 'when': '', 'evidence_req': '范围限定原文句', 'question': '研究对象与边界如何界定（{obj}，{years}，{ds}）？'}]

def fill_contract(c, body, alias):
    if not isinstance(c, (dict, list)):
        return {'applicable': False}
    flat = lambda a: re.sub('[^a-z0-9\\u4e00-\\u9fff]', '', str(a).lower())
    names, stack = ([], [c])
    while stack:
        o = stack.pop()
        if isinstance(o, dict):
            names += [str(k) for k in o]
            stack += list(o.values())
        elif isinstance(o, list):
            stack += o
        elif isinstance(o, str) and len(nu(o)) <= 60:
            names.append(nu(o).strip('`*'))
    ns = list(dict.fromkeys(names))
    src = dict(body, **(body.get('synthesis') or {}))
    for n in ns:
        if n not in body:
            k = flat(n.strip('`*'))
            body[n] = next((src.get(ck) for ck, al in alias.items() if k and any((flat(a) and (flat(a) in k or k in flat(a)) for a in [ck] + al))), None)
    return {'applicable': True, 'n_fields': len(ns), 'filled': [n for n in ns if body.get(n) not in (None, [], {})], 'null_filled': [n for n in ns if body.get(n) in (None, [], {})]}

def snapshot(out, ctx, status, extra=None):
    body = {'skill': {'name': 'deep-research-ledger', 'version': '1.0.0'}, 'case_id': ctx.get('case_id'), 'status': status, 'research_question': {'text': ctx.get('question') or None, 'extracted_from': ctx.get('qsrc')}, 'sub_questions': [], 'search_plan': [], 'evidence_matrix': [], 'citations': [], 'sources': [], 'synthesis': {'claims': [], 'conflicts': [], 'gaps': []}, 'coverage': {}, 'uncertainty': {}, 'pending_human': PEND, 'errors': ERRS, 'degradations': DEGS, 'changes': CHGS, 'artifacts': [], 'tool_calls': CALLS, 'output_contract_echo': ctx.get('contract'), 'runtime': {'seconds': round(time.time() - T0, 2), 'network': 'disabled'}}
    body.update(extra or {})
    body['contract_fill'] = fill_contract(ctx.get('contract'), body, ctx.get('alias') or {})
    wj(Path(out) / 'result.json', body)
    return body
FACET = {k: v.split(',') for k, v in {'design': 'rct,randomi,cohort,case-control,meta-analys,systematic review,cross-sectional,longitudinal,in vitro,in vivo,benchmark,ablation,临床试验,队列,随机,系统综述,横断面,体外,体内', 'outcome': 'efficacy,safety,survival,yield,accuracy,precision,recall,sensitivity,specificity,toxicity,cost,efficiency,latency,throughput,auc,疗效,安全性,存活,产率,精度,准确率,灵敏度,特异度,毒性', 'mechanism': 'mechanism,pathway,signal,expression,regulation,binding,cataly,mediated,inhibit,activat,机制,通路,信号,表达,调控,结合,催化,介导,抑制,激活,靶点', 'compare': 'vs,versus,compared,comparison,difference,outperform,superior,对比,比较,差异,优于,高于,低于'}.items()}
QK = ['research_question', 'question', 'task_instruction', 'instruction', 'prompt', 'objective', 'topic', '研究问题', '研究任务', 'goal', 'task', 'title']

def findq(case, files):
    cd, stack = ([], [case])
    while stack:
        o = stack.pop()
        if isinstance(o, dict):
            for k, v in o.items():
                if isinstance(v, str) and len(nu(v)) >= 15 and any((q in str(k).lower() for q in QK)):
                    cd.append((0, nu(v)))
                elif isinstance(v, (dict, list)):
                    stack.append(v)
        elif isinstance(o, list):
            stack += o[:30]
    for f in files:
        if f['kind'] == 'text' and Path(f['path']).name.lower() in ('task.md', 'prompt.md'):
            try:
                for ln in Path(f['path']).read_text(encoding='utf-8', errors='replace').splitlines():
                    s = nu(ln.lstrip('#>-* '))
                    if len(s) >= 25 and (not s.startswith(('|', '```'))):
                        cd.append((1, s))
            except Exception as ex:
                ERRS.append({'stage': 'findq', 'error': str(ex)})
    if not cd:
        return ('', 'none')
    top = min((c[0] for c in cd))
    return (cut(max([c[1] for c in cd if c[0] == top], key=len), 600), 'case_field' if top == 0 else 'task_md')

def fac(q):
    ql, f = (q.lower(), {'years': sorted(set(re.findall('(?:19|20)\\d{2}', q)))[:8], 'terms': {}})
    for k, ws in FACET.items():
        f['terms'][k] = [w for w in ws if (bool(re.search('(?<![a-z])' + re.escape(w), ql)) if w.isascii() else w in ql)][:6]
    f['compare'] = bool(f['terms']['compare'])
    o, seen = ([], set())
    for e in map(nu, re.findall('\\b[A-Z][A-Za-z0-9\\-]{2,}(?:\\s+[A-Z][A-Za-z0-9\\-]{2,})?\\b', q) + re.split('[，,。；;：:（）()\\[\\]\\"\'、\\s]+|的|与|和|在|对|及|或', q)):
        if 2 <= len(e) <= (8 if not e.isascii() else 14) and e.lower() not in seen and (not (e.isascii() and e.lower() in STOP)):
            seen.add(e.lower())
            o.append(e)
    f['entities'] = o[:8]
    return f

def write_report(out, ctx):
    """Render research_report.md: every row comes from run data, no free text conclusions."""
    srcs, sqs, cl, ci = (ctx['srcs'], ctx['sqs'], ctx['claims'], ctx['cites'])
    f, conf, gaps = (ctx.get('facets') or {}, ctx['conflicts'], ctx['gaps'])
    T = f.get('terms') or {}
    pl = (ctx.get('plan') or {}).get('plan', [])
    empty = [s['id'] for s in sqs if not any((c.get('sq') == s['id'] for c in cl))]
    L = ['# 研究报告 %s' % (ctx.get('question') or '（输入未提供研究问题）'), '', '- case_id `%s` ｜ 状态 **%s** ｜ 范围：`/input` 的 %d 个材料；未联网、未引入外部文献' % (ctx.get('case_id'), ctx.get('status'), len(srcs)), '', '## 1. 研究问题与范围', '', tb(['维度', '识别结果'], [['研究对象', '、'.join(f.get('entities') or []) or '未显式给出'], ['时间范围', '、'.join(f.get('years') or []) or '未限定'], ['比较关系', '存在' if f.get('compare') else '未识别'], ['设计限定', '、'.join(T.get('design') or []) or '未限定'], ['结局指标', '、'.join(T.get('outcome') or []) or '未限定']]), '', '## 2. 问题拆解', '', tb(['子问题', '类型', '依赖', '证据要求'], [[s['id'], s.get('type'), ', '.join(s.get('deps') or []) or '—', s.get('evidence_req')] for s in sqs]), '', '## 3. 检索与材料', '', '%d 条检索式 / %d 波次；详见 result.json.search_plan。' % (sum((len(p.get('queries', [])) for p in pl)), len({p.get('wave') for p in pl})) if pl else '（无检索计划记录）', '', tb(['source_id', '材料', '类型', '状态', '段落'], [[s['source_id'], s.get('rel'), s.get('kind'), s.get('parse_status'), s.get('n_passages')] for s in srcs]), '', '- 候选证据 %d；来源 %d/%d；结论 %d；无结论子问题：%s' % (ctx.get('ncand', 0), len({c['source_id'] for c in ci}), len(srcs), len(cl), '、'.join(empty) or '无'), '', '## 4. 分主题综合', '']
    L += [tb(['结论', '子问题', '强度', '引用', '论断', '适用条件'], [[c['claim_id'], c.get('sq') or '—', c['strength'], ' '.join(('[%d]' % n for n in c['citations'])) or '—', c.get('claim'), c.get('conditions') or '—'] for c in cl])] if cl else ['**未生成结论**：无 `synthesis.json`，只交付证据台账，不把候选段落当结论。']
    L += ['', '## 5. 冲突', '', tb(['ID', '议题', 'A 方', 'B 方', '处置', '依据'], [[c['conflict_id'], c['topic'], c['side_a']['position'], c['side_b']['position'], c['resolution'], c['basis']] for c in conf]) if conf else '未识别到直接冲突（不等于不存在），强度 insufficient。', '', '## 6. 空白', '', tb(['ID', '空白', '依据', '已检索', '如何填补'], [[g['gap_id'], g['gap'], g['basis'], g.get('searched'), g.get('what_would_close_it')] for g in gaps]) if gaps else '未记录研究空白。', '', '## 7. 引用可追溯表', '', tb(['#', 'source_id', 'locator', '逐字证据', '校验', '用于'], [['[%d]' % c['n'], c['source_id'], c['locator'], cut(c['quote'], 200), c['quote_match'], ', '.join(c['used_by'])] for c in ci]) if ci else '（无可追溯引用）', '', '## 8. 不确定性与局限', '', '- 逐字校验 %d/%d 条结论带引用，未通过者进 pending_human。' % (len([c for c in cl if c['citations']]), len(cl)), '- 冲突 %d、空白 %d；未解析材料：%s' % (len(conf), len(gaps), '、'.join([s.get('rel') for s in srcs if s.get('parse_status') != 'ok']) or '无'), '- 只覆盖提供材料；词法检索对同义改写不敏感。']
    Path(out, 'research_report.md').write_text('\n'.join(L) + '\n', encoding='utf-8')
    return str(Path(out) / 'research_report.md')
