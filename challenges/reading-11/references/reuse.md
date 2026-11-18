# 复用、扩展与维护

## 1. 换一个新案例（3 分钟）

```bash
# 1. 放材料（case.json 可缺；材料名任意）
ls /input            # case.json, paper.pdf, table.csv ...
# 2. 建索引
python3 -B scripts/main.py init
# 3. 读原文、抄句子
python3 -B scripts/main.py show --material M01 --start 1 --limit 20
# 4. 写题集草稿（字段见 references/schema.md）
$EDITOR /app/work/questions.draft.json
# 5. 校验 → 出包
python3 -B scripts/main.py check
python3 -B scripts/main.py build
```

产物固定在 `/app/output/`。想留档就先 `cp -r /app/output /app/output.v1`（`build` 是覆盖写，幂等）。

不需要草稿也能跑：`build` 在草稿缺失/全部不可核验时自动生成最小摘录/数值题（`mode=fallback_minimal`，`status=partial`）。这是兜底，不是正式用法。

## 2. 在别的仓库/流水线里当组件用

| 用法 | 做法 |
|---|---|
| 批量跑多案例 | 外层循环改 `SCIBENCH_INPUT/SCIBENCH_OUTPUT/SCIBENCH_WORK` 三个环境变量，逐案例跑 `init→build` |
| 只当库 | `import bench`：`scan()` 建索引、`cache()/verify()` 核验引文、`validate()` 校验题集、`norm_item()` 归一字段 |
| 接自己的评分器 | 用 `benchmark.json`（题目+rubric+参考要点）与 `anchors.json`（locator+quote）作为输入；`scoring.json` 只是可判性自检，可替换 |
| 做回归对比 | 保存两版 `benchmark.json`，按 `id` 对齐比 `rubric` 与 `anchors.verified`，只重算变化的题 |

`bench.py` 路径解析：环境变量 → `/input`（或包同级 `input/`）→ 相对当前目录；嵌入别的程序时用环境变量最稳。

## 3. 扩展点

- **加题型**：改 `bench.TY` 加一个枚举；`type` 只在报告里分组，不影响算分。
- **改评分口径**：`main.score_items()` 里 `s = 2 if x >= 0.6 else (1 if x > 0 else 0)`，阈值与档位都在这行；改完升 `version`。
- **加材料类型**：改 `bench.kind()` 与 `bench.extract()`；失败返回 `("", "none", 原因)`，不中断全流程。
- **换 PDF 解析器**：`bench.ext_pdf()` 的探测顺序（pdftotext → PyMuPDF → pdfminer → 内置 zlib），平台工具插最前。
- **改报告版式**：`main.report()`，输入是算好的 `bench/anch/sc/idx`，不依赖别的状态。

## 4. 已知限制

- 图片材料无 OCR：只登记 `degradations`，由 Agent/平台工具补读后再出题。
- 引文核验是字符串匹配：改写、翻译、拼接都不算通过（这是刻意的——防止"看起来像原文"的伪造）。
- `key_terms` 覆盖度是启发式：中文按 4 字滑窗、英文按 ≥4 字母词，短术语（如 "pH"）建议显式写进 `key_terms`。
- 自检分只说明"题可判"，不说明"题难"或"题好"；难度分布要人看 `benchmark.json`。
- 兜底题只有摘录/数值两类，不能替代推理题、冲突题、跨段对比题。

## 5. 版本与变更

| 版本 | 变更 |
|---|---|
| 1.5.0 | Agent 主导出题流程（init→show→draft→check→build）；契约字段回填进 result.json 顶层；兜底题从真实段落生成；checker 日志只登记不评分；自审计摘要 |
| 1.4.x | 引入 `M01#pN` 稳定 locator 与一致性检查 |
| ≤1.3 | 单文件脚本，索引与报告耦合，异常即中断（历史低分主因） |

改版本时同步三处：`SKILL.md` 的流程/限制、`scripts/*.py` 的 `V`、本表。评分口径的变化必须写进本表，否则历史分数不可比。

## 6. 分享建议

`report.md` 是一次评测的凭证（材料、题面、locator、自检分、缺口），评审不必打开 JSON；`benchmark.json`+`anchors.json` 可入库当题集快照与引文抽查表；`rejected`+`pending_human` 就是下一版专项题的来源。
