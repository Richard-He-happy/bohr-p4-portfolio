---
name: bio-mechanism-figure
description: 把机制材料（论文段落、figure workorder、图表数据、已有 SVG/PDF）转成可追溯、可编辑、可复核的生物机制图/通路图：分层可编辑 SVG、真实渲染 PNG/PDF 预览、content_map、compliance_checks、来源与变更记录、result.json（原 output_contract 全字段并双回显）。优先单命令全流程；无 Agent draft 时脚本确定性兜底，仍产出完整产物。任何情况下 result.json 合法且退出码 0。Use when the task asks for a biological mechanism diagram, pathway figure, signalling schematic, source-preserving figure edit, or chart/mechanism figure generation.
version: 4.0.0
---

# 生物机制图与通路图：可编辑、可追溯、可复核

## 0. 最高优先级规则（先读，不可违背）

1. **只读事实材料**：必须真实解析 `/input` 下的 `case.json`、`task.md`、PDF/DOCX/CSV/JSON/SVG/PNG 及工作单中指定的原文、原始图、数据文件。不得依据文件名或领域标签推测内容，不得补造缺失科学数据。
2. **单命令全流程优先**：进入任务后先运行本包 `run` 命令。它内部完成 init → build → selfcheck，产出全套基线交付物。不可跳过基线。
3. **双路径但同一契约**：
   - Agent 路径：读取台账与原文，把生物学判断写入 `/app/work/plan.json`（本包的 draft），再 `check`、`build`。
   - 无 `plan.json` 时：脚本必须用 init 台账确定性抽取、逐字引用和 locator，生成实质工作稿并渲染全部产物，同时把 `AUTO_EXTRACT` 写入 `degradations`。
   - 两条路径必须产出同一套文件与同一份 `result.json` 契约。
4. **不手改结构化 JSON 框架**：`result.json`、`content_map.json`、`compliance_checks.json` 等结构化字段由脚本生成或更新。Agent 可写 `plan.json`、`agent_review.json` 等核验记录，但不得删除/重命名契约字段。脚本不可用时才允许手写最小合法 `result.json`，并保留已产出文件。
5. **完整性优先**：基线产物只增强、不删除。先落盘全套产物，再做增量审校。不得为了“干净”删除部分产物。
6. **退出码恒为 0**：脚本命令失败、材料缺失、导出失败等都必须被记录；最终返回合法 `result.json`，主流程不得以非 0 退出。
7. **科学语义判断优先于逐字引文通过**：逐字 quote/locator 是必要条件，不是充分条件。还要判断实体类型、箭头语义、通路方向、区室、图例与图形是否一致；不确定就写 `pending_human`，不要硬判。

---

## 1. 入口命令与目录

### 1.1 单命令首选入口

```bash
python3 -B /skills/weekly-skill/scripts/main.py run \
  --input /input \
  --output /app/output \
  --work /app/work
```

`run` 应等价完成：

- **init**：盘点 `/input` 全部材料，给来源编号 `S1..Sn`，生成台账、候选实体/关系词组、冲突分组。
- **build**：校验 `plan.json`/工作单；缺失时确定性兜底抽取；渲染全部可编辑源文件与导出件；生成 `content_map`、`compliance_checks`、来源记录、变更记录、`result.json`。
- **selfcheck**：按第 7 节清单核对产物与契约，写 `self_check.json`。

### 1.2 如 `run` 不存在，使用等效降级命令

```bash
python3 -B /skills/weekly-skill/scripts/main.py init --input /input --output /app/output --work /app/work
python3 -B /skills/weekly-skill/scripts/main.py build --input /input --output /app/output --work /app/work
python3 -B /skills/weekly-skill/scripts/main.py selftest --output /app/output --work /app/work
```

不要因为某个子命令缺失就中断任务；把降级方式写入 `degradations`。

- 安装位置：`/skills/weekly-skill`。若实际路径不同，使用实际路径。
- 输入目录：`/input`，必须读取 `case.json`、`task.md` 及材料。
- 工作目录：`/app/work`；最终交付目录：`/app/output`。
- 纯标准库、离线、不依赖 CWD、`python3>=3.8`。所有命令可重入。

---

## 2. 执行流程

### 步骤 0：先落盘完整基线

无论材料是否读得懂、工作单是否齐全，先执行：

```bash
python3 -B /skills/weekly-skill/scripts/main.py run --input /input --output /app/output --work /app/work
```

