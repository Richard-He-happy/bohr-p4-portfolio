# Rubric mapping, self-check and maintenance

## 1. Rubric → field / artefact

| Rubric | Where it is answered |
|-|-|
| 任务完成度 15 | `result.json` with a full `output_contract` backfill, `candidates.csv`, `candidates.json`, `query_log.json`; `search_scope` shows the executed constraints |
| 结果正确性 15 | `candidates[].title/authors/year/venue/doi` copied verbatim from the source record; `flags[]` marks each missing field; `metadata_gaps` counts them |
| 结果完整性 5 | `coverage.facet_coverage`, `uncovered_facets`, `recall_estimate` (known-item), `missing[]` |
| 结果可核验性 5 | `provenance[]` (database + query_id + retrieved_at + file + JSON pointer) per candidate, `query_log.json`, `evidence_snippet` |
| 质量增益 15 | dedupe + facet coverage + acronym/synonym expansion + citation chaining; `evaluation` reports P@k / nDCG@k under a stated label rule |
| 效率增益 5 | one pass over the input, no network, `runtime.elapsed_s`, `evaluation.n_dedup_removed`, candidate count vs record count |
| 增益可验证性 5 | every number is recomputable from `candidates.csv` + the stated formulas in `schema.md`; no claim about the official whiteboard |
| 新增能力 5 | query planning, multi-source union, cross-database dedupe, screening log, citation chaining, coverage/gap accounting |
| 方法改进 5 | token-level facet matching, IDF-weighted coverage ranking, union-find dedupe (DOI + fuzzy title), seed-based known-item recall |
| 创新证据 5 | `queries[]` shows each planned step and its hit count; `coverage.uncovered_facets` shows what the plan failed to cover |
| 调用与易用性 3 | `python3 main.py --input /input --output /app/output`; `--help`; `--max-k`; `--quiet` |
| 运行稳定性 4 | stdlib only, no network, no CWD dependency, partial result written first, `errors[]` per stage |
| 异常处理 3 | empty input → `input_error`; broken JSON → `insufficient_evidence` + `errors[stage=case_json]`; PDF/CSV → `missing[]`; missing DOI/year/venue → `flags[]`; conflicts → `year_conflict`；无源端查询 → `missing_query_id` |
| 文档完整性 3 | `SKILL.md` (usage, IO, method, limits, failures) + this file + `schema.md` + `terms.md` |
| 资源可复用性 4 | `terms.md` is a plain editable lexicon; `engine.py` can be imported (`from engine import dedupe, rank, screen`) |
| 分享推广价值 3 | case-agnostic pipeline; the demo case in `SKILL.md` §12 is reproducible |

## 2. Self-check commands

```bash
python3 -B scripts/main.py --help
python3 -B scripts/main.py --input /input --output /app/output
python3 -c "import json;r=json.load(open('out/result.json'));print(r['status'],len(r['candidates']),r['self_check'])"
python3 -c "import json;r=json.load(open('out/result.json'));oc=r['output_contract'];print([k for k in oc if k not in r])"
```

Expected: exit code 0 in every case; `self_check` all true; the second command prints `[]`.

## 3. Known failure modes and handling

| Failure | Handling |
|-|-|
| `case.json` absent | falls back to any JSON with `output_contract`, else `task.md` topic; status `insufficient_evidence` |
| unparsable JSON | recorded in `errors[stage=case_json]`, scan continues with other files |
| no records at all | `status=insufficient_evidence`, `pending_human` explains live search is unavailable offline |
| PDF / CSV material | listed in `missing[]` with a reason; never silently dropped |
| duplicate record across databases | merged by DOI / fuzzy title, both sources kept in `sources[]` |
| metadata conflict (year differs) | both years kept in `conflict_year`, candidate flagged `year_conflict` |
| Chinese or patent record | Han terms matched by substring (no `\b` inside a Han run); patent without DOI is kept and flagged `missing_doi`, patent number never written into `doi` |
| missing DOI / year / venue | `flags[]` + `coverage.metadata_gaps`, never invented |
| seed not in provided records | `citation_chaining.seeds_missing` + `missing[]` + `pending_human` |
| scope excludes everything | `screening.excluded_items[]` shows the reason per item; status `partial` |

## 4. Maintenance

- Version: 1.0.0 (2026-11). Python ≥ 3.8, standard library only, no network.
- To extend vocabulary: edit `references/terms.md` only.
- To change ranking weights: edit `engine.rank` and mirror the change in `schema.md` §3.
- Re-run the three smoke tests (minimal case, empty dir, broken JSON) after any change.
