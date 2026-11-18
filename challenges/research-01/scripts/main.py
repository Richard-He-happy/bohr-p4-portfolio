"""research-01 deep-research runner (stdlib only, offline, always exit code 0).

  plan      discover -> decompose -> retrieval plan -> index -> evidence candidates
  finalize  re-parse sources, verify quotes, assemble report/csv/result.json
  check     deterministic self-check of the produced package
  auto      plan + finalize + check
"""
import argparse, csv, json, sys, time
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import research_core as C
V = '1.0.0'
nu, rd, wj = (C.nu, C.rd, C.wj)
Q, QSRC, SN = ('', 'none', {})
STR = ('directly_supported', 'inferred', 'insufficient')
ALIAS = {l.split('|')[0]: l.split('|')[1].split(',') for l in 'research_question|research_question,question,研究问题,aim,topic\nsub_questions|sub_question,decomposition,拆解,子问题\nsearch_plan|search_plan,retrieval_plan,query_plan,检索\nevidence_matrix|evidence_matrix,evidence_map,证据,evidence\nsynthesis|synthesis,findings,conclusion,综述,结论\nconflicts|conflict,contradict,冲突\ngaps|gap,research_gap,空白,limitation\ncitations|citation,reference,引用\nsources|source,material,文献,来源\ncoverage|coverage,覆盖\nuncertainty|uncertain,不确定性,bias\nreport|report,deliverable,产物\nerrors|error,exception,错误'.strip().splitlines()}

def plan(q, f):
    rep = {'obj': '、'.join(f['entities'][:3]) or '研究对象的总体', 'oc': '、'.join(f['terms']['outcome'][:3]) or '主要结局/性能指标', 'mc': '、'.join(f['terms']['mechanism'][:3]) or '机制或方法路径', 'ds': '、'.join(f['terms']['design'][:3]) or '研究设计类型', 'years': '、'.join(f['years']) or '材料未限定'}
    extra = {'conflict': ['however', 'inconsistent', 'no difference', 'limitation', '冲突', '不一致'], 'gap': ['future', 'unclear', 'remain', 'not reported', '空白', '尚不清楚']}
    S = []
    for r in C.sqtpl():
        if r['when'] == 'compare' and (not f['compare']):
            continue
        s = dict(r)
        for k, v in rep.items():
            s['question'] = s['question'].replace('{%s}' % k, v)
        b = f['entities'][:4] + f['terms']['outcome'][:3] + f['terms']['mechanism'][:3] + f['terms']['design'][:3] + f['years'][:3] + extra.get(s['type'], []) + [w for w in C.re.findall('[a-zA-Z][a-zA-Z\\-]{3,}', q) if w.lower() not in C.STOP][:8]
        seen, terms = (set(), [])
        for x in map(nu, b):
            if x and x.lower() not in seen:
                seen.add(x.lower())
                terms.append(x)
        s['ask_terms'] = terms[:16]
        S.append(s)
    dep, done, waves = ({s['id']: set(s['deps']) for s in S}, set(), [])
    while dep:
        rdy = [k for k, v in dep.items() if not v - done] or list(dep)
        waves.append(rdy)
        done |= set(rdy)
        for k in rdy:
            dep.pop(k)
    P = []
    for wi, w in enumerate(waves, 1):
        for sid in w:
            s = next((x for x in S if x['id'] == sid))
            P.append({'sq': sid, 'wave': wi, 'mode': 'sequential' if wi == 1 else 'parallel', 'queries': [' AND '.join(('"%s"' % t if ' ' in t else t for t in s['ask_terms'][:4])), ' OR '.join(s['ask_terms'][:6])], 'source_scope': 'provided_corpus_only', 'depends_on': s['deps'], 'executed': False, 'hits': 0, 'stop_condition': '新增支持性段落<2 / 遍历完毕 / 达候选上限'})
    return (S, P)

def snap(out, status, extra=None):
    return C.snapshot(out, {'case_id': SN.get('case_id'), 'question': Q, 'qsrc': QSRC, 'contract': SN.get('contract'), 'alias': ALIAS}, status, extra)