若 `run` 不可用，执行 `init` + `build`。

检查 `/app/output` 至少出现：

- `figure.svg`
- `figure.pdf`
- `figure.png`（若无位图渲染器，则记录降级，并以 PDF 作为检视件）
- `content_map.json`
- `compliance_checks.json`
- `result.json`
- `diff_report.md`
- `golden_standard.json`
- `version_history.md`
- `self_check.json`
- `run.log`

已有文件保留；后续只覆盖增强，不删除。

失败分支：磁盘不可写或脚本完全不可用 → 写最小合法 `result.json`，列出已存在文件与错误，退出码 0。

### 步骤 1：盘点输入与真实阅读

- 读 `/input/case.json`，提取 `case_id`、`output_contract`、任务类型、材料路径。
- 读 `/input/task.md`，识别要画什么、导出什么、可编辑源有什么要求。
- 若有 `artifacts/figure-workorder.json`，逐条读取工作单中的实体、边、图例、导出约束。
- 用 `show` 命令查看材料切片：

```bash
python3 -B /skills/weekly-skill/scripts/main.py show --doc note --locator para3
python3 -B /skills/weekly-skill/scripts/main.py show --doc figure03 --locator stream7
```

- 对 PDF/DOCX 读取文本层；CSV/JSON 直接解析；SVG/PNG 检查实际图面而不只读文件名。
- 无文本层或无法解析的，列入 `gaps`/`degradations`，禁止用 OCR 幻觉补造。如果环境明确有 OCR，可尝试但必须标 `uncertainty`。
- 记下每个机制判断对应的 `locator` 和原文 quote 草稿。

### 步骤 2：Agent 写 draft/plan

Agent 在 `/app/work/plan.json` 中写入判断。schema 见 `references/plan-schema.md`。关键字段必须包含：

- `title`
- `source_scope`：哪个来源、哪个图、哪段材料
- `compartments[]`：按上游→下游排放；跨膜、胞内、核内位置根据原文；未说明则 `unspecified`
- `entities[]`：
  - `id`
  - `label`（原文写法，保留基因/蛋白/复合物/细胞类型/区室区分）
  - `kind`：`gene` / `protein` / `complex` / `cell_type` / `compartment` / `small_molecule` / `other`
  - `name_style_from_source`
  - `compartment`
  - `evidence.quote`：原文逐字片段 ≥ 6 字符
  - `evidence.locator`
  - `confidence`
- `relations[]`：
  - `id`
  - `source` / `target`
  - `type`：`activation` / `inhibition` / `binding` / `modification` / `translocation` / `unspecified`
  - `direction`
  - `arrow_style`
  - `evidence.quote`
  - `evidence.locator`
  - `confidence`
- `data_encoding[]`：颜色、线宽、节点大小/形状到表达量、显著性、置信度、时间点等的映射依据
- `legend[]`
- `gaps[]`
- `pending_human[]`

材料没写的，不要编造。实体歧义时保留原文写法，用 `kind_basis=not_stated` 区分，不要强行归一化。

### 步骤 3：核验

运行：

```bash
python3 -B /skills/weekly-skill/scripts/main.py check --input /input --output /app/output --work /app/work
```

核验点：

- 每个 `quote` 必须能定位到来源文本或工作单。
- 实体/关系不缺少必要语义字段。
- 通路方向与区室不违背原文。
- workorder 声明的条目是否覆盖。
- 图例映射是否有依据。

若 `check` 出现 `rejected`，Agent 应修正 `plan.json` 中的 quote/locator/类型，或把该项标为 `uncertain`；不得静默删除。

### 步骤 4：重建增强产物

```bash
python3 -B /skills/weekly-skill/scripts/main.py build --input /input --output /app/output --work /app/work
python3 -B /skills/weekly-skill/scripts/main.py selftest --output /app/output --work /app/work
```

`build` 必须：

- 渲染分层、命名清晰、字体可替换的 `figure.svg`。
- 生成真实 `figure.pdf` 与 `figure.png` 预览；若 PNG 不可生成，记录原因。
- 生成 `content_map.json`：每个关键实体、边、图例项、数据编码都带 `[S#]` 与 `文件#行号/段落号`。
- 生成 `compliance_checks.json`：检查实体类型、箭头语义、方向、区室、图例、导出格式、可编辑性、PDF/PNG 可打开性。
- 生成 `/app/output/result.json`，见第 3 节。
- 若输入是“编辑已有图”，保留原图来源，生成修改后版本，并在 `version_history.md` 中写清变更点。

