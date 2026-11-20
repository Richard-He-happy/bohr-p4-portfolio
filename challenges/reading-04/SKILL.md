---
name: literature-qa
description: 文献智能问答。读取带段落编号的英文论文文本与中文问题清单，逐题回答并给出可回溯原文的依据；每条关键论断绑定 paper_id、paragraph_id 与逐字 quote，区分 reported 与 inferred，材料未报告时明确说明 insufficient_evidence。先运行 python3 -B scripts/main.py run 生成完整交付基线，再由 Agent 可选地阅读原文、写入 draft.json 后重新构建增强；无 draft 时脚本确定性兜底抽取。输出 /app/output/result.json，覆盖完整 output_contract，并以双回显方式保留 case_id 等契约字段。适用于论文精读问答、数值与条件核验、跨章节整合与“论文是否报告 X”类边界判断。仅使用题面材料，不使用外部知识或网络。
version: 4.0.0
---

# literature-qa（文献智能问答 Skill）

## 1. 目标与最高优先级规则

本 Skill 用于完成“带段落编号的论文材料 + 中文问题清单 → 逐题回答 + 证据定位 + result.json”的完整流程。最终交付物必须满足以下要求：

1. 每个问题都要有回答，且不能省略无法回答的问题。
2. 每个回答至少对应一个 claim，claim 必须有原文 evidence；evidence 必须包含 paragraph_id 和逐字 quote。
3. 数值、单位、比较对象、实验条件、结论范围必须与 /input 材料一致。
4. 明确区分：
   - reported：原文直接报告的内容。
   - inferred：由 Agent 跨句、跨段、跨表整合推出的内容；必须写入 conditions 并降低确定性表述。
5. 材料未报告某点时，必须说“材料未报告/无法确定”，状态使用 insufficient_evidence 或 partial，不得编造。
6. 只依据 /input 中实际提供的材料；不得使用外部知识、网络检索、文件名猜测或领域标签猜测。
7. 不读取任何含 score、gold、rubric、verifier、expected 的评测类文件；如需在 /input 中寻找 case 文件，跳过这些路径。
8. 最终 result.json 必须合法、完整，且异常情况下也必须 exit 0。

## 2. 运行契约与目录约定

- 输入：
  - /input/case.json：案例与论文标识、material_version、任务说明、问题清单，以及可能的 output_contract。
  - /input/task.md：题面 Runtime contract。
  - /input 可能内嵌段落文本，或材料文件路径。
- 工作目录：
  - /app/work：可写，放 draft.json、ledger.json、核验记录等中间文件。
- 最终产物：
  - 主产物：/app/output/result.json
  - 兼容产物：如环境要求 /app/answers.json，将 result.json 中的 answers 字段同步复制为 /app/answers.json；若 /app/output/answers.json 被要求，也可写镜像。
- Skill 根目录：
  - 优先使用 /skills/literature-qa；如果该目录不存在，则使用 /skills/weekly-skill。
- 无外部依赖：
  - 仅使用 Python 标准库，Python 3.8+。当前镜像提供 Python 3.12.1。禁止 pip install、联网安装依赖。
- 预算：
  - 官方预算为 64 次模型请求 / 900 秒 / 单次响应 16384 tokens 含推理。
  - 脚本运行是秒级、不占模型请求；优先使用脚本完成确定性兜底和结构化生成。

## 3. 单命令全流程入口

首个动作必须运行完整命令。命令内部会按 init → build → selfcheck 顺序执行：

```
SKILL_DIR="/skills/literature-qa"
[ -d "$SKILL_DIR/scripts" ] || SKILL_DIR="/skills/weekly-skill"
python3 -B "$SKILL_DIR/scripts/main.py" run --input /input --output /app/output --work /app/work || true
```

若目标脚本不支持 run 子命令，使用兼容命令：

```
python3 -B "$SKILL_DIR/scripts/main.py" --input /input --out /app/output || true
```

脚本职责说明：

- init：盘点 /input 材料，生成 source_id、段落清单、候选证据、问题分组、冲突分组，写 /app/work/ledger.json。
- build：校验候选证据；若存在 /app/work/draft.json，优先合并 Agent 判断；若不存在，则使用 init 台账确定性抽取产生逐字 quote、locator、conditions、claims，并把 AUTO_EXTRACT 诚实写入 degradations/gaps。
- selfcheck：检查产物与 output_contract 字段一致性、问题覆盖、quote 逐字性、状态合法性，并 finalize /app/output/result.json。

无论脚本内部发生什么错误，都必须保证最终 result.json 存在；脚本本身必须 exit 0，或在命令末尾使用 `|| true` 兜底。

## 4. 双路径：Agent 增强与确定性兜底