def stage_plan(inp, out, budget, topk):
    stale = Path(out).parent / 'work' / 'synthesis.json'
    if stale.is_file():
        stale.replace(stale.with_name('synthesis.stale.json'))
        C.CHGS.append({'stage': 'plan', 'change': 'stale synthesis.json quarantined as synthesis.stale.json'})
    files = C.disc(inp)
    if not files:
        C.ERRS.append({'stage': 'plan', 'error': 'no material files under input'})
        C.PEND.append({'item': 'no_material', 'why': 'input has no readable file', 'action': 'add materials'})
    meta = [f for f in files if Path(f['rel']).name.lower() in ('case.json', 'task.md')]
    srcs, pas, idf = C.index([f for f in files if f not in meta], budget)
    srcs += [dict(f, source_id='s%d' % (len(srcs) + i + 1), parse_status='meta', n_passages=0,
                   parse_note='instruction/input descriptor, excluded from evidence corpus')
              for i, f in enumerate(meta)]
    S, P = plan(Q or '材料未提供明确研究问题', C.fac(Q))
    cands, cov = ([], [])
    for s in S:
        if time.time() - C.T0 > budget:
            C.DEGS.append({'stage': 'retrieve', 'degradation': 'budget reached; %s skipped' % s['id']})
            cov.append({'sq': s['id'], 'hits': 0, 'status': 'budget_skipped'})
            continue
        hits, qt = C.ret(pas, idf, s['ask_terms'], topk)
        row = {'sq': s['id'], 'query_terms': qt, 'hits': len(hits), 'status': 'covered', 'candidate_ids': []}
        for sc, p, h in hits:
            cands.append({'candidate_id': 'E%02d' % (len(cands) + 1), 'sq': s['id'], 'source_id': p['sid'], 'source_path': p['src'], 'locator': p['locator'], 'quote': C.bq(p, h), 'matched_terms': h[:8], 'score': round(sc, 3), 'passage_id': p['pid'], 'origin': 'auto_retrieval'})
            row['candidate_ids'].append(cands[-1]['candidate_id'])
        if not hits:
            row['status'] = 'empty'
            C.PEND.append({'item': 'sub_question_no_evidence:%s' % s['id'], 'why': 'no passage matched', 'action': 'report as gap, do not conclude'})
        cov.append(row)
        for pl in P:
            if pl['sq'] == s['id']:
                pl['executed'], pl['hits'] = (True, len(hits))
    wj(Path(out) / 'evidence_candidates.json', {'candidates': cands, 'note': 'quotes are verbatim passage substrings; locator = file + unit'})
    wj(Path(out) / 'source_index.json', {'sources': srcs, 'passages': [{k: p[k] for k in ('pid', 'sid', 'src', 'locator', 'text')} for p in pas]})
    (Path(out) / 'tool_calls.jsonl').write_text('\n'.join((json.dumps(c, ensure_ascii=False) for c in C.CALLS)), encoding='utf-8')
    empty = [r['sq'] for r in cov if not r['hits']]
    return {'sub_questions': S, 'search_plan': P, 'sources': srcs, 'evidence_matrix': cands, 'artifacts': ['evidence_candidates.json', 'source_index.json', 'tool_calls.jsonl'], 'coverage': {'n_sub_questions': len(S), 'n_covered': len(S) - len(empty), 'empty_sub_questions': empty, 'coverage_rate': round((len(S) - len(empty)) / max(1, len(S)), 3), 'n_sources': len(srcs), 'n_parsed': sum((1 for s in srcs if s['parse_status'] == 'ok')), 'unparsed_sources': [s['rel'] for s in srcs if s['parse_status'] != 'ok'], 'n_passages': len(pas), 'n_candidates': len(cands), 'n_tool_calls': len(C.CALLS), 'n_queries': sum((len(p['queries']) for p in P)), 'per_sub_question': cov}}