### 步骤 5：最终自检与回填

- 对照第 7 节自检清单逐项核对。
- 核对「`output_contract` 字段 × 磁盘文件 × `result.json` 键」一一对应。
- Agent 的逐条核验结论写入 `agent_review.json` 或 `result.json.verified`。
- 无法确认的写入 `uncertainty`/`pending_human`。
- 本轮变更写入 `changes`。
- 所有异常写入 `errors`/`degradations`。
- 最终保证 `/app/output/result.json` 合法、诚实、完整，退出码 0。

---

## 3. result.json 契约

### 3.1 必须包含原 `output_contract` 全字段

从 `case.json` 中读取 `output_contract`，逐项回填。若缺失，至少保证：

```json
{
  "case_id": "...",
  "status": "complete|partial|empty|input_error|export_error|fallback",
  "editable_source": {},
  "export_artifact": {},
  "content_map": {},
  "compliance_checks": {},
  "exceptions": []
}
```

键名不得更改、不得遗漏；缺值用 `null` 或 `[]`，并在 `exceptions` 说明。

### 3.2 双回显

`case_id` 与所有 `output_contract` 字段必须在 `result.json` 顶层和 `output_contract` 嵌套对象中各出现一次。例如：

```json
{
  "case_id": "SYN-FIGURE",
  "status": "complete",
  "editable_source": { "file": "figure.svg", "layers": true },
  "export_artifact": { "files": ["figure.pdf", "figure.png"] },
  "content_map": { "file": "content_map.json" },
  "compliance_checks": { "file": "compliance_checks.json" },
  "exceptions": [],
  "output_contract": {
    "case_id": "SYN-FIGURE",
    "status": "complete",
    "editable_source": { "file": "figure.svg", "layers": true },
    "export_artifact": { "files": ["figure.pdf", "figure.png"] },
    "content_map": { "file": "content_map.json" },
    "compliance_checks": { "file": "compliance_checks.json" },
    "exceptions": []
  }
}
```

### 3.3 诚实状态附加字段

还必须包含：

- `sources`：来源清单、来源编号、文件路径、版本/页/段落范围。
- `uncertainty`：方向不明、实体歧义、数据不足等。
- `pending_human`：需要人工确认的科学判断。
- `errors`：命令失败、解析失败、导出失败等。
- `degradations`：AUTO_EXTRACT、缺少 plan、PNG 缺失、PDF 字体问题、OCR 不可用等。
- `changes`：Agent 增强、重描、修订、降级。
- `runtime`：init/build/selftest 的耗时、子命令状态。
- `verified`：Agent 核验结论。
- `conflicts`：材料之间不一致。

---

## 4. 科学绘图规则

### 4.1 实体命名

- 基因、蛋白、复合物、家族成员、细胞类型、亚细胞区室必须分开。
- 保留材料原文写法；若原文同时出现同义名/旧名，不擅自合并，可在 `content_map` 中登记同义候选。
- 物种前缀、修饰状态（如磷酸化）不丢失。
- 同名基因与蛋白不混用；材料未写的一律 `unspecified`，不得判成确定类型。

### 4.2 关系语义到图元

关系必须可区分，不得把所有箭头画成同一样式：

- `activation`：实心箭头。
- `inhibition`：T-bar/平头抑制线。
- `binding`：无箭头连接线或端点圆点。
- `modification`：如磷酸化、泛素化；用不同端点标记/线型并写进图例。
- `translocation`：虚线或开放箭头，明确起止区室。
- `unspecified`：用中灰线，并写进 `pending_human`。

### 4.3 方向与区室

- 通路方向必须按原文上下游顺序，不能自动把名词平铺成圆环。
- 受体在膜上、膜外/膜内位置要依据来源；跨膜受体不得画在胞内或膜内。
- 分支、反馈环、并行通路必须显式保留。
- 有冲突的证据：保留并写 `conflicts`，不人为消除。

### 4.4 图例与数据编码

- 颜色、线宽、节点大小/形状、虚线实线都要有图例。
- 图例必须从材料或工作单找到依据；没有依据就标 `unspecified`。
- 图面配色/线宽必须与图例一致，不能出现图例说红色=抑制、图面却用红色=激活。
- 图表数据映射（如表达量、显著值）必须回源到数据行。

### 4.5 可编辑源文件

