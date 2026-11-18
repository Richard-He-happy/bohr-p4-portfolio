# 输入 / 输出契约 · v1.0.0

## 1. 输入布局（可能出现的文件）

```
/input/
  case.json                # 权威入口；键名不固定
  task.md                  # 题面
  artifacts/               # 检索响应、题录、参考图谱、查询日志
    queries.jsonl
    responses/*.json
    records.jsonl
    reference_graph.json
    citations.jsonl
    material.json
    schema.json
    config.yaml
  seed_papers/*.pdf        # 种子全文
  *.pdf / *.docx / *.csv / *.xlsx / *.png
```

## 2. 语义键识别（键名不固定时按同义词命中）

| 语义 | 可接受的键名（小写比较，忽略 `_`/`-`） |
|---|---|
| 案例标识 | `case_id` `caseid` `id` `task_id` |
| 任务说明 | `task_instruction` `instruction` `task` `prompt` `question` `task_description` |
| 输出契约 | `output_contract` `contract` `expected_output` `output_schema` |
| 范围约束 | `organizer_supplied_scope` `scope` `constraints` `search_scope` |
| 主题 | `topic` `subject` `theme` `research_question` `keywords` |
| 数据库 | `db` `databases` `sources` `indexes` |
| 年份 | `years` `year_range` `time_span` `from_year`/`to_year` |
| 语言 | `lang` `language` `languages` |
| 纳入/排除 | `include` `exclude` `include_criteria` `exclude_criteria` |
| 种子 | `seeds` `seed_papers` `seed_dois` `known_items` |
| 上限 | `max_k` `top_k` `limit` |
| 材料清单 | `materials` `artifacts` `formal_inputs` `runtime_files` `files` |

`output_contract` 若为字符串（如 JSON 字符串或逗号分隔键名），先尝试 `json.loads`，失败则按 `,`/换行切分成键名列表。

## 3. 支持的文献记录形态（脚本按结构识别，不靠文件名）

1. **Crossref**：`{"message":{"items":[{ "DOI","title":[...],"author":[{"family","given"}],"issued":{"date-parts":[[2020,1]]},"container-title":[...],"abstract","URL"}]}}`
2. **EuropePMC**：`{"hitCount":N,"resultList":{"result":[{"id","doi","title","authorString","pubYear","journalTitle","abstractText"}]}}`
3. **裸列表**：`[{"title":..., "doi":..., "year":...}, ...]`
4. **JSONL**：每行一条记录（`records.jsonl` / `citations.jsonl`）
5. **查询日志**：`{"query":"...","db":"...","hits":12,"status":"ok","retrieved_at":"..."}` 或 JSONL
6. **参考图谱**：`{"nodes":[{...}],"edges":[{...}]}` 或 `{"references":[...]}` —— 只用于候选补全与来源标注，不臆造被引文献
7. **PDF/DOCX/TXT/MD**：正文来源；PDF 侧邻的 `*.json`/`*.txt` 若存在，用于题录补全

识别算法：深度遍历 JSON，凡字典同时含"标题类键"与以下任一（DOI / 年份 / 作者 / 摘要 / 期刊）即视为文献记录；字段值支持 `str`、`list[str]`、`{"family","given"}`、`{"date-parts"}`、`{"value"}` 多种形态。

## 4. 契约回填算法（result.json）

```text
template = build(output_contract)
  dict  -> {k: default(v)}      list -> []      str/num/bool -> null
default(v):  dict->{}, list->[], else null

for key in template:
    semantic = normalize(key)              # 去大小写与分隔符
    if semantic matches known group:       # 见 §5 映射
        template[key] = value_from_group(semantic)
    else:
        unfilled.append(key)               # keep null / []
result = {**standard_keys, **template_overrides}
result["output_contract"]      = template      # 逐字段回填
result["output_contract_echo"] = deepcopy(input_contract)   # 原文保留
result["output_contract_unfilled"] = unfilled
```

原契约中出现的键**一律保留**，不删、不改名、不合并。已知组映射到真实结果；未知键保持 `null`/`[]` 并在 `output_contract_unfilled` 登记（这比编一个值更可核验）。

## 5. 语义键 → 结果映射

| 语义组 | 触发词（normalize 后包含即命中） | 填入 |
|---|---|---|
| 候选集 | `candidate` `papers` `records` `literature` `articles` `items` `results` `searchresult` | `candidates` |
| 检索日志 | `quer` `log` `searchhistory` `trail` `trace` | `queries` |
| 筛选 | `screen` `filter` `selection` `included` `excluded` | `screening` |
| 覆盖/遗漏 | `coverage` `gap` `missing` `recall` `limitation` | `coverage` |
| 评价 | `apprais` `assess` `quality` `grade` `evaluat` `critique` `bias` `risk` | `appraisal_items` |
| 文档级等级 | `overall` `summary` `verdict` `docgrade` | `grades` |
| 引用/聚类 | `citation` `cluster` `graph` | 有输入则填，否则 `[]` |
| 状态 | `status` `state` | `status` |
| 不确定/备注 | `uncertain` `note` `remark` `comment` | `uncertainty` |

## 6. 输出文件与字段

### `result.json`（必需）

```json
{"case_id":"...","status":"ok|partial|insufficient_evidence|input_error",
 "skill":{"name":"literature-quality-appraisal","version":"1.0.0","rubric_version":"1.0.0"},
 "task":{"instruction":"...","topic":"...","scope":{...},"design_summary":{"rct":1,"cohort":2}},
 "inputs":{"dir":"/input","case_json":"/input/case.json",
           "files":[{"path":"...","role":"pdf_fulltext","bytes":123,"pages":9,"text_source":"pdf:pdftotext","status":"ok"}]},
 "candidates":[{"candidate_id":"c001","title":"...","authors":["..."],"year":2021,"venue":"...",
   "doi":"10.xxxx/yyy","url":"https://...","source_db":"EuropePMC","retrieved_at":"2024-01-02T03:04:05Z",
   "query_id":"q1","relevance_score":4.0,"relevance_reason":"title:statin;abstract:adherence",
   "screening_decision":"include","exclusion_reason":null,"fulltext_available":true,
   "metadata_confidence":"high","flags":[],"provenance":[{"source_file":"artifacts/epmc.json","json_pointer":"/resultList/result/0"}]}],
 "queries":[{"query_id":"q1","db":"EuropePMC","raw":"...","expanded":null,"filters":{},
   "hits":12,"retained":9,"status":"ok","error":null,"retrieved_at":"...","source_file":"artifacts/queries.jsonl","origin":"artifact"}],
 "screening":[{"candidate_id":"c001","decision":"include","criteria":"topic_match;year_in_scope","reason":"..."}],
 "appraisals":[{"doc_id":"d001","candidate_id":"c001","title":"...","doi":"10.xxxx/yyy","design":"cohort",
   "design_confidence":"high","text_source":"pdf:pdftotext","pages":9,"items":21,
   "overall_risk":"some_concerns","confidence":"high","coverage":0.857,
   "per_domain":[{"domain":"selection","grade":"未见迹象","points":0.0,"basis_item_ids":["D1.3"],"applicable":true}],
   "grade_trace":{"applicable":21,"judged":18,"coverage":0.857,"bias_points":1.0,
                  "rule_fired":"R3: bias_points>=1.0","formula":"bias_points = sum(selection=0.0, ...) = 1.0"}},
  {"...":"grades 为同一列表"}],
 "appraisal_items":[{"doc_id":"d001","dimension":"D2","item_id":"D2.4","item_label":"混杂控制与多变量调整",
   "judgment":"reported","evidence_quote":"...","locator_page":5,"locator_section":"Methods",
   "evidence_scope":"methods","quote_verified":"verified","char_start":8123,"probe_hit":["adjusted for"],
   "confidence":"high","human_override":null,"override_reason":null,"adjudication":null}],
 "grades":[{"同 appraisals"}],
 "coverage":{"documents_in_scope":3,"appraised":3,"fulltext":2,"abstract_only":1,"no_text":0,
             "gaps":["abstract_only:1"],"recall_estimate":null,"recall_note":"..."},
 "metrics":{"items_total":63,"items_judged":47,"items_verified":41,"evidence_anchor_rate":0.872,
            "abstain_rows":16,"not_reported_rows":5,
            "dimension_coverage":1.0,
            "naive_reference":{"dimension_coverage":0.2,"evidence_anchor_rate":0.0}},
 "selfcheck":{"contract_keys_resolved":true,"verified_rows_located":true,"unappraisable_reasoned":true},
 "artifacts":{"result":"/app/output/result.json","candidates_csv":"...","appraisal_csv":"...","report":"..."},
 "sources":["..."],"uncertainty":[...],"pending_human":[...],"errors":[...],"degradations":[...],
 "changes":[...],"missing":[...],
 "runtime":{"started_at":"...","finished_at":"...","elapsed_s":1.2,"python":"3.12.4",
            "determinism":{"sha1":"22b9a8294da8b7d3","note":"重跑应得同一 sha1"},
            "budget":{"model_requests":0,"network":false,"deadline_s":780.0}}}
```