### 4.1 路径 A：Agent 增强路径，推荐且质量更高

如果预算允许，按以下步骤增强：

1. 先运行上面的 run 命令，得到基线 result.json 与 /app/work/ledger.json。
2. 阅读 /app/work/ledger.json，确认材料来源、paragraph_id 范围、候选 evidence 与问题清单。
3. 真实读取 /input 中的论文段落、表格文字、图注、参考文献著录信息。
4. 把你的判断写入 /app/work/draft.json。draft.json 形状与 result.json 的 answers/claims 结构一致，可参考 `references/guide.md`。至少包含：
   - question_id
   - answer 中文本
   - conditions
   - status
   - claims 列表，含 claim_id、text、kind、evidence 列表
   - evidence 中 paragraph_id、quote、paper_id
   - unanswered_parts
   - coverage
5. 重新运行 run 命令，使脚本把 draft.json 合并进最终产物，并完成 selfcheck 和 finalize。
6. 若 draft 被合并后仍有问题，按脚本提示调整 draft，最多再运行 1–2 次；不要手工编辑 result.json。

### 4.2 路径 B：无 draft 时确定性兜底

如果没有时间写 draft，直接保留 run 生成的基线产物。该基线必须：

- 为每个问题生成实质回答，而不是空模板；
- 每条主要论断附逐字 quote 和 locator；
- 记录 AUTO_EXTRACT 到 degradations/gaps；
- 状态为 partial 或 insufficient_evidence 时，明确写出未回答部分；
- result.json 顶层与 nested output_contract 双回显。

不要因为基线是脚本生成就重新手写整个 JSON；如果基线缺答案或字段，只能通过写 draft.json 后重新 run 来修正，或在极端失败时创建最小合法 result.json。

## 5. 标准执行流程

### 步骤 1：运行全流程脚本

立即运行第 3 节的单命令脚本。如果 /app/output/result.json 不存在，检查 /app/output 是否可写；若不可写则尝试 /app 可写路径，并写兼容 /app/answers.json。

### 步骤 2：读取 material/ledger

读取 /app/work/ledger.json，或直接读取 /input：

- case_id、paper_id、material_version。
- 段落编号清单。
- 问题清单及子问题。
- 材料格式：
  - JSON 内嵌段落：逐段读取摘要、正文、表格文字、图注、参考文献。
  - 表格文字：把每一行展开为“表头: 值”形式的伪段落，并保留原段落编号。
  - 图注：作为独立 pseudo paragraph，归属于原图所在段落编号或图注编号。
- 记录所有已读取文件和实际工具。

### 步骤 3：核验 evidence 与 claims

对每个问题及其子问：

1. 定位原文段落。
2. 确认关键数值、单位、条件、比较对象是否准确。
3. 摘录逐字 quote，通常 15–60 词；quote 必须是原文连续子串，不允许改写。
4. 为每条 claim 记录：
   - claim_id：建议 Q1-C1、Q1-C2 格式，问题内递增。
   - text：中文论断。
   - kind：reported 或 inferred。
   - evidence：paragraph_id、quote、paper_id、locator，locator 建议为“材料文件#段落号”或“材料名#行号/段落号”。
5. 若基线 claim 存在，逐条核验：
   - quote 是否逐字；
   - 段落编号是否有效；
   - 数值单位是否匹配；
   - 论断是否真的被引文支持。
6. 找不到依据：
   - 状态标 insufficient_evidence 或 partial；
   - 将未回答部分写入 unanswered_parts；
   - 不要反复搜索同一问题，避免浪费预算。

### 步骤 4：编写答案

用中文回答。规则：