- `figure.svg` 必须分层，给出稳定 `id`，标签可改，字体可替换。
- SVG 不能用扁平路径伪装成可编辑科研图；应保留文本节点、组、边、端点标记。
- 不允许只输出位图截图。

---

## 5. 异常与鲁棒性

| 情况 | 处置 | 落点 |
|---|---|---|
| `case.json` 缺失或坏 JSON | 抢救 `case_id`/`output_contract`，继续跑 | `errors`, `status=input_error` |
| `output_contract` 缺失 | 至少回填第 3.1 节字段 | `exceptions` |
| 材料缺失/损坏/不支持 | 列出缺口，不猜内容 | `gaps`, `degradations` |
| 扫描 PDF 无文本层 | 不清洗不编造；有 OCR 可试并标不确定性，没有则放弃 | `gaps`, `pending_human` |
| 无 `plan.json` | `build` 用确定性兜底抽取实体/关系 | `degradations` |
| `quote` 无法逐字匹配 | 仍出图，标未核验，状态降级 | `uncertainty`, `counts.rejected_quotes` |
| 实体歧义、方向缺失 | 保留原文写法，标 `unspecified` | `gaps`, `pending_human` |
| 图面元素过多 | 按来源优先级降噪，保留关键机制主干 | `compliance_checks` |
| PDF 字体丢失/非拉丁字符 | SVG 保留原文；PDF 丢字计数 | `compliance_checks.pdf` |
| 无 PNG 渲染器 | 用 PDF 作检视件，出不 PNG | `raster_preview`, `degradations` |
| 编辑已有图但来源不可解析 | 保留原来源文件，列出不可改动点 | `version_history.md`, `degradations` |
| 超时/逼近预算 | 立即保存当前产物，运行 build/selftest 收尾 | `runtime`, `status=partial` |
| 子进程失败 | 记录 `pass=false`，继续主流程 | `self_check.fallback`, `errors` |

---

## 6. 预算策略

官方预算：64 次模型请求 / 900 秒 / 单次 16384 tokens。

建议分配：

- 步骤 0 基线 `run`/`init+build`：2–4 次。
- 步骤 1 读材料，优先读工单、机制段、图例/数据段：10–20 次。
- 步骤 2 写 `plan.json`：3–8 次。
- 步骤 3 `check` + 修 quote：2–5 次。
- 步骤 4 `build` + `selftest`：2–5 次。
- 步骤 5 自检与回填：2–4 次。

保留约 25–30% 余量处理歧义、rebuild、异常恢复。

超过约 780 秒或约 50 次请求仍未完成时：立即保存当前最完整产物，运行 `build` 或保留基线，写诚实 `partial`，不要继续循环。最早在步骤 0 落盘全套基线，之后每次增强都更新 `/app/output`。

---

## 7. 自检清单

每次收尾前逐项确认：

1. `figure.svg` 存在，打开后实体、边、图例可编辑；文本不是全部转路径。
2. `figure.pdf` 存在且非零字节；`figure.png` 存在，或已记录无法生成的降级。
3. `content_map.json` 覆盖每个关键实体、关系、图例项、数据映射，且都有 `[S#]` 与 locator。
4. `compliance_checks.json` 包含实体类型、箭头语义、方向/区室、图例一致、导出件检查。
5. `result.json` 合法 JSON，顶层与 `output_contract` 都包含原始字段与 `case_id`。
6. `status` 诚实：完整则 `complete`，有缺口则 `partial`，输入坏则 `input_error`，导出坏则 `export_error`。
7. `sources`、`uncertainty`、`pending_human`、`errors`、`degradations`、`changes` 均非空且描述可操作。
8. `run.log`、`self_check.json`、`version_history.md` 存在且与当前产物一致。
9. 没有伪造 `golden_standard`、分数、基准结果。
10. 主流程退出码 0。

---

## 8. 必须避免

- 不要只输出 PNG 位图或纯样式示意图。
- 不要利用错误的领域标签补造机制内容。
- 不要手改结构化 JSON 后掩盖原始字段。
- 不要把“逐字引用通过”当作“科学绘图正确”。
- 不要将基因/蛋白/复合物/细胞类型/区室混为一类。
- 不要丢失反馈环、分支、抑制/激活差异。
- 不要在没有来源时给颜色/线宽/节点大小赋予数据含义。
- 不要因异常中断导致无 `/app/output/result.json` 或非 0 退出。