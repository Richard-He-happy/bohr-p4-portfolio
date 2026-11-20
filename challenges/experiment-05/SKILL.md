---
name: experiment-result-anomaly-explainer
description: >-
  围绕“实验结果解释与异常分析”的 Agent Skill。输入 /input/case.json、task.md 和实际实验材料，
  输出 /app/output/result.json 及 protocol.md、anomaly_table.csv、recheck_checklist.csv、
  risk_table.csv 等可复核产物。五段结论：趋势与拐点、异常点定位、可能原因候选、可执行复核步骤、
  下一轮实验建议。脚本提供确定性基线，Agent 负责真实读材料、核验、撰写并补齐 output_contract。
version: 3.0.0
license: MIT
---

# experiment-result-anomaly-explainer

## 0. 目标与最高优先级

每道案例必须把原始实验数据解释成五段可检查结论：

1. **趋势与拐点**：从读数/曲线中给出走势、拐点、平台期、偏离幅度，说明区间、对照与拟合方式。
2. **异常点**：按样本/批次/通道/孔位/时间点定位，给出异常程度、阈值、与对照或重复的关系。
3. **可能原因**：形成按证据强度与可检验性排序的候选清单，标明支持证据、排除证据、相关不等于因果的风险。
4. **复核步骤**：写成第二个人可直接执行的动作：回查文件/sheet/行/列、核对批次/设备日志、补做对照或重复。
5. **后续实验建议**：依据原因候选与证据缺口，给出补对照、加密采样点、调整参数范围、扩大重复数等方案。

同时回填 `output_contract` 全部字段。禁止用预制答案代替实际运行；禁止把脚本骨架直接当成品；禁止脱离实际文件编造数据或来源。

---

## 1. 单命令全流程入口

首次优先执行：

```bash
python3 scripts/main.py run --input /input --output /app/output --work /app/work
```

该命令内部完成：

- `init`：盘点 `/input` 材料、分配来源编号 `S#`、抽取候选数值与冲突分组。
- `build`：校验抽取、写入/渲染全部产物、finalize `result.json`。
- `selfcheck`：按 output_contract 检查产物与字段是否齐全。

退出码必须恒为 `0`。任何异常写入 `errors`/`degradations`/`pending_human`，不中断。启动后先写合法 partial `result.json`，再逐步覆盖为 finalize；时间或请求不足时保留 partial。

如果当前安装的 `main.py` 不接受 `run` 子命令，则使用等价单命令：

```bash
python3 scripts/main.py --input /input --output /app/output --work /app/work
```

不要散乱调用零散脚本。`scripts/analysis.py` 只作为诊断和复核工具，不作为交付入口。

---

## 2. Agent-first 双路径

### 路径 A：Agent 增量高质量路径

1. 先运行一次 E2E 基线命令，得到完整候选产物。
2. 读 `/app/work/inventory.json`、候选抽取结果和 `/input` 全部原始材料。
3. 将判断写入 `/app/work/draft.json`。
4. 再次运行 E2E 命令；主脚本检测到 `draft.json` 后，将 Agent 判断合并进正式产物。
5. 进行 selfcheck，补齐 `agent_review.json` 与 honest gaps。

`draft.json` 至少应包含：

```json
{
  "case_id": "从 /input/case.json 原样读取",
  "trend": [{"claim": "方向/拐点/幅度", "source_id": "S#", "locator": "文件#页/行/列", "quote": "逐字引用", "confidence": "high|medium|low"}],
  "anomalies": [{"index": "样本/批次/通道/时间点", "score": "偏离度量", "threshold": "判定阈值", "source_id": "S#", "locator": "..."}],
  "causes": [{"hypothesis": "...", "strength": "direct|indirect|exclusion_only", "support": ["S#..."], "against": ["S#..."], "testable": true}],
  "recheck": [{"action": "可执行动作", "file_target": "文件/字段", "expected_if_true": "...", "expected_if_false": "..."}],
  "next_experiment": [{"change": "补对照/扩大重复/加密采样/调参", "gap_addressed": "...", "rationale": "..."}],
  "uncertainty": [],
  "pending_human": []
}
```

### 路径 B：无 draft 的确定性兜底

如果 Agent 没有写入 `draft.json`，或只能完成部分 draft，主脚本必须从 init 台账确定性抽取生成实质工作稿：逐字 quote、locator、source_id、可复核数值。此路径允许诚实记录 `AUTO_EXTRACT` 到 `degradations` 和 `gaps`。

两条路径必须产出同一套产物结构和同一份 `result.json` 契约。不允许因为走兜底就删除字段或换格式。

---

## 3. 输入与输出目录

- 输入：`/input/case.json`、`/input/task.md`、题面规定的材料与 artifacts。
- 工作：`/app/work`。
- 最终输出：`/app/output`。

最终输出至少包含：

