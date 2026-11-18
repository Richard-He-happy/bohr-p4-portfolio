# 方法与运维说明 v1.0.0

## 1. 两段式流水线

```
/input/  ──build_graph.py──▶  graph_raw.json (nodes, edges, sources, paragraph index)
                              result.json  (partial, 契约键已占位)
         ──verify.py──▶       claims.json, queries.md, verify_report.json,
                              nodes.csv, edges.csv, result.json (final)
```

- `build_graph.py`：只做"读材料 → 抽实体/关系 → 归一合并 → 落盘"。不做判断性结论。
- `verify.py`：独立复核（引文是否逐字命中）+ 派生 claim + 执行查询 + 契约终填。
  由 `build_graph.py` 自动调用；也可单独重跑：`python3 verify.py --input /input --output /app/output`。

两段式的好处：抽取逻辑与核验逻辑分离，核验不信任抽取的结论，只信任段落原文。

## 2. 输入发现（语义识别，不假设键名）

1. 读 `<input>/case.json`；缺失时退化为递归扫描。`case_id` 原样保留，`output_contract` 原样保留。
2. 递归扫描输入目录下所有文件，按**扩展名 + 内容**判断类型：
   - JSON：递归找"像段落"的对象——同时具备文本键（`text/body/content/paragraph/sentence/chunk/...`）与 id 键（`paragraph_id/pid/id/key/...`）。沿途收集 `doi/title/section` 作为来源与章节线索。
   - XML/JATS：去 DOCTYPE、去 namespace，抓 `<article-id pub-id-type="doi">`、`<article-title>`、`<sec><title>`、`<p id="...">`。
   - DOCX / 纯文本：按空行切块（段落 id 为合成 id，`degradations` 中标注 `DOCX_SYNTH_PID`）。
   - PDF：无标准库文本层，记 `PDF_UNPARSED` 降级 + `pending_human`，**不猜内容**。
3. `corpus-manifest.json` 只用来补来源元数据（DOI/title/authors/license）与研究者节点；不当作论文正文。
4. 材料未给的对象一律进 `uncertainty`/`pending_human`，不构造。

**同篇多格式去重**：以规范化正文的 sha1 去重，保留优先级最高的文件（`primary-*` > `secondary-*` > 其他 > `material.json` 汇总索引），并写入 `changes`。若 `material.json` 是两篇的汇总索引，则它不会把同一段算两遍。

**来源划分**：段落自带 `doi/source_id` 时用它，否则取正文中出现的 DOI，再次退回文件名。`root DOI/title/authors` 只属于第一篇，绝不套到第二篇。

## 3. 实体抽取

- 候选来源三类：① `graph_rules.json` 的领域词表（大小写不敏感）；② 首字母大写多词短语；③ 全大写缩写与带数字型号。
- 过滤：长度 < 3、stop 词、章节标题词、纯数字；同段落内重叠候选取**最长**、从左到右不重叠。
- 归一化 `nm()`：小写、统一破折号/引号、去标点、压缩空白、去首尾 `. - /`。
- 节点 id 只由规范化 label 决定（`n-<sha1[:8]>`），因此**同一概念在不同论文、不同批次都得到同一 id**，天然支持增量。
- 类型来自词表命中，只作提示；一律标 `type_basis`，不伪装成原文结论。
- 预算：每篇最多 45 个实体（跨篇节点不受限），每篇最多 120 条边。

## 4. 关系抽取（只建"有谓语证据"的边）

1. 段落切句（避免把小数点、缩写切碎）。
2. 句内定位实体命中位置。
3. 对每条 cue 正则：取 cue **左侧最近的实体**为 subject、**右侧最近的实体**为 object，同句中且不同节点才建边。
4. 边的证据 = 该句逐字引文 + 段号 + 句在段内的字符区间；`condition` 记录"该断言只在此段范围成立"。
5. 同一 (subject, predicate, object, source, paragraph) 只出现一次。
6. **同句共现不建边**。共现只是候选线索，永远不会成为证据。

## 5. 别名归一与跨篇对齐

| 情形 | 处理 | 记录位置 |
|-|-|-|
| 规范化字符串相同 | 合并为一个节点，源与别名合并 | `merge.auto_merged`（含 `basis`、`risk`） |
| 大小写/连字符/连写不同 | 视为同一规范化形式，进入 `aliases` | 同上 |
| 同一缩写、不同全称 | **不合并**，保留两个节点 | `merge.non_merge_conflicts`（附双方引文） |
| 出现在两篇论文 | `sources` 有两个值 | `merge.cross_source_nodes` |

**合并的风险声明**：字符串相同只证明"两篇用了同一个术语"，**不**证明同一物理样品、同一数据集、同一模型实例或同一实验条件。该限制写在 `merge.guard` 与每条对齐 claim 的 `not_claimed` 字段里。

## 6. 冲突与人工确认

- 关系层面的对立表述（`contradicts`）单独成边，不做裁决，也不覆盖已有边；冲突在两个方向上都保留证据。
- 数值/条件冲突：本 skill **不做跨篇算术合并**；指标只按来源分别列出。
- 进 `pending_human` 的典型情形：PDF 无法取文本、缺少段落 id 导致定位退化、样品同一性判定、引文核验失败项。

## 7. 查询（每次运行实际执行，不只是模板）

| id | 类型 | 回答什么 | 何时 `no_result` / `undetermined` |
|-|-|-|-|
| Q1 | cross_source_alignment | 哪些实体跨篇出现、合并依据 | 无共享术语 → `no_result`；样品同一性 → `undetermined` |
| Q2 | provenance | 度数最高实体的每条边与原文引文 | 无边则不产出 |
| Q3 | metric_by_source | 各来源的指标节点，声明不可跨篇比较 | 无 metric 节点 → `no_result` |
| Q4 | conflict_detection | 是否存在矛盾表述 | 未检出 → `no_result` + "不等于结论一致" |
| Q5 | sameness_check | 是否同一物理样品/数据集/条件 | 恒为 `undetermined` + 需要什么证据才能定 |
| Q6 | reverse_locate | 给定段号反查该段贡献的节点与边 | 该段无边 → `no_result` |

每条查询都带 `executed: true`、`status`、`answer`、`result_nodes`、`result_edges`、`evidence`（逐字引文 + 定位）、`undetermined`、`limitations`。

## 8. 增量更新

- 节点 id 由规范化 label 决定，不含批次号与序号：新论文进来时命中即复用，不会重编号。
- 新增论文的流程：同规则解析 → 抽取 → 规范化命中已有节点则追加 source 与 evidence → 未命中则新建 → 追加边。
- 冲突证据并存：同一对实体在不同论文里给出相反关系时，保留两条边，各自带各自段号与引文，**不覆盖**。
- `incremental.id_policy` 与 `incremental.on_new_paper` 写进 result.json，供他人按同规则续建。

## 9. 异常与降级分支

| 情形 | 检测点 | 处理 | 落点 |
|-|-|-|-|
| `case.json` 缺失/坏 JSON | build 启动 | 继续递归发现；坏 JSON 记错 | `errors`, `degradations`, `uncertainty` |
| 输入目录不存在 | build 启动 | 写空图 partial | `uncertainty[U-INPUT]` |
| 材料一条也解析不出 | 解析后 | 空图 + `pending_human` | `pending_human[H-NOMAT]`, status=`input_error` |
| 单个文件解析异常 | `pa()` | 只跳过该文件 | `errors[stage=parse]` |
| PDF 无文本层 | `pa()` | 跳过并列出人工项 | `degradations[PDF_UNPARSED]` |
| 段落无组织方 id | 组装 | 生成并**标注**合成 id | `degradations[PID_SYNTHETIC]` |
| 引文核验失败 | verify | 计数、列前 20 条、状态降为 partial | `uncertainty[U-QUOTE]`, `verify_report.json` |
| 查询无结果 | verify | 保留查询、状态 `no_result`，不改写为"没有" | 查询对象内 |
| 任意未捕获异常 | 顶层 | 保留已有 partial result.json，退出码 0 | `errors[stage=fatal]` |

## 10. 自查方法

```bash
python3 -B scripts/build_graph.py --input /input --output /app/output --quiet
python3 -B scripts/verify.py --input /input --output /app/output
```

看四件事：
1. `verify_report.json` 的 `quotes_failed` 是否为 0；
2. `contract_coverage.unmapped_nulled` 是否为空（非空说明契约键没映射上，需人工补）；
3. `graph_summary.edges_per_paper` 两篇是否都非 0（为 0 说明该篇没抽到关系）；
4. `queries` 里是否至少 3 条 `answered`。

## 11. 适用与不适用

- 适用：两篇及以上英文科研论文，提供 JATS/XML、JSON 段落索引或纯文本；需要"实体—关系—证据—查询"闭环的阅读型任务。
- 不适用：需要图像/像素级图注解析（本包不做 OCR 与像素读数）、需要跨篇元分析合并数值、需要 PDF 页码定位。
- 许可与来源：词表为手写通用科学英语种子词，不含任何语料或评测数据；论文内容版权归原作者，本包只做引用级摘录。

## 12. 维护

- 改词表/线索：只改 `references/graph_rules.json`，两个脚本自动读取（路径相对包根，不依赖 CWD）。
- 改字段：`references/schema.md` 与两个脚本必须同步改，字段名是契约。
- 升级版本号时同时改 `SKILL.md` frontmatter 的 `version` 与本文件标题。