- 覆盖每个子问；子问也要有状态。
- 回答自然，但数值、单位、条件须与原文一致。
- 主要论断后引用证据，形式可为“见 [S#] 段落 P#”，但结构化 evidence 必须在 claims 中。
- 明确区分原文报告与 Agent 推断。
- 材料来源冲突时：在 answer 中明确说明“原文 P# 与 P# 不一致”，在 uncertainty 中登记，cl claims 可分别保留对应证据。
- 材料未报告时：回答写“材料未报告/无法确定”，不要把缺失写成否定结论。

### 步骤 5：写 draft 并重跑

如需更新基线，写 /app/work/draft.json，然后再次运行 run。完成后：

- 检查 result.json 是否包含你的答案和核验后的 claims。
- 检查 verification 是否通过，degradations 是否诚实。

### 步骤 6：最终自检

逐项核对第 7、8、9 节契约。若不满足：

- 通过 draft.json 修正；
- 时间不足时，保留合法结果，并在 pending_human 中记录。

## 6. result.json 双回显与顶层字段

result.json 必须包含以下顶层键：

- case_id：与输入一致。
- paper_id：与输入一致。
- material_version：与输入一致。
- status：整体状态，枚举 ok、partial、insufficient_evidence、input_error。
- summary：一段简短中文摘要，说明整体完成情况与主要缺口。
- result：对象，包含 answers、unanswered_parts、coverage。
- answers：数组，等于 result.answers 的镜像。
- claims：全局 claims 数组，所有逐题 claims 的汇总。
- uncertainty 或 uncertainties：至少包含一个数组；两者都可保留，但必须有一个非空数组键。
- sources：实际读取的文件与工具列表。
- pending_human：需要人工复核或无法自动完成的事项。
- errors：运行错误、读取失败、解析失败。
- degradations：降级项，包括 AUTO_EXTRACT、表格未解析、证据不足、时间截断等。
- changes：本次运行相对基线或草稿的修改记录。
- counts：如 questions、answered、partial、insufficient_evidence、input_error、claims、reported、inferred、evidence、sources。
- verification：selfcheck 结果，必须真实；无 verify 脚本时写 manual_selfcheck 的布尔与问题列表。
- primary_result：主产物路径，优先 /app/output/result.json。
- method_notes：方法说明，简述 Agent 是否介入、是否使用 draft、是否使用 AUTO_EXTRACT。
- runtime：记录 elapsed_seconds、model_requests_used 等真实可采集信息；不谎报人工计时。
- contract_keys：列出 output_contract 中已满足的键。
- question_ids：问题 id 列表，顺序与输入一致。
- output_contract：嵌套对象，必须再回显输入 output_contract 的每个键；未知键保留，缺值用 null 或 [] 补足。其中 case_id、paper_id、material_version、answers 等契约字段也必须出现在 nested output_contract 中。

如果输入没有 output_contract，则根据标准契约构造 nested output_contract，至少包括：case_id、paper_id、material_version、answers、coverage、status、sources、uncertainty、pending_human、errors、degradations。

## 7. answers[] 契约

每个 answer 对象包含：

- question_id：字符串，来自输入。
- question：原始问题文本。
- answer：中文回答文本；不能为空。
- conditions：数组，列明结论成立条件，例如温度、压力、样本、材料版本、适用章节。
- status：枚举：
  - answered：完整回答。
  - partial：部分回答。
  - insufficient_evidence：材料不足。
  - input_error：输入读取失败。
- question_type：如 factual、numeric、comparison、yes_no、method、cross_section、boundary。
- flags：数组，如 needs_cross_section、conflicting_evidence、not_reported、value_uncertain。
- sub_questions：数组，每个对象含 index、question、status、claim_ids、evidence_paragraph_ids。
- claims：该问题对应的 claims 数组，可以是全局 claims 的引用或复本。
- unanswered_parts：数组，每个对象含 part、reason、closest_evidence_paragraph_ids。
- evidence_paragraph_ids：该题所有证据段落 id。

规则：

- 不得省略任何问题；即使无法回答，也要生成 answer 项，answer 文本写“材料未报告/无法确定”，并选择 insufficient_evidence。
- status 要与 answer 内容、claims、unanswered_parts 一致。
- 子问覆盖完整；若某个子问被合并回答，也必须在 sub_questions 中列出该子问 id 与状态。

## 8. claims[] 与 evidence[] 契约

claim 对象：

- claim_id：稳定唯一，建议 Q<题号>-C<序号>。
- text：中文论断，包含关键数值、单位、条件。
- kind：reported 或 inferred。
- evidence：数组，每条如下。
- source_id：指向 sources 中的来源。

evidence 对象：

- paragraph_id：段落编号，必须来自输入。
- quote：原文逐字短引文，不允许改写、翻译、省略成非原文。
- char_start：quote 在段落中的起始字符位置，无法计算时为 -1。
- locator：如“materials.txt#P7”或“case.json#paragraphs[7]”。
- paper_id：与输入一致的论文标识。

reported 与 inferred 判断：

- reported：引文直接包含数值、实验条件、比较对象或结论。
- inferred：需要综合多句/多段才得出的结论；必须在 text 中写“推断：”，并在 answer.conditions 中写推理前提。

## 9. coverage、uncertainty、gaps

coverage 对象：

- read_sections：已读章节列表。
- sections_unread：未读章节列表及原因。
- unread_reason：未读原因，如实填写。
- not_supplied：材料未提供的章节或对象。
- read_status：complete 或 partial。

coverage 必须与实际读取一致，不能声称读取未读章节；平台会结合运行记录核验。

uncertainty 数组建议每条包含：

- uncertainty_id
- question_id 或 claim_id
- issue：冲突、单位缺失、数值范围不清、材料未报告。
- severity：high、medium、low。
- resolution：Agent 如何处理。
- evidence_paragraph_ids：相关段落。

gaps/degradations：

- 缺材料：写入 degradations，并在 unanswered_parts 中说明。
- AUTO_EXTRACT：若使用脚本确定性兜底，必须保留该退化标记，不要删除。
- 表格未解析、图片未读、段落乱码等：必须写入 errors 或 degradations。

## 10. 异常处理与可靠性

- 输入 /input/case.json 不存在或坏 JSON：在 /input 下递归寻找非评测 JSON；若仍找不到，生成 status=input_error、answers=[]、errors[stage=load_case] 的合法 result.json，并 exit 0。
- 材料文件不可读：跳过该文件，记录 errors/degradations，将相关章节写入 coverage.sections_unread。
- 证据冲突：在 answer 中说明冲突，在 uncertainty 中登记，不强行选择一边。
- 材料不足：status 多选 insufficient_evidence 或 partial，写“材料未报告”或“仅能部分回答”。
- 脚本失败：优先检查是否有 result.json；没有则创建最小合法 result.json，包含空业务字段、errors、degradations。
- 退出码：无论任何情况，都要确保最终 exit 0。
- 重复运行：脚本应 deterministic；Agent 不要依赖随机外部知识。相同输入应产生稳定结果，仅 Agent 增强路径可能因 draft 不同而改变。

## 11. 预算管理

- 先跑 run，脚本生成全量基线，消耗 0 次模型请求。
- 优先花请求在：
  1. 阅读 ledger 与输入材料；
  2. 核验关键数值、单位、条件；
  3. 写 draft.json 提升回答质量。
- 避免：
  - 在单一问题上反复搜索超过 5 次；
  - 重写整个 JSON；
  - 手工格式化超大文件；
  - 阅读参考文献中不存在全文的条目。
- 接近 60 次模型请求或 800 秒时，停止增强，保留基线，确保 result.json 合法、可核验、状态诚实。

## 12. 最小调用示例

输入示例：

case_id: example-case
paper_id: ex-paper
material_version: v1
问题 Q1：“Experimental group 的去除率是多少？与对照相比如何？”
原文段落 P12：The initial nitrate concentration was 10.0 mg/L and the removal efficiency reached 87.5% in the experimental group, compared with 46.2% in the control group.

产出 answer 示例：

question_id: Q1
answer: “实验组去除率为 87.5%，对照组为 46.2%；实验组明显高于对照组。该结果来自 P12。”
status: answered
conditions: ["初始硝酸盐浓度为 10.0 mg/L", "比较对象为 experimental group 与 control group"]
claims 示例：

claim_id: Q1-C1
text: “实验组去除率为 87.5%，对照组为 46.2%。”
kind: reported
evidence:
  - paragraph_id: P12
    quote: "The initial nitrate concentration was 10.0 mg/L and the removal efficiency reached 87.5% in the experimental group, compared with 46.2% in the control group."
    locator: "case.json#P12"
    paper_id: ex-paper

该示例仅用于说明接口，不代表正式案例答案。

## 13. 包内资源与文档

以下资源应存在，并在运行时按需读取：

- SKILL.md：本文件，入口。
- references/guide.md：draft.json 形状、工作流、build/selfcheck 细节。
- references/schema.md：result.json 完整字段与枚举定义。
- references/glossary.md：中英术语归一、同义词扩展说明。
- references/example.md：完整示例。
- SELFTEST.md：自检清单与预期输出；结束前必须核对。
- environment/resources.yaml：资源与依赖声明，应为 Python 标准库、离线。
- scripts/main.py、scripts/core.py：可执行脚本；仅使用标准库。

若 SELFTEST.md 存在，结束前读取并逐项检查。若 references/guide.md 存在，draft.json 写法以它为准。

## 14. 最终交付清单

在结束前逐项确认：

- /app/output/result.json 存在且为合法 JSON。
- top-level case_id、paper_id、material_version 与输入一致。
- nested output_contract 内也包含 case_id、paper_id、material_version、answers 等契约字段。
- 每个 question_id 在 answers[] 中恰好出现一次。
- 每个 answer 的 status 在四种枚举中。
- 每个 claim 至少有一条 evidence；quote 是原文逐字子串。
- coverage 与实际读取一致。
- unanswered_parts 列明未完成部分；没有则为空数组。
- errors/degradations/pending_human 如实填写。
- 没有读取评分数据或隐藏答案。
- 没有使用外部知识，没有编造数据或引用。
- 命令异常时也已 exit 0，并生成合法 result.json。

完成以上即可结束。