- `result.json`：主结果与 output_contract 双回显。
- `protocol.md`：假设、变量、对照、步骤、参数、资源、判读标准、风险与确认项。
- `anomaly_table.csv`：异常点明细，含来源 locator。
- `recheck_checklist.csv`：第二人可执行复核清单。
- `risk_table.csv`：依据、风险、异常处置、来源 locator。
- 如 output_contract 要求 Office/幻灯片/图形，须同时提供可编辑文件和真实渲染的 PDF/PNG 预览。
- `agent_review.json`：Agent 核验记录；若未执行 Agent 路径，说明自动兜底。

---

## 4. 材料盘点与来源编号

必须真实读取实际文件，不得依据文件名或领域标签猜测内容。

1. 读 `case.json` 与 `task.md`，提取 `case_id`、`topic`、`domain`、`goal`、`equipment`、`reagents`、`time/budget/personnel`、`output_contract`。
2. 列全 `/input` 下所有材料，按真实类型处理：CSV/TSV/TXT、XLSX/XLSM、PDF、DOCX、图片/图谱。
3. 每个来源分配 `S#`，稳定编号，供引用与回指。
4. `case.json` 缺失或损坏时，先查同级 `case*.json`；仍失败则继续用材料，`case_id` 记 `UNKNOWN`，`status` 记 `partial` 或 `insufficient_evidence`。
5. 无任何可读材料时，仍产出合法 `result.json`，状态 `insufficient_evidence`，不是 failure。

结构化表格：由脚本解析，Agent 抽查数值。  
PDF：调用环境可用的文本提取工具，读全文和表格；PDF 无文本层时如实标 `not-read` 并写 `pending_human`。  
DOCX：读段落和表格。  
图片/图谱：有 OCR/曲线读取工具才提取；否则标 `not-read`。

---

## 5. 证据、locator 与可核验性

每条关键数字、异常定位、原因论断必须能回指到原始材料。

- locator 示例：
  - 表格：`[S3] sample_workbook.xlsx#sheet=Sheet1#row=12#col=3#range=D12:D18`
  - PDF：`[S2] full_paper.pdf#page=4#paragraph=3#line=2`
  - CSV：`[S1] raw_reads.csv#row=7#col=2`
- quote 必须逐字引用，不转述。
- 没有 locator 和 source_id 的断言不得进入正式结论；如暂时无法定位，放入 `uncertainty` 或 `pending_human`。
- 主观判断须写参考答案、来源定位、可接受范围、不确定性。

必须记录判定方法与阈值，例如：

- 趋势：至少 3 个时间点；5 点以上可用线性/Theil-Sen 斜率；记录 R²、窗口、单位。少于 5 点只能给方向，不给拐点强度。
- 异常：默认稳健 z 或 MAD，阈值 `median + 3.5 * MAD`；少于 5 次重复不判异常，只标“可观察波动”；封顶/超量程数据单独标记。
- 原因：按 `direct support` / `indirect support` / `only plausible` / `excluded` 四级排序；必须有排除证据，不把相关写成因果。
- 对照：有对照时才允许推断处理效应；缺对照只能描述趋势，不推断归因。

---

## 6. 五段结论怎么写

### 6.1 趋势与拐点

- 报告方向、幅度、区间起点/终点、拐点位置、平台期。
- 说明拟合方式、使用窗口、对照区间。
- 不允许写“读数升高”却不给数值、区间、单位。
- 区分信号与噪声：小波动不得称为拐点。

### 6.2 异常点

- 定位维度完整：样本、批次、通道、孔位、时间点。
- 给异常分数、阈值、与对照/重复的偏离关系。
- 封顶数据、超量程数据、表观异常但可能与批次绑定者须注明。
- 哪些不是异常也要给排除说明。

### 6.3 可能原因

每条原因候选包括：

- 假设。
- 支持证据 `support`，逐条带 `S#`/locator。
- 排除证据 `against`。
- 可检验性：可由哪个复核动作验证。
- 风险：相关不等于因果、批次混淆、设备漂移、通道串扰等。

必须排序，不能只给一个“最可能原因”。

### 6.4 复核步骤

不能写“检查数据质量”。要写成：

- 打开哪个文件、哪个 sheet、哪个列/行。
- 重新计算哪个公式。
- 核对哪个批号/设备日志。
- 验证如果假设成立应该看到什么；如果不成立应该看到什么。
- 要补做哪些对照或平行重复。

### 6.5 后续实验建议

- 对应证据缺口：补对照、增加重复、加密采样点、调整参数范围、分批次标记。
- 每个建议说明解决哪个不确定性、预期读数和失败判读方式。
- 不把未经确认的建议写成可执行事实。

---

## 7. result.json 契约

`result.json` 必须同时满足：

1. 所有原 `output_contract` 字段**在顶层出现一次**。
2. 所有原 `output_contract` 字段**在 `nested output_contract` 中再出现一次**，内容一致。
3. `case_id` 原样保留。
4. 必须包含：
   - `status`：`finalize` / `partial` / `insufficient_evidence`
   - `summary`
   - `sources[]`
   - `uncertainty[]`
   - `pending_human[]`
   - `errors[]`
   - `degradations[]`
   - `changes[]`
   - `counts`：趋势条数、异常条数、原因条数、复核条数、后续实验条数、未解释项数。
   - `runtime`：秒，诚实记录。
   - `output_contract`：嵌套完整契约。
5. 不伪造 `golden_standard`、`diff_report` 或自评分数；自检只引用真实执行结果。
6. 失败、缺失、无法判断必须诚实写入，不得用占位符伪装完成。

---

## 8. 异常与降级处理

| 场景 | 处理 |
|---|---|
| `case.json` 缺失/损坏 | 查同级 `case*.json`；仍缺则 `case_id=UNKNOWN`，继续执行，状态 partial/insufficient_evidence |
| 材料全部不可读 | 输出合法 result.json，状态 `insufficient_evidence`；`errors` 写详情 |
| 单个 PDF/DOCX/XLSX 解析失败 | 该来源标 parsed=error；其他继续 |
| 单位不一致 | 保留原单位；禁止在无换算依据时强行统一 |
| 重复数不足 | 不判离群点；降级为描述性结论，写入 `pending_human` |
| 缺对照 | 不推断处理效应；只报告趋势和限制 |
| 读数超量程/封顶 | 标注可能为饱和/截断；单独处理，不纳入普通趋势斜率 |
| 结论互相冲突 | 写入 `conflicts` 或 `uncertainty`，不压制 |
| 脚本异常 | 捕获后写 partial result.json，退出码 0 |

---

## 9. 自检清单

结束前逐项核对：

- [ ] `python3 scripts/main.py run --input /input --output /app/output --work /app/work` 可复跑且退出码 0。
- [ ] result.json 合法 JSON，含 case_id。
- [ ] output_contract 字段在顶层和 `output_contract` 嵌套内各出现一次且不缺键。
- [ ] 五个文本型交付物齐全，文档内容与 result.json 一致。
- [ ] 每个数字/异常/原因至少一条 `S#` + locator。
- [ ] 材料缺失、解析失败、数据不足均有诚实 gaps。
- [ ] 没有把主观/专家确认内容写成事实。
- [ ] 所有文件大小与数量符合平台限制：≤50 文件、单文件≤500KB、总≤2MB。
- [ ] 如 output_contract 要求，已提供可编辑 Office 文件和 PDF/PNG 预览。
- [ ] `status` 不为 finalize 时，明确列出 limits。
- [ ] `changes[]` 记录 Agent 实际读/改/废内容。

---

## 10. 预算意识与增量收尾

官方预算：64 次模型请求 / 900 秒 / 单响应 16384 tokens。

- 先跑 1 次 E2E 基线，确保全套产物和合法 partial。
- 剩余请求优先用于：读关键材料、核验 locator、补 draft 正文、修正错误。
- 达到 40 次模型请求或 600 秒时，立即转向收尾：保证 result.json 合法、status 诚实、所有 output_contract 键存在。
- 不追求完美长文，先保存 honest partial，再改进。
- 若 Agent 来不及写 draft，确定性兜底也是完整交付；不要空手等靠模型。

---

## 11. 生态与复用

本包附带的资源均为离线、纯标准库、可复现：

- `references/checklists.md`：五段结论核验清单、异常处理清单、接收/拒绝标准。
- `references/input-formats.md`：CSV/TSV/XLSX/PDF/DOCX/图片等输入格式发现规则和解析优先级。
- `references/method-and-thresholds.md`：趋势、稳健 z、MAD、批次/通道异常绑定、原因排序、复核清单生成、阈值默认值和调整原则。

其他要求：

- 纯 Python 标准库，`python3 >= 3.8`，离线。
- 中英文自适应：输入中文用中文，输入英文用英文。
- 交付文件不得依赖未说明的个人文件、网络、手工临时操作。

---

## 12. 最小调用示例

输入：

```bash
python3 scripts/main.py run --input /input --output /app/output --work /app/work
```

`/input` 内至少包含：

- `case.json`
- `task.md`
- 题面提供的实验材料，如 `raw_reads.csv` 或 `sample_workbook.xlsx`、`full_paper.pdf`

示意输出：

```text
/app/output/result.json
/app/output/protocol.md
/app/output/anomaly_table.csv
/app/output/recheck_checklist.csv
/app/output/risk_table.csv
/app/output/agent_review.json
```

此示例只说明接口，不冒充正式案例结果。实际输出完全由输入材料与 Agent 推理决定。

---

## 13. 禁止事项

1. 禁止手工篡改 `result.json` 结构或直接编辑脚本生成的结构化 JSON。
2. 禁止依据文件名、领域标签或以往记忆补造材料内容。
3. 禁止生成自设 `golden_standard`、benchmark 分数或白板对比。
4. 禁止把主观判断/专家确认内容写成事实。
5. 禁止在缺对照或重复不足时下因果结论。
6. 禁止省略顶层或嵌套 output_contract。
7. 禁止因单个文件错误停止运行；必须退出码 0。
8. 禁止用示例输出冒充案例真实结果。