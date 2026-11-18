# 目标规范映射表（GB/T 7714—2015 / APA 7th）

`reftool.render(record, number, style)` 按本表生成条目；`style` 取 `gbt7714`（默认）或 `apa`。
实现只使用条目中**已经存在**的字段；缺字段写 `[待补]`，不做推断或补造。

## 1. 统一字段模型

| 统一字段 | 来源字段（BibTeX / RIS / CSL-JSON / GB/T 文本） |
|-|-|
| `title` | title / TI,T1 / title / `[J]` 前题名 |
| `authors` | author（`and`、`;` 分隔）/ AU,A1 / author[].family+given / 题名前作者串 |
| `year` | year,date / PY,Y1 / issued.date-parts[0][0] / 年份数字 |
| `container` | journal,booktitle / JO,JF,T2 / container-title / `[J].` 后刊名 |
| `volume` / `issue` / `pages` | volume/number/pages / VL/IS/SP-EP / volume,issue,page / 卷(期): 页 |
| `doi` | doi / DO / DOI / 文中 `10.xxxx/…` |
| `publisher` | publisher,school,institution / PB / publisher / `出版地: 出版者` |
| `url` | url / UR / URL / `https://…` |
| `type_code` | BibTeX 类型、RIS TY、CSL type 统一映射（见 §4） |
| `source` / `line` | 记录来源文件名与起始行（可追溯，不进入渲染文本） |

## 2. GB/T 7714—2015（顺序编码制）

通用骨架：`[序号] 主要责任者. 题名[文献类型标识]. 出处, 年, 卷(期): 起止页. DOI.`

| 类型 | 模板 |
|-|-|
| 期刊 `J` | `[1] 王明, 李强. 镉胁迫对水稻根系生理特性的影响[J]. 农业环境科学学报, 2019, 38(4): 801-808. DOI: 10.11654/jaes.2019.04.011.` |
| 专著 `M` | `[2] 作者. 书名[M]. 出版地: 出版者, 2020.` |
| 会议 `C` | `[3] 作者. 题名[C]//会议录名. 出版地: 出版者, 2020: 12-20.` |
| 学位论文 `D` | `[4] 刘洋. 水稻重金属耐性机理研究[D]. 长沙: 湖南农业大学, 2020.` |
| 报告/标准/专利 `R/S/P` | `[5] 作者. 题名[R]. 出版者, 2021.` |
| 电子资源 `EB/OL` | `[6] 作者. 题名[EB/OL]. (2021)[2024-05-01]. https://…` |
| 其他 `Z` | `[7] 作者. 题名[Z]. 出处, 2021.` |

作者规则（`reftool.au("gbt", r)`）：

- 中文：≤3 人全列，>3 人取前 3 位 + `, 等`。
- 西文：`姓 全大写 + 名首字母（空格分隔、无点）`，如 `ZHANG L`、`HEWITT J A`；>3 人取前 3 位 + `, et al`。
- 英文条目中的 `,` 视为"姓, 名"分隔；无逗号时最后一个词视为姓。

其他规则：

- 页码统一半角连字符 `-`（原文 `--`、`–`、`—` 会被归一）。
- DOI 统一输出 `DOI: 10.xxxx/yyy.`（去 `https://doi.org/` 前缀）。
- 文献类型标识取自条目类型码；缺失时用 `Z`（"其他"），不猜。

## 3. APA 7th（作者—年份制）

| 元素 | 规则 |
|-|-|
| 作者 | `Family, I. N.`；≤20 人全列，最后一人前加 `& `；>20 人列前 19 位 + `... ` + 末位 |
| 年份 | `(2019).`；缺失写 `(n.d.).` |
| 题名 | 句首大写（保留原字符），后接 `.` |
| 期刊 | `*刊名*, 卷(期), 起–止页.`（页码用 en dash `–`） |
| 专著 | `出版者.` |
| DOI/URL | `https://doi.org/10.xxxx/yyy` 或原 URL |
| 正文引注 | `(王明, 2019)`、`(Zhang, 2018)`；同一处多引以 `; ` 分隔 |

示例：

```text
王明, & 李强 (2019). 镉胁迫对水稻根系生理特性的影响. *农业环境科学学报*, 38(4), 801–808. https://doi.org/10.11654/jaes.2019.04.011
ZHANG, L., & CHEN, Y. (2018). Cadmium stress and root activity in rice. *Plant and Soil*, 425(1), 233–245. https://doi.org/10.1007/s11104-018-3601-2
```

说明：中文条目在 APA 下不做拼音转写（无网络、无字典，转写必然出错），保留原字符；如期刊要求拼音，请在交付后人工改写作者字段。

## 4. 文献类型码映射

| GB/T 码 | 含义 | BibTeX 类型 | RIS TY | CSL type |
|-|-|-|-|-|
| J | 期刊论文 | article | JOUR, JFULL | article-journal, article |
| M | 专著/析出 | book, incollection | BOOK, CHAP | book, chapter, monograph |
| C | 会议论文 | inproceedings, conference, proceedings | CONF, CPAPER | paper-conference |
| D | 学位论文 | phdthesis, mastersthesis | THES | thesis, dissertation |
| R | 报告 | techreport | RPRT | report |
| P | 专利 | patent | PAT | patent |
| S | 标准 | standard | STAND | standard |
| N | 报纸 | newspaper | NEWS | newspaper-article |
| DS | 数据集 | — | — | dataset |
| EB/OL | 电子资源 | online | ELEC | webpage |
| Z | 其他 | misc, unpublished | GEN, PREP | preprint, 其他 |

类型码缺省为 `Z`；不使用"看起来合理"的猜测（例如把无类型英文条目直接当 `J`）。

## 5. 中英文混排与标点

- 中文条目用中文逗号分隔责任者与要素，句末用 `.`（与 GB/T 示例习惯一致）；西文条目全部半角。
- `pages` 中的 `--`、`–`、`—`、`~` 统一为 `-`；APA 输出再转 `–`。
- 题名前后的多余空白、`<i>` 等标签会被清理；不做大小写强制转换，避免破坏专有名词。
- 卷期页缺任一项时，模板自动省略对应片段，不会产生 `, ,` 之类的空段。

## 6. 已知边界

1. 不输出"出版地"与"出版者"分离的 GB/T 形式（除非原库字段已含 `出版地: 出版者`）。
2. 不生成 `[引用日期]`（无网络无法确定访问日期），`EB/OL` 条目仅保留 URL。
3. 不做作者消歧（同姓同名不同人）；如需区分，请在原库中写全 `family, given`。
4. 不排序为"著者—出版年制文献表"顺序（APA 正式发表时通常按字母序）；当前按正文首现顺序输出，便于与顺序编码制对照。