def finalize(inp, out, work, synp):
    out, syn = (Path(out), {})
    for p in ([Path(synp)] if synp else []) + [Path(work) / 'synthesis.json', out / 'synthesis.json']:
        if p.is_file() and (rd(p, {}) or {}):
            syn = rd(p, {})
            C.CHGS.append({'stage': 'finalize', 'change': 'synthesis from %s' % p})
            break
    if syn.get('case_id') and SN.get('case_id') and str(syn['case_id']) != str(SN['case_id']):
        C.ERRS.append({'stage': 'finalize', 'error': 'synthesis case_id mismatch: %s' % syn['case_id']})
        syn = {}
    if not syn:
        C.ERRS.append({'stage': 'finalize', 'error': 'no synthesis.json; evidence ledger only'})
    prev = rd(out / 'result.json', {}) or {}
    srcs = (rd(out / 'source_index.json', {}) or {}).get('sources') or [dict(f, source_id='s%d' % (i + 1), parse_status='unparsed', n_passages=0) for i, f in enumerate(C.disc(inp), 1)]
    texts, rel = ({}, {})
    for s in srcs:
        u, st, note = C.parse({'path': s['path'], 'rel': s.get('rel'), 'kind': s.get('kind')})
        texts[s['source_id']], rel[s['source_id']] = (u, s.get('rel'))
        s['parse_status'], s['parse_note'], s['reverified'] = (st, note, True)
    cmap = {c['candidate_id']: c for c in (rd(out / 'evidence_candidates.json', {}) or {}).get('candidates', [])}
    sqs = prev.get('sub_questions') or []
    for s in syn.get('sub_questions') or []:
        sid = str(s.get('id') or 'SQ-L%d' % (len(sqs) + 1))
        if sid not in {x['id'] for x in sqs}:
            sqs.append({'id': sid, 'type': s.get('type', 'agent_added'), 'question': s.get('question', ''), 'deps': s.get('depends_on', []), 'evidence_req': s.get('evidence_req', 'Agent 补充'), 'origin': 'agent_refined'})
            C.CHGS.append({'stage': 'finalize', 'change': 'sub-question added: %s' % sid})
    claims, rows, cites, cidx = ([], [], [], {})
    for i, c in enumerate(syn.get('claims') or [], 1):
        cid, ev = (str(c.get('claim_id') or 'C%d' % i), [])
        for e in c.get('evidence') or []:
            e = {'candidate_id': e} if isinstance(e, str) else e
            if not isinstance(e, dict):
                continue
            sid, q = (e.get('source_id') or e.get('src'), e.get('quote', ''))
            cm = cmap.get(str(e.get('candidate_id') or ''))
            if not sid and cm:
                ev.append(dict(cm, quote_match='strict', support_type=e.get('support_type', 'support')))
                continue
            if not sid:
                C.ERRS.append({'stage': 'finalize', 'error': '%s: evidence lacks source_id' % cid})
                continue
            tier, loc = C.quote_tier(q, texts.get(sid, []))
            if tier == 'none':
                C.ERRS.append({'stage': 'verify_quote', 'error': '%s: quote not in %s: %r' % (cid, sid, nu(q)[:60])})
                C.PEND.append({'item': 'unmatched_quote:%s' % cid, 'why': 'not verbatim in %s' % sid, 'action': 'supply a verbatim passage or drop the claim'})
            ev.append({'candidate_id': e.get('candidate_id'), 'source_id': sid, 'source_path': rel.get(sid), 'locator': e.get('locator') or loc or 'unknown', 'quote': nu(q), 'quote_match': tier, 'support_type': e.get('support_type', 'support')})
        st = c.get('strength') if c.get('strength') in STR else 'insufficient'
        if st != 'insufficient' and (not any((r['quote_match'] != 'none' for r in ev))):
            C.CHGS.append({'stage': 'finalize', 'change': '%s -> insufficient (no verified quote)' % cid})
            st = 'insufficient'
        nums = []
        for r in ev:
            if r['quote_match'] == 'none':
                continue
            k = (r['source_id'], r['locator'], nu(r.get('quote'))[:100])
            if k not in cidx:
                cidx[k] = len(cidx) + 1
                cites.append({'n': cidx[k], 'source_id': r['source_id'], 'source_path': r.get('source_path'), 'locator': r['locator'], 'quote': r.get('quote'), 'quote_match': r['quote_match'], 'used_by': []})
            cites[cidx[k] - 1]['used_by'].append(cid)
            nums.append(cidx[k])
        claims.append({'claim_id': cid, 'sq': c.get('sq'), 'claim': c.get('text') or c.get('claim'), 'strength': st, 'citations': sorted(set(nums)), 'conditions': c.get('conditions'), 'limits': c.get('limits'), 'quote_failures': [r['quote'][:60] for r in ev if r['quote_match'] == 'none']})
        rows += [{'claim_id': cid, 'sq': c.get('sq') or '', 'strength': st, 'source_id': r['source_id'], 'source_path': r.get('source_path') or '', 'locator': r['locator'], 'quote': r.get('quote'), 'quote_match': r['quote_match'], 'support_type': r.get('support_type'), 'candidate_id': r.get('candidate_id') or ''} for r in ev]

    def side(k, sn):
        d = k.get(sn) or {}
        return {'label': d.get('label') or sn[-1].upper(), 'position': d.get('position'), 'citations': [n for key, n in cidx.items() if key[0] == d.get('source_id')][:3]}
    conflicts = [{'conflict_id': str(k.get('conflict_id') or 'X%d' % i), 'topic': k.get('topic'), 'side_a': side(k, 'side_a'), 'side_b': side(k, 'side_b'), 'resolution': k.get('resolution') or 'unresolved', 'basis': k.get('basis') or 'unstated'} for i, k in enumerate(syn.get('conflicts') or [], 1)]
    gaps = [{'gap_id': str(g.get('gap_id') or 'G%d' % (i + 1)), 'gap': g.get('gap'), 'basis': g.get('basis') or 'unstated', 'searched': g.get('searched'), 'what_would_close_it': g.get('what_would_close_it')} for i, g in enumerate(syn.get('gaps') or [])]
    gaps += [{'gap_id': 'G-AUTO-%s' % s, 'gap': '子问题 %s 在提供材料中无命中段落' % s, 'basis': 'retrieval_gap', 'searched': '本地词法检索（见 search_plan）', 'what_would_close_it': '补充该子问题材料'} for s in prev.get('coverage', {}).get('empty_sub_questions', []) or []]
    status = ('insufficient_evidence' if not any((c['citations'] for c in claims)) else 'ok' if all((c['citations'] for c in claims)) else 'partial') if claims else 'insufficient_evidence' if srcs else 'input_error'
    rep = C.write_report(out, {'question': Q, 'case_id': SN.get('case_id'), 'status': status, 'facets': C.fac(Q), 'sqs': sqs, 'srcs': srcs, 'claims': claims, 'cites': cites, 'conflicts': conflicts, 'gaps': gaps, 'ncand': len(cmap), 'plan': {'plan': prev.get('search_plan', [])}})
    with (out / 'evidence_map.csv').open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, extrasaction='ignore', fieldnames=['claim_id', 'sq', 'strength', 'source_id', 'source_path', 'locator', 'quote', 'quote_match', 'support_type', 'candidate_id'])
        w.writeheader()
        w.writerows(rows)
    cov = dict(prev.get('coverage', {}), n_claims=len(claims), n_citations=len(cites), n_quoted=len({c['source_id'] for c in cites}), n_conflicts=len(conflicts), n_gaps=len(gaps), n_evidence_rows=len(rows), quote_backlink_rate=round(len([c for c in claims if c['citations']]) / max(1, len(claims)), 3), claims_by_strength={s: sum((c['strength'] == s for c in claims)) for s in STR})
    body = snap(out, status, {'sub_questions': sqs, 'search_plan': prev.get('search_plan', []), 'evidence_matrix': rows, 'citations': cites, 'sources': srcs, 'screening': syn.get('screening', []), 'synthesis': {'claims': claims, 'conflicts': conflicts, 'gaps': gaps}, 'coverage': cov, 'uncertainty': {'conflicts': [c['conflict_id'] for c in conflicts], 'gaps': [g['gap_id'] for g in gaps], 'unparsed_sources': [s.get('rel') for s in srcs if s.get('parse_status') != 'ok'], 'quote_failures': sum((len(c['quote_failures']) for c in claims)), 'limits': syn.get('limits') or ['结论仅覆盖提供材料，不代表领域全量文献', '词法检索对同义改写不敏感']}, 'changes': (prev.get('changes') or []) + C.CHGS, 'artifacts': ['research_report.md', 'evidence_map.csv', 'result.json', 'selfcheck.json', 'evidence_candidates.json', 'source_index.json', 'tool_calls.jsonl'], 'report_path': rep, 'evidence_map_path': str(out / 'evidence_map.csv')})
    body['verification'] = selfcheck(out, texts, claims)
    wj(out / 'result.json', body)
    return body

