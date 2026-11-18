# 数据源字段映射与失效处理

本 Skill 不联网。它消费的是本案保留的引文记录——通常是接口响应的落盘副本。下表是 `citelib` 实际识别的字段；匹配时忽略大小写、下划线与连字符差异（`getf()` 归一化），所以 `container-title`、`container_title`、`ContainerTitle` 等价。

## 1 Crossref `works` 记录

| 语义 | 字段 | 备注 |
|-|-|-|
| DOI | `DOI` | 规范化为小写、去 `https://doi.org/`、去尾标点 |
| 题名 | `title`（数组或字符串） | 取首元素 |
| 作者 | `author[].family` + `given` | 输出 `Family, Given` |
| 年份 | `issued.date-parts[0][0]`，回退 `published-print` / `published-online` / `created` | 正则取 4 位年份 |
| 期刊 | `container-title` | |
| 摘要 | `abstract` | 常带 JATS 标签，已去标签 |
| 类型 | `type`（`journal-article` / `posted-content` / `proceedings-article`） | 用于 `preprint`、`conference_version` 标记 |
| 后向引用 | `reference[]`（元素含 `DOI` / `article-title` / `year` / `unstructured` / `key`） | `key` 是本地编号，**不作为标识** |
| 前向计数 | `is-referenced-by-count` | 只是计数，不含列表；本 Skill 不据此造边 |

## 2 EuropePMC

| 语义 | 字段 |
|-|-|
| 标识 | `id`（配 `source` 判类型：`MED` → PMID）、`doi`、`pmid`、`pmcid` |
| 题名 | `title` |
| 作者 | `authorList.author[]`（`fullName` / `lastName`）或 `authorString`（`A B, C D` 形式，按 `;`/`and` 切分） |
| 年份 | `pubYear` |
| 期刊 | `journalInfo.journal.title` / `journalTitle` |
| 摘要 | `abstractText` |
| 后向引用 | `/references` 响应的 `referenceList.reference[]` |
| 前向引用 | `/citations` 响应的 `citationList.citation[]`（元素本身就是施引文献） |
| 计数 | `citedByCount`、`referenceCount` |

注意：EuropePMC 的 `source` 字段是库名，不是"施引方"，不会被当成边的一端。

`referenceList.reference[]` 的元素常用 `id` 而非 `doi` 承载被引标识（形如 `10.1000/x`、`DOI:10.1000/x`、`27129234`）。`key_of_item()` 对这类只带 `id` 的对象会先试 DOI，再试 OpenAlex/arXiv/PMID 规则；`id` 为空或无法识别时该引用条目被跳过，并在 `missing` 的未解析边计数中体现，不会伪造边。

## 3 OpenAlex

| 语义 | 字段 |
|-|-|
| 标识 | `id` → `Wxxxx`；`doi` |
| 题名 | `display_name` |
| 作者 | `authorships[].author.display_name` |
| 年份 | `publication_year` |
| 来源 | `primary_location.source.display_name` |
| 后向引用 | `referenced_works[]`（OpenAlex URL 数组） |
| 计数 | `cited_by_count`、`referenced_works_count` |

`referenced_works` 只有 id，因此被引作品会以"仅标识"的 stub 记录进入图，`metadata_confidence=low`。

## 4 Semantic Scholar

| 语义 | 字段 |
|-|-|
| 标识 | `paperId`；`externalIds.DOI` / `ArXiv` |
| 题名 | `title` |
| 作者 | `authors[].name` |
| 年份 | `year`，期刊 `venue` |
| 后向/前向 | `references[]` / `citations[]`（元素是论文对象） |

## 5 通用兜底

任何未列出的 schema，按语义找键：题名 `title/article-title/display_name/orig_title`；年份 `year/pubYear/publication_year/issued/published-print/published-online/published/publication_date/date/created`；作者 `author(s)/creators/authorList/authorships/contributors`；来源 `container-title/journal/journalTitle/venue/source_title/publication/primary_location/host_venue`；后向 `reference(s)/bibliography/referenced_works`；前向 `citations/cited_by/citing`。

边也可以来自显式对：`citing↔cited`、`from↔to`、`src↔dst`、`source_id↔target_id`、`parent↔child`、`citing_doi↔cited_doi`。为避免误判，这类对只在对象键数 ≤14 且文件名含 cit/ref/edge/graph/link 或对象自带 `relation/direction/database/source_db` 时才采纳。

### 5.1 定界表与自由文本

- `.csv/.tsv`：按表头语义映射。列名含 `citing` 进施引侧，含 `cited` 进被引侧，`doi/id` → DOI、`title` → 题名。两侧 DOI 齐全且不同时，同一行产出**被引工作记录 + 施引工作记录 + 一条 `cites` 有向边**；仅单侧有 DOI 时只登记该侧，不造边。表头无法识别时退化为纯 DOI 抽取；CSV 不承载年份/期刊/作者。
- `.yaml/.yml/.txt/.bib/.ris/.xml`：不做结构化解析，仅按 `10.x/...` 正则抽取 DOI 生成仅标识记录，用于补种子或补边端点；题名与年份不猜测。

## 6 落盘标记

- `retrieved_at`：优先取记录里的 `retrieved_at / fetched_at / retrieved / timestamp / access_date`；都没有则用文件 mtime，并在 `runtime` 中体现。
- `source_locator.file`：相对 `--input` 的路径；`json_pointer`：记录在该文件中的 JSON 路径（JSONL 记 `/行号` 下的路径，CSV 定界表记 `/rows/行号`）。
- `source_db`：按文件路径关键词推断（crossref / epmc、europepmc / openalex / semantic、s2 / pubmed / arxiv / patent），否则 `retained_input`。缓存文件建议保留库名（如 `openalex_responses.json`）；`s2_*.json` 也归到 `semanticscholar`。

## 7 失效与权限

| 情形 | 本 Skill 的行为 |
|-|-|
| 接口无权限 / 未授权抓取 | **不发起请求**。需要在线补检的方向写 `planned_query(status=not_executed, note="offline: retained records only")` |
| 限流（HTTP 429） | 同上：离线环境下不会出现，若输入里带了 429 响应体，其记录解析为空，并在 `degradations` 记一行 |
| 某库只有被引计数、没有列表 | 记入 `coverage.gaps`（该种子前向不可用），不根据计数编造施引文献 |
| 新预印本无前向引用 | `uncertainty.seed_without_forward_citations` |
| 记录字段冲突（题名/年份/期刊不一致） | 主值取置信度最高者，其余来源进 `provenance`；分歧写入 `gaps` 或 `flags` |
| 撤稿 / 更正 | 从题名或摘要文本识别 `retracted / withdrawal / erratum / correction to / expression of concern`，打标记并要求人工核实 |

这些分支的共同原则：**宁可少一条，也不补一条**。空的 `candidates` 配 `status=insufficient_evidence` 是合法且诚实的输出。
