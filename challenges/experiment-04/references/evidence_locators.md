# 证据与定位规范（plan-compare v1.0.0）

比较结论要能被第三方复核：每个进入判断的数字或事实，都要能顺着一行证据回到输入文件的确定位置。

## 1. 证据条目

```json
{"id": "E07", "claim": "A_thermal 机时", "value": 28, "source": "case.json",
 "locator": "case.json#/candidate_plans/0/machine_hours", "quote": "28", "kind": "measured"}
```

| 键 | 要求 |
|---|---|
| `id` | `E01`… 顺序稳定，便于在正文引用 |
| `claim` | 一句话说明这条证据支撑什么判断 |
| `value` | 实际参与计算的数值（不是格式化后的字符串） |
| `source` | 源文件名，必须与 `sources[].path` 的 basename 一致 |
| `locator` | `文件名#<JSON Pointer>`，见第 2 节 |
| `quote` | 源文件中**逐字出现**的片段，见第 3 节 |
| `kind` | `measured`（原值）/ `pointer`（结构位置）/ `narrative`（文字描述）/ `limit`（窗口或上限） |

## 2. 定位语法

- JSON 源：`case.json#/candidate_plans/0/materials/0/unit_price`
- 数组中第 n 项：`/…/n`（0 起）；对象键：`/<key>`；键名含 `/` 时按 JSON Pointer 规则转义为 `~1`，`~` 转义为 `~0`。
- 参数窗口：`case.json#/equipment_limits/temp_C`（整块区间）。
- 契约数值：`case.json#/organizer_workorder/budget_cny`，同时登记在 `cost_model.contract_locators`。
- 证据不足时宁可用指向父对象的粗定位（`…/candidate_plans/0`），也不要编造更细的路径。

## 3. 逐字引用规则

1. `quote` 必须能在源文件中按原样检索到（`in` 判定）。数字按原文写法：源写 `480` 就引 `480`，不改成 `480.00`。
2. 不合并、不省略、不翻译、不改写单位；跨行文本截断到 80 字符以内。
3. 从结构推导出来的值（例如"总成本"）不作为 `quote`，改用其分项作为证据：单价行、机时行、费率行分别为三条。
4. 引用不到就给 `unknown`，把"缺证据"写进 `uncertainty`；**绝不能为凑通过而修改源文本**。

## 4. 覆盖要求

- 每个进入硬门判定的数（预算、总成本、周期、机时、参数值）至少一条证据。
- 每个方案至少一条字段定位证据，缺字段本身要作为缺口写明。
- 每个风险条目至少一条 `narrative` 证据。
- 证据条数上限 90，超出截断并在 `degradations` 记一笔。

## 5. 自检行为

`scripts/verify.py` 对每条证据做三件事：源文件是否存在、`quote` 是否逐字命中、证据计数是否与 `counts.evidence` 一致。
命中率 ≥70% 视为通过；未命中的条目写入 `self_check.warnings`，并在 `self_check.passed` 上体现，不静默放过。

## 6. 常见错误

| 错误 | 后果 | 正确做法 |
|---|---|---|
| 引用文献页码但页面内容未核对 | 结论无法复核 | 只引用实际打开读过的位置 |
| 把"理论可行"写成"本实验室可做" | 可行性误判 | 分别记 `feasible_theory` 与 `feasible_now`，后者需设备/耗材/审批证据 |
| 只写"存在风险" | 无法处置 | 每条风险给出触发条件、后果量级、缓解措施、回退路径 |
| 报价单过期仍按原价核算 | 成本失真 | 记录报价日期，超期写入 `pending_human` |