### 其余主产物（共 4 个 + result.json）

| 文件 | 说明 |
|---|---|
| `candidates.csv` | `rank,candidate_id,title,authors,year,venue,doi,url,source_db,retrieved_at,query_id,relevance_score,relevance_reason,screening_decision,exclusion_reason,fulltext_available,metadata_confidence,flags`（UTF-8 BOM） |
| `appraisal.csv` | 行级评价表（UTF-8 BOM，Excel 直接打开），17 列，含空列 `human_override,override_reason,adjudication` 供人工原位改写；重跑默认保留已填 override |
| `query_log.json` | `{count, queries:[{query_id,db,raw,filters,hits,retained,status,error,retrieved_at,source_file,origin}]}`；`origin=artifact` 来自输入日志，`record_scan` 为按题录文件生成的补记 |
| `appraisal_report.md` | 人类可读摘要：每文档一行（设计｜风险｜置信｜覆盖率），行级证据细节在 `appraisal.csv` |

`result.json` 内 `grades` 与 `appraisals` 同源（文档级汇总），`candidates.json`/`appraisal.json` 不再单独输出（其内容即 `result.json.candidates` / `.appraisal_items` + `.appraisals`），以减少重复文件与不一致风险。

## 7. 最小示例（**示例，非正式案例结果**）

`/input/case.json`（示例）：

```json
{"case_id":"demo-001",
 "task_instruction":"评价所给文献的研究质量并给出可复核证据",
 "output_contract":{"candidates":[],"queries":[],"appraisal":[],"status":null,"notes":null},
 "organizer_supplied_scope":{"topic":"statin adherence","db":["EuropePMC"],"years":[2015,2024],"max_k":10},
 "artifacts":["artifacts/epmc.json","seed_papers/paper1.pdf"]}
```

`artifacts/epmc.json`（示例，结构同 EuropePMC 检索响应）：

```json
{"hitCount":1,"resultList":{"result":[{"id":"12345","doi":"10.1000/demo","title":"Statin adherence in primary care",
 "authorString":"Doe J, Roe R","pubYear":"2021","journalTitle":"Demo Journal","abstractText":"...","retrieved_at":"2024-01-02T03:04:05Z"}]}}
```

示意输出（示例，非正式案例结果，仅示字段关系）：

```json
{"case_id":"demo-001","status":"ok",
 "candidates":[{"candidate_id":"c001","title":"Statin adherence in primary care","doi":"10.1000/demo",
   "source_db":"EuropePMC","retrieved_at":"2024-01-02T03:04:05Z","query_id":"q1","relevance_score":4.0}],
 "appraisal_items":[{"doc_id":"d001","item_id":"D2.2","judgment":"reported","evidence_quote":"（示意）",
   "locator_page":4,"locator_section":"Results","quote_verified":"verified"}],
 "output_contract":{"candidates":["<已回填>"],"queries":["<已回填>"],"appraisal":["<已回填>"],
                    "status":"ok","notes":[]},
 "output_contract_unfilled":[], "selfcheck":{"contract_keys_resolved":true,"verified_rows_located":true},
 "runtime":{"determinism":{"sha1":"..."}}}
```

示例中的标题、DOI、页码均为**占位示意**，不代表任何真实文献。
