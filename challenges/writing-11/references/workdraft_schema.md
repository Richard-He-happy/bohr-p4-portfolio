# 工作稿 schema 与校验排错（workdraft.json）

本文件是 `scripts/kit.py::validate` 的实现口径。脚本只比对、不改写原文。

## 1. 字段

| 字段 | 类型 | 必需 | 说明 |
|---|---|---|---|
| `case_id` | str | 否 | 与输入一致；缺失时用索引中的 case_id |
| `target_lang` | str | 否 | `"en"` / `"zh"`；缺省时按原文语种与任务说明推断 |
| `glossary` | list | 建议 | `{term, target, locator, note}`；`target` 为空即计入 `pending_human` |
| `paragraphs` | list | **是** | 每项 `{para_id, source_quote, translation, note}`；非空列表才被认作有效工作稿 |
| `change_log` | list | 建议 | `{para_id, action, original_quote, revised_quote, reason, locator}`；`action` 如 `translate`/`term_lock`/`split`/`merge` |

`para_id` 必须来自 `work/index.json`（形如 `M1-P003`：材料号 `M1` + 段序号 `P003`）。笔记可写在 `note`，不影响校验。

## 2. 校验项与判据

| 校验 | 判据（代码口径） | 触发后果 |
|---|---|---|
| 覆盖 | 每个索引段落存在一条 `translation` 非空白的记录；`ratio = covered/expected` | `ratio < 0.999` → `verdict=fail` |
| 空译文 | `translation` 为空白 | 记入 `empty_translations`，fail |
| 重复/未知 id | 同一 `para_id` 出现多次；或 id 不在索引中 | `duplicate_para_ids`/`unknown_para_ids` → fail |
| 引文 | `source_quote` 与原文做空白归一化（`\s+`→单空格，去首尾，NBSP/全角空格视为空格）后忽略大小写求子串 | 不在原文中 → `quote_issues`，fail。**不得改原文以凑通过** |
| 数字 | 用 `\d+(?:[.,]\d+)*` 抽 token，去千分位逗号后做集合包含比较 | 译文缺任一 token → `number_issues`，fail |
| 单位 | 原文含单位（mg、mL、°C、min、kPa… 见 `kit.UNIT`）而译文完全不含单位 | 记为 `number_issues`（`missing=["unit:mg"]`），fail |
| 引用标记 | `[12]`、`[3,4]`、`(Zhang, 2019)` 等整体原样出现在译文 | 缺失 → `citation_issues`，fail |
| 术语 | 术语 `term` 出现在该段原文，则 `target` 必须出现在该段译文；英文按前 6 字符前缀容忍词形变化（photocatalysis / photocatalytic） | 不一致 → `term_issues`，fail |

`verdict=pass` 需要以上全部通过。`check` 只读不写工作稿，报告同时落到 `work/check_report.json`。

## 3. 常见失败与处置

| 报告 | 原因 | 处置 |
|---|---|---|
| `coverage 5/6` + `missing: M1-P004` | 漏译图注/参考文献条目 | 补一条 `paragraphs`，译题注编号与原条目 |
| `quote not verbatim` | 引文抄写有误、跨段拼接、改动了标点 | 换成该段内真实存在的连续子串（取句首 10–30 字即可） |
| `numbers [12.5]` | 数字被四舍五入、换成中文数字或删去 | 原样写回 `12.5`；若原文用“万/亿”，换算值写在 `note`，正文保留换算后的等值数字并注明 |
| `numbers ["unit:mg/L"]` | 只译了数值没有单位 | 补回单位，不做单位换算 |
| `cites ["[12]"]` | 引用标记被改写为脚注或删除 | 原样补回 `[12]`；体例差异只改括号形式 |
| `terms 光催化 → photocatalysis` | 该段用了别的译名（如 `photo-catalysis`） | 统一为术语表译名；确需变体则在 `glossary.note` 说明并保持全篇一致 |
| `unknown_para_id M1-P007` | 索引重建后 id 变了 | 重新 `init` 后按新 id 对齐；或 `show --all` 核对 |

## 4. 多文件与重跑
- 工作稿可拆成多个 `draft*.json`；脚本按文件名与 `paragraphs` 非空挑选，`workdraft.json` 优先。
- `work/workdraft.template.json` 是 init 生成的空骨架，**不参与**校验（文件名含 `template` 会被跳过），不要直接改它当工作稿。
- `build` 永远会跑完：工作稿缺失时用骨架兜底（译文槽写 `[待译 / PENDING TRANSLATION]`），`status=partial`，缺口记入 `pending_human`。
