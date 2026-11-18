# 资料库规则表（library-rules）v1.0.0

本文件是 `scripts/curator.py` 的行为规范；改规则先改这里，再改代码常量并升版本号。

## 1. 目录模板

```
library/<project>/<year>/<category>/<canonical_name>
```

| 层 | 取值 | 缺失时 | 可否由代码猜 |
|---|---|---|---|
| `project` | 元数据 `project_code`（`[A-Z]{2,6}-?\d{2,5}(-\d{2,5})?`，如 `PROJ-2023-014`）→ 退 `project` | `_unassigned` | 仅文件名可读的编码，不猜语义项目名 |
| `year` | 文件名四位年（1900–2100，剔除项目号内数字）→ 伴随表 `year` | `_undated` | 不取 mtime 作年份 |
| `category` | 扩展名 + 内容信号 | `07_other` | 见 §2 |
| `canonical_name` | 归一化文件名 | 原名 | 见 §3 |

## 2. 分类规则（category）

| 目录 | 判据 |
|---|---|
| `01_literature` | `.pdf` 且（正文含 DOI 正则 `10.\d{4,9}/\S+` 或 前 2000 字符含 `journal`/`article`/`abstract`） |
| `02_documents` | `.pdf`（其余）、`.doc .docx .odt .rtf .md .txt .tex` |
| `03_tables` | `.csv .tsv .xlsx .xls .ods` |
| `04_figures` | `.png .jpg .jpeg .tif .tiff .svg .eps .gif` |
| `05_code` | `.py .r .m .ipynb .do` |
| `06_archives` | `.zip .tar .gz .tgz .7z .rar .bz2` |
| `07_other` | 其他/未知扩展名（含无扩展名） |

分类只依赖扩展名与可验证的内容信号，**不依赖文件名里的语义词**（如"图""数据""报告"）。

## 3. 命名规则（canonical_name）

1. `unicodedata.normalize("NFC", name)`
2. 控制字符与 `<>:"/\|?*` → `-`
3. 连续空白折叠为一个空格，首尾去空白
4. 总长 ≤120 字符（保留扩展名；主名 ≤100 + 扩展名 ≤20）
5. 空名 → `unnamed`
6. 原始文件名永远保存在 `inventory.csv:filename`，规范化只影响库内路径

**冲突处理（不覆盖）**

| 情形 | 处理 | 记录 |
|---|---|---|
| 目标存在且 sha256 相同 | `action=reuse`，不复制 | `operations.log:reuse` |
| 目标存在且 sha256 不同 | 追加 `__alt1`、`__alt2`… | `integrity_flag=name_conflict` |
| 复制后哈希不符 | 删半成品 | `errors:hash_mismatch_after_copy` + `copy_rollback` |

## 4. 判重与版本策略

**精确重复**：sha256 相同（与文件名、大小、时间无关）。
- 每组保留一份：优先不含 copy 类标记（`copy/副本/(1)/备份/backup`）者，其次名短者，再次路径字典序。
- 其余成员 `action=exact_duplicate`、`dup_of=<keep item_id>`，**不复制、不进版本链**。
- 依据字段 `basis="content_sha256"`；禁止按文件名或大小判重。

**版本链**：`base_key` 相同且 sha256 不同才成链。
- `base_key = 扩展名小写 + "|" + 规范化主名`，规范化时去除 `(1)`、`v\d+(\.\d+)?`、`ver/rev/r+数字`、`final/draft/revised/copy/backup/定稿/最终/修订/草稿/副本/备份`。
- 排序键 `(mtime, 版本号, 文件名)`；版本号：`v3`→3，`final/定稿/最终`→900，`revised/修订`→500，`draft/草稿`→100，`copy`→10。
- 输出 `order`（1..n）、`supersedes`、`superseded_by`、`diff_vs_previous`（两侧都有文本时给行数变化，否则给字节差）。
- 行政批注（`notes`，`source=admin_note`）作为证据保留，但**不覆盖哈希/时间排序**；矛盾时按 §7 上报。
- 扩展名不同视为不同链（`a.csv` 与 `a.xlsx` 不是版本关系），扩展名相同才比较。

## 5. 元数据字段字典

