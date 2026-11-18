# 号码规范化、字段口径与法律状态规则

本文件是 `ptcore.nn()` / `ptcore.hdr()` / `ptcore.legal()` 的**规则说明书**，也是人工复核时的口径表。
一切判断以"材料里逐字有什么"为准；规则只用于**解析与标注**，不用于补全。

## 1. 号码解析输出的口径

| 字段 | 含义 | 取值 |
|---|---|---|
| `country` | 两位局别代码 | `US/WO/EP/CN/JP/KR/DE/GB/FR/TW/…`，无法识别为 `null` |
| `number_kind` | 号码**类型**（不是权利状态） | `publication` 公开、`grant` 授权、`application` 申请、`pct_application` PCT 申请、`unknown` |
| `role` | 该号码在**本条记录字段**里的角色 | `publication/application/grant/priority`（来自字段名，如 `priority_number`） |
| `kind_code` | 文献种类代码 | `A/A1/A2/B1/B2/C/U/Y/S/E/H/T` 等 |
| `digits` | 去掉分隔符后的数字串 | 仅数字 |
| `year` | 能确定时给出（公开年/申请年） | 4 位 |
| `canonical` | `国家+数字+种类代码`，如 `US10123456B2` | 用于展示与比对 |
| `stem` | `国家+数字`，如 `US10123456` | **去重用**（同族连边只用申请号/优先权号） |
| `valid_format` | 位数是否在 4–13 的合理区间 | 布尔 |
| `warnings` | 解析告警（不阻断） | 见 §5 |

## 2. 主要局别的常见形态

| 局 | 形态 | 解析要点 |
|---|---|---|
| US 公开 | `US 2019/0123456 A1` | 11 位=年(4)+流水(7)；`number_kind=publication` |
| US 授权 | `US 10,123,456 B2` | 7–8 位；`number_kind=grant`；**B2 只说明"授权后公开过申请"，不是"现在有效"** |
| US 申请 | `US 16/123,456` | 系列号(≤2 位)/流水号(6–7 位)；`number_kind=application` |
| WO | `WO 2019/123456 A1` | 年(4)+流水(6)；`publication`；A1 有检索报告、A3 仅是检索报告 |
| EP | `EP 3 456 789 A1` / `EP 3456789 B1` | 7–8 位；B1 授权、C 异议期结束 |
| CN | `CN 110123456 A` / `CN 201910123456.7` | 9 位为公开；12–13 位为申请（末位校验位合并时会告警） |
| JP | `JP 2019-123456 A` / `JP 6543210 B1` | 年+6 位为公开；7 位为授权 |
| PCT | `PCT/US2018/012345` | 记为 `pct_application`，`warnings=["pct_application_not_a_publication"]`；**不得**当公开号使用 |

不同局的写法差异（空格、逗号、斜杠、连字符）都在解析前统一去除；`kind_code` 缺失只告警 `no_kind`，不阻断。

## 3. 种类代码（kind code）的含义边界

| code | 含义 | 可否当"有效" |
|---|---|---|
| A / A1 / A2 | 申请公开（A1 附检索报告、A2 无检索报告） | 否 |
| A3 | 单独公布的检索报告 | 否 |
| B1 / B2 | 美国授权（B1 无前置公开、B2 有前置公开） | 否——只说明"已授权公开" |
| C | EP 授权且异议期结束 | 否——年费/无效仍可能改变状态 |
| U / Y | 实用新型 | 否——保护期与年费另计 |
| S / P | 外观 / 植物 | 否——保护客体不同 |
| E | 再颁（reissue） | 否 |
| H | 法定发明登记（SIR） | 否——不可执行 |
| T | 仅译文 | 否 |

**本 Skill 的唯一规则**：kind code 只填 `stage_hint` / `kind_code_hint`，并在文本中写明"publication stage only, never a validity finding"。

## 4. 法律状态：三档核验与词表

`legal()` 的判定顺序：

1. 状态文本 + **官方域名** URL → `sourced_official_register`（`confidence=medium`，以材料所载状态日为准）。
2. 只有状态文本 → `secondary_or_unknown_provenance`（`confidence=low`），进 `uncertainty`。
3. 无状态字段 → `not_in_corpus`（`confidence=none`），进 `pending_human`。

官方域名白名单：`uspto.gov`、`epo.org`、`wipo.int`、`cnipa.gov.cn`、`j-platpat`、`jpo.go.jp`、`kipris.or.kr`、`dpma.de` 等。
聚合站（如 patents.google.com、lens.org、freepatentsonline）**不在**白名单内：可作检索线索，不作登记依据。

状态词归一（中英混写均可命中，命中即映射，未命中记 `unrecognised` 并保留原文）：

| 归一值 | 命中词（示例） |
|---|---|
| granted | grant / issued / in force / 授权 / 有效 |
| pending | pending / 审查中 / 审中 |
| published | published / 公开 |
| withdrawn | withdrawn / 撤回 |
| refused | refused / rejected / 驳回 |
| expired | expired / 期限届满 / 失效 |
| lapsed | lapsed / 未缴费 |
| revoked | revoked / 无效 / 撤销 |
| abandoned | abandoned / 放弃 |

冲突：同一号码出现多个归一值 → `uncertainty[id=status_conflict:<number>]`，处置为"按登记查询日期定序，不得取平均、不得择一当结论"。

## 5. 告警（warnings）字典

| 告警 | 含义 | 建议动作 |
|---|---|---|
| `no_kind` | 无种类代码 | 到登记库确认文献类型 |
| `no_prefix` | 无可识别的局别前缀 | 让用户确认局别，勿猜 |
| `checkdigit` | CN 等末位校验位被并入 | 展示时保留原写法 |
| `pct_application_not_a_publication` | PCT 申请号不是公开号 | 换用公开号检索 |
| `role_vs_parsed_<kind>` | 字段名角色与解析类型不一致 | 以登记库著录为准 |
| `empty` | 空号码 | 视为字段缺失 |

## 6. 官方登记入口（人工复核用）

| 局 | 入口 |
|---|---|
| US | USPTO Patent Center（https://patentcenter.uspto.gov/）、Patent Public Search（https://ppubs.uspto.gov/pubwebapp/）、转让记录（https://assignment.uspto.gov/） |
| EP | EPO Register（https://register.epo.org/） |
| WO | WIPO PATENTSCOPE（https://patentscope.wipo.int/） |
| CN | CNIPA 专利检索（https://epub.cnipa.gov.cn/） |
| JP | J-PlatPat（https://www.j-platpat.inpit.go.jp/） |
| KR | KIPRIS（https://www.kipris.or.kr/） |

复核时逐号码记录：状态、状态生效日、**查询日**、族成员口径（simple/extended）、权利要求版本来源。
本 Skill 不代替上述查询，也不会在缺少这些记录时给出状态结论。

## 7. 同族口径

- `observed_links_only`：只用材料里**实际出现的**优先权号/申请号连边（并查集）。
- 未连边 ≠ 无族：缺 INPADOC simple family / DOCDB extended family 数据时，只能说"在给定语料内未观测到连接"。
- 连通不等于权利要求范围相同：`claim_scope_note` 永远写明 "links only; NOT equal claim scope"。
- 成员缺失不等于不存在：`caveat` 写明 "absence != proof"。
