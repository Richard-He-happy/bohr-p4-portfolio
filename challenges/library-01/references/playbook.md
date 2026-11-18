# 操作手册（playbook）v1.0.0

面向"拿到一批科研文件、需要在可核验前提下落库"的使用者与 Agent。

## 1. 五步操作

```bash
# 1) 落库（唯一必需步骤）
python3 -B scripts/main.py --input /input --output /app/output

# 2) 独立复核（可随时重跑，只读产物）
python3 -B scripts/main.py --check --input /input --output /app/output

# 3) 查看结论
python3 -c "import json;r=json.load(open('/app/output/result.json'));print(r['status'],r['metrics'])"

# 4) 看清单与出处
column -s, -t /app/output/inventory.csv | head
grep -c . /app/output/metadata.csv

# 5) 看失败与待人工确认
python3 -c "import json;r=json.load(open('/app/output/result.json'));print(r['errors'],r['pending_human'])"
```

`--input`/`--output` 省略时依次探测 `/input`、`/app/input`、`./input` 与 `/app/output`、`./output`。

## 2. 结果怎么读

1. 先看 `status`：`ok` 才代表无阻断项；`partial` 必须读 `errors`/`pending_human` 才知道缺什么。
2. `metrics` 的守恒式先对上：`materials_indexed + excluded_control + denied_paths == files_seen`，对不上说明有静默跳过（正常情况下不会发生）。
3. `inventory.csv` 逐文件核对：`sha256` 与源文件一致、`path_library` 真实存在、`action` 说明处置。
4. `metadata.csv` 逐字段看出处；`confidence=low` 的字段（如内容首行当标题）应人工确认后再用于正式目录/交接。
5. `version_chain.json` 看谁替代谁、差多少行；`duplicates.exact_groups` 看哪些文件是同一份内容。
6. `operations.log` 是"到底动了什么"的唯一凭据：每条含 before/after 哈希与目标路径。

## 3. 复核（他人可复跑的判据）

```bash
python3 -B scripts/main.py --check --input <same input> --output <same output>
cat verify_report.json    # passed / 9 项 checks / failed 计数
```

九项检查覆盖：结果可解析、状态合法、契约键齐全、源哈希重算一致、副本存在且哈希一致、计数守恒、重复组自洽、版本链自洽、日志为合法 JSONL。
另外可用 `run_manifest.json` 校验产物未被改动：

```bash
python3 - <<'EOF'
import json, hashlib, pathlib
m = json.load(open('/app/output/run_manifest.json')); bad = []
for rel, meta in m['files'].items():
    p = pathlib.Path('/app/output') / rel
    if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest() != meta['sha256']:
        bad.append(rel)
print('mismatched:', bad)
EOF
```

## 4. 复跑与幂等

- 同输入同输出再跑一次：已入库文件 `action=reuse`、`metrics.copied=0`，清单与哈希集合不变（`run_id` 相同）。
- 源文件被改动后再跑：同名不同哈希 → 目标侧生成 `__altN`，并在 `integrity_flag` 记 `name_conflict`；旧副本不动，避免破坏原有归档。
- 想改规则（目录/命名/判重）：先改 `references/library-rules.md`，再改 `curator.py` 中 `CG/FA/INSTR/VW` 常量，最后升 `VER` 并同步 `SKILL.md` §14。

## 5. 降级演练（如何验证异常处理是真的）

| 演练 | 构造方式 | 期望 |
|---|---|---|
| 空输入 | 空目录 + 无 case.json | 退出码 0，`result.json` 合法，`status=input_error`，`errors=[case_missing]` |
| 坏 case.json | 写入非法 JSON | 退出码 0，仍扫描材料，`status=input_error`，`errors` 含 `case_json_unreadable` |
| 权限不足 | `chmod 000` 某文件（非 root 运行） | 该文件 `read_status=permission_denied`，其余照常入库，`failures.unreadable` 列出 |
| 损坏压缩包/Office | 用 `PK\x03\x04` 开头写垃圾字节的 `.docx` | `read_status=corrupt`，`errors=archive_read_failed`，文件仍入库 |
| 零字节/上传中断 | `: > empty.dat` | `integrity_flag=empty_file`，`degradations` 记录 |
| 重名冲突 | 两个不同内容同名文件分放不同目录 | 第二个落 `__alt1`，`integrity_flag=name_conflict`，两份都在 |
| 空间不足 | 目标盘几乎写满 | `skip_disk_space`，清单与日志仍完整，`status=partial` |

## 6. FAQ

**Q：为什么不把文件 MOVE 进库？**
A：源批次是唯一凭证。复制 + 复制后哈希校验 + `reuse` 幂等，能保证"库里有什么、原文件是什么"都可追溯；移动会破坏复跑。

**Q：year 为什么有 `_undated`？**
A：只从文件名/伴随表取四位年（排除项目号里的数字）。拿不到就放 `_undated`，mtime 年只记 `metadata.mtime_year`（`source=derived`），不拿运行时间冒充资料年份。

**Q：PDF 没抽到文本怎么办？**
A：`read_status=no_text_layer`，只保留元数据；不 OCR、不猜内容。可先用外部工具转文本后再入批次。

**Q：检索答不上来？**
A：`queries[].status=no_match` 且 `answer=null` 是合法结论。词法检索不覆盖同义词/语义近似，需人工或换关键词。

**Q：契约里有我没见过的字段名？**
A：仍原样保留在顶层；命中不了语义映射的写 `null`/`[]`/`{}` 并列进 `contract_unresolved`，绝不套用别的产物冒充。

**Q：能处理超大文件吗？**
A：>8MB 文件跳过文本抽取（`bounded_read`），但仍计算全量 sha256 并入库；总量与文件数上限见 `library-rules.md` §9。

## 7. 限制（明确不承诺的部分）

- 无 OCR、无语义检索、不做跨批次增量库、不做云同步与断点续传协议。
- 版本链顺序以 mtime 为主键；解压/复制会改写 mtime 时可倒置，`basis` 字段已声明，需人工复核的会进 `uncertainty`。
- 中文 PDF 若用 CID 字体，明文串可能不可读 → 视为 `no_text_layer`。
- 不做去重后的存储回收（重复文件只是不复制，不删除源）。

## 8. 最小调用示例（示例，非正式案例结果）

输入（示例，非正式案例结果）：

```json
{"case_id": "demo-001",
 "output_contract": {"inventory": "list of files with sha256", "version_chains": "array",
                     "duplicates": "array", "status": "string"},
 "queries": ["2019 XRD raw data"]}
```

调用：

```bash
python3 -B scripts/main.py --input /input --output /app/output
```

示意输出（示例，非正式案例结果）：`status="ok"`；`metrics={"files_seen":4,"materials_indexed":2,"copied":2,...}`；
`library/PROJ-2023-014/2019/03_tables/PROJ-2023-014_XRD_2019 v1.csv` 与同名 `v2.csv` 形成 1 条版本链；
另一份同哈希文件记为 `exact_duplicate`（`dup_of=IT0007`）而不复制。真实案例结果以运行时产物为准。

## 9. 版本与维护

| 版本 | 日期 | 变化 |
|---|---|---|
| 1.0.0 | 2026-11 | 首版：哈希清单、字段出处、按哈希判重、mtime+版本号建链、复制校验、九项自检、`--check` |

维护要点：脚本仅标准库；新增规则时保持"结果可复跑、失败必记录、不覆盖源文件"三条不变式。