| 字段 | 来源优先级 | `source` | `confidence` | locator 形态 |
|---|---|---|---|---|
| `title` | 伴随表 → 内容首行 | `companion_table`/`content` | high / low | `content:line=1` |
| `authors` | 伴随表 → 内容 | 同上 | high / medium | `<table>:row=N` |
| `year` | 文件名 → 伴随表 | `filename`/`companion_table` | medium / high | `filename#regex:year` |
| `mtime_year` | 文件系统 | `derived` | low | `filesystem:mtime` |
| `project` | 伴随表 → 文件名编码 | `companion_table`/`filename` | high / medium | `<table>:row=N` |
| `project_code` | 文件名 → 伴随表 | `filename` | medium | `filename#regex:project_code` |
| `instrument` | 文件名 → 内容词表 | `filename`/`content` | medium | `content:offset=N` |
| `doi` | 内容 → 文件名 | `content`/`filename` | high | `content:offset=N` |
| `version_label` | 文件名 | `filename` | medium | `filename#regex:version_label` |
| `notes` | case 别名/批注原文 | `admin_note` | high | `$.admin_notes` |
| `data_type` | 伴随表 → 扩展名 | `companion_table`/`derived` | high | `<table>:row=N` |

仪器词表：`LC-MS, GC-MS, ICP-MS, HPLC, XRD, SEM, TEM, NMR, FTIR, Raman, MicroCT, PCR`。

**伴随表识别**：任意 `.json`（非 case）里的 dict 列表，或 `.csv/.tsv` 表；只要某列名匹配 `file|name|path|文件名`，该列值（文件名或路径）即连接键，按 `nk()`（小写、仅保留字母数字与汉字）匹配 `filename` 或 `stem`。
**出处纪律**：抽不到 → 不写该字段；绝不从研究领域标签推断作者、年份、DOI。

## 6. 检索（queries）

输入来自 case 内 `query/search/question/ask/检索/查询/问题` 键（`\b` 边界，跳过 `output_contract` 子树），支持字符串或字符串列表或 `{query,q,text}` 列表。
打分：词元命中文件名 +3、命中路径/元数据 +2、命中抽取文本 +1；中文额外生成 2-gram。返回前 5 条，含 `item_id`、`score`、`matched_terms`、`locator`；`confidence`：最高分 ≥6 为 high，否则 medium，无命中为 `no_match`。这是**检索辅助**，不是语义检索。

## 7. 处置矩阵（不静默跳过）

| 现象 | 检测点 | 处置 | 落点字段 | status 影响 |
|---|---|---|---|---|
| `size==0` | stat | 入清单，标 `empty_file`，跳过哈希比较 | `degradations` | partial |
| 读/stat 失败 | OSError | 入清单 `permission_denied` | `failures.unreadable` | partial |
| 目录不可遍历 | `os.walk onerror` | 记路径，继续其余 | `failures.denied_paths` | partial |
| 扩展名/魔数不符 | 魔数表 | 仍入库 + 标记 | `failures.integrity_suspect` | partial |
| 压缩包/Office 损坏 | zipfile 异常 | 不取文本，仅元数据 | `errors` | partial |
| PDF 无文本层 | 抽取结果为空 | 仅元数据 | `degradations:no_text_layer` | 不变 |
| 复制后哈希不符 | 重算 | 回滚 + 报错 | `errors` + `copy_rollback` | partial |
| 存储不足 | `free < 50MB` | 跳过复制，只写清单/日志 | `degradations:disk_space` | partial |
| 批注/别名目标不存在 | 名称匹配失败 | 保留原文 | `pending_human:admin_or_alias_unresolved` | partial |
| 契约缺失 | 无 `output_contract` | 只写固定键 | `pending_human:contract_missing` | partial |
| case.json 坏 | JSONDecodeError | 空契约继续 | `errors` | input_error |
| 批次为空 | 材料数 0 | 正常收尾 | — | insufficient_evidence |

## 8. 状态机

`ok`：无 errors/degradations/pending_human，且无失败动作。
`partial`：任一上述情形（最保守，宁可标未完成）。
`insufficient_evidence`：批次无材料。
`input_error`：无 case 或 case 不可解析。

## 9. 预算与边界

单文件文本 ≤2MB、总文本 ≤32MB、文件数 ≤4000、PDF 解压流 ≤4MB/文件、CSV 伴随表 ≤2MB、XML 单部件 ≤4MB。超限记 `degradations:bounded_read|bounded_scan`，不中断整体。
