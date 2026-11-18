# Minimal calling example (示例 / illustrative — not an official case result)

> 示例，非正式案例结果。This walkthrough uses a **synthetic** three-file demo built only to
> exercise the interface. It is not one of the platform's fixed cases and must not be read
> as a benchmark result.

## 1. Input

```
demo/
  case.json
  artifacts/config.yaml
  artifacts/train.log
  artifacts/methods_draft.md
```

`case.json` (abridged):

```json
{
  "case_id": "DEMO-01",
  "task_instruction": "补写论文的方法与实验章节，标注来源，缺口交作者确认。",
  "organizer_workorder": ["必须给出参数表，正文数值与表一致", "不得增加材料之外的数值"],
  "output_contract": {
    "case_id": null,
    "status": null,
    "manuscript": null,
    "preserved_facts": [],
    "evidence_map": [],
    "change_log": [],
    "pending_human": [],
    "self_check": {}
  }
}
```

`artifacts/config.yaml` (abridged): `dataset: {name: CIFAR-10, version: v1.0-original,
split: 0.8/0.1/0.1}`, `train: {batch_size: 64, epochs: 30, lr: 0.001, seed: 42}`.

`artifacts/methods_draft.md` (abridged): "…使用学习率 0.01 与批大小 64，共训练 30 个 epoch…"

## 2. Call

```bash
python3 -B scripts/main.py --input-dir ./demo --out ./demo_out
# exit code 0
# stderr: [methods-writer] status=partial materials=3 facts=12 steps=2 gaps=6 (0.4s)
```

## 3. Output (excerpt, illustrative)

`demo_out/manuscript.md`

```markdown
## 2 数据集与划分

- 数据集：CIFAR-10[E1]
- 版本：v1.0-original[E2]
- 划分：0.8/0.1/0.1[E3]

## 5 超参数

表 1 参数表（正文取值与本表一致）

| 参数 | 取值 | 作用对象 | 来源 | 定位 |
|---|---|---|---|---|
| batch | 64 | - | M1 | M1#L9 |
| lr | 0.001 | - | M1 | M1#L10 |

## 附录 B 待确认项

| 编号 | 要素 | 需确认内容 | 依据 |
|---|---|---|---|
| Q3 | 硬件 | 训练与评测所用硬件型号与数量是什么？ | 材料未出现 |
| C1 | lr | lr 在草稿中为 0.01，在 M1 中为 0.001，应以哪个为准？ | M1#L10 / M3#para 3 |
```

`demo_out/result.json` (excerpt):

```json
{
  "case_id": "DEMO-01",
  "status": "partial",
  "self_check": {"passed": 9, "failed": 0, "failed_items": []},
  "change_log": [
    {"change_id": "C1", "type": "corrected", "element": "parameters",
     "original_quote": "使用学习率 0.01 与批大小 64", "revised_quote": "lr = 0.001",
     "reason": "草稿值与配置/日志不一致，改用配置值", "locator": "M1#L10"}
  ],
  "pending_human": [
    {"id": "C1", "item": "lr", "blocking": true,
     "question": "lr 在草稿中为 0.01，在 M1 中为 0.001，应以哪个为准？"}
  ]
}
```

## 4. What the example demonstrates

| Behaviour | Where to look |
|-|-|
| Draft number contradicted by config → corrected, both locators kept | `change_log[0]`, Appendix B row `C1` |
| Missing element → question, not a guessed value | `pending_human` `Q3` |
| Every clause traceable | `[E1]…[E3]` resolve in Appendix A / `evidence_map` |
| Contract keys preserved verbatim | `case_id`, `status`, `manuscript`, … `self_check` all present |

## 5. Failure-mode examples (also illustrative)

| Input | Observable result |
|-|-|
| `--input-dir ./missing` | exit 0, `status=input_error`, `degradations` names the missing input dir, `pending_human` lists what is needed |
| malformed `case.json` | exit 0, `errors[0].stage=case`, contract fields absent from the broken file are simply not copied, `status=partial` or `input_error` |
| case with no `output_contract` | contract-free skeleton (the ten required fields), `status` reflects material coverage |
| PDF without a text layer | that file is `parse_status=degraded`, a `degradations` entry asks for author-supplied text, the rest of the run continues |