def selfcheck(out, texts=None, claims=None):
    out, r = (Path(out), rd(Path(out) / 'result.json', {}) or {})
    names, stack = ([], [r.get('output_contract_echo')])
    while stack:
        o = stack.pop()
        if isinstance(o, dict):
            names += [str(k) for k in o]
            stack += list(o.values())
        elif isinstance(o, list):
            stack += o
        elif isinstance(o, str) and len(nu(o)) <= 60:
            names.append(nu(o).strip('`*'))
    names = list(dict.fromkeys(names)) if isinstance(r.get('output_contract_echo'), (dict, list)) else []
    if texts is None:
        texts = {s['source_id']: C.parse({'path': s['path'], 'rel': s.get('rel'), 'kind': s.get('kind')})[0] for s in (rd(out / 'source_index.json', {}) or {}).get('sources', [])}
    cl = claims if claims is not None else (r.get('synthesis') or {}).get('claims', [])
    bad = [x['n'] for x in r.get('citations') or [] if C.quote_tier(x.get('quote'), texts.get(x.get('source_id'), []))[0] == 'none']
    miss = [n for n in names if n not in r]
    chk = {'result_json': bool(r), 'contract_fields': not miss, 'citations_verbatim': not bad, 'status_enum': r.get('status') in ('ok', 'partial', 'insufficient_evidence', 'input_error'), 'report_exists': (out / 'research_report.md').is_file(), 'evidence_csv': (out / 'evidence_map.csv').is_file(), 'claims_cited': all((x['citations'] for x in cl if x.get('strength') != 'insufficient'))}
    res = {'checks': [{'check': k, 'ok': bool(v)} for k, v in chk.items()], 'passed': sum(chk.values()), 'total': len(chk), 'failures': [k for k, v in chk.items() if not v], 'missing_contract_fields': miss[:8], 'unverified_citations': bad[:8], 'n_citations_checked': len(r.get('citations') or [])}
    wj(out / 'selfcheck.json', res)
    return res

def main(argv=None):
    ap = argparse.ArgumentParser(prog='main.py', description='Deep-research runner (research-01): decomposition, retrieval planning, verbatim locators, grounded synthesis, self-check.', epilog='Stages: plan | finalize | check | auto. Always exits 0; result.json exists at every exit.')
    ap.add_argument('--stage', default='auto', choices=['plan', 'finalize', 'check', 'auto'])
    ap.add_argument('--input', default='/input', help='dir with case.json / task.md / materials')
    ap.add_argument('--output', default='/app/output', help='output dir for result.json and deliverables')
    ap.add_argument('--work', default=None, help='work dir (default <output>/../work)')
    ap.add_argument('--budget-seconds', type=int, default=780, help='soft wall-clock budget, seconds')
    ap.add_argument('--top-k', type=int, default=6, help='evidence candidates per sub-question')
    ap.add_argument('--synthesis', default=None, help='path to synthesis.json')
    ap.add_argument('--version', action='version', version='%(prog)s ' + V)
    a = ap.parse_args(argv)
    out = Path(a.output)
    work = Path(a.work) if a.work else out.parent / 'work'
    out.mkdir(parents=True, exist_ok=True)
    global Q, QSRC
    case = {}
    for c in [Path(a.input) / 'case.json'] + sorted(Path(a.input).rglob('case*.json')):
        if c.is_file():
            case = rd(c, None)
            if not isinstance(case, dict):
                C.ERRS.append({'stage': 'load_case', 'error': '%s invalid JSON object' % c.name})
                case = {}
            break
    SN['contract'] = case.get('output_contract')
    SN['case_id'] = next((case[k] for k in ('case_id', 'caseId', 'id', 'caseid', '案例编号') if isinstance(case.get(k), (str, int))), None)
    try:
        if a.stage != 'check' and not (out / 'result.json').is_file():
            snap(out, 'partial')
        Q, QSRC = C.findq(case, C.disc(a.input))
        body = rd(out / 'result.json', {}) or snap(out, 'partial')
        if a.stage in ('plan', 'auto'):
            body = snap(out, 'partial', stage_plan(a.input, out, a.budget_seconds, a.top_k))
        if a.stage in ('finalize', 'auto'):
            body = finalize(a.input, out, work, a.synthesis)
        if a.stage in ('check', 'auto'):
            print(json.dumps(selfcheck(out), ensure_ascii=False)[:1500])
            body = rd(out / 'result.json', body)
        print(json.dumps({'stage': a.stage, 'status': body.get('status'), 'n_claims': len((body.get('synthesis') or {}).get('claims', [])), 'n_citations': len(body.get('citations', [])), 'errors': len(C.ERRS)}, ensure_ascii=False))
    except Exception as e:
        C.ERRS.append({'stage': 'fatal', 'error': str(e)[:500]})
        try:
            old = rd(out / 'result.json', None)
            if isinstance(old, dict) and old.get('status') in ('ok', 'partial'):
                old['errors'], old['pending_human'] = C.ERRS, C.PEND
                wj(out / 'result.json', old)
            else:
                snap(out, 'input_error')
        except Exception:
            pass
        print(json.dumps({'stage': a.stage, 'status': 'input_error', 'error': str(e)[:300]}, ensure_ascii=False))
    return 0
if __name__ == '__main__':
    sys.exit(main())
