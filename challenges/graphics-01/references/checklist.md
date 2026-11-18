# 自检清单与故障排查

## A. 运行前

- [ ] 输入目录里有 `case.json`（或在树内任意 `case*.json`）；`case_id`、`output_contract` 存在。
- [ ] 材料至少一种可读：md / txt / csv / tsv / json / yaml / tex / xml / 带文本层的 pdf。
- [ ] 若有 workorder：`required_entities`、`required_relations`、`source_artifact`（编辑类）能解析。
- [ ] 输出目录可写。

## B. 运行后（逐项机器可查）

| # | 检查 | 期望 | 看哪里 |
|-|-|-|-|
| 1 | 三件产物存在 | `figure.svg`、`figure.png`、`figure.pdf` 非空 | `ls -l` |
| 2 | SVG 合法 | `ET.fromstring` 通过；`<g id="layer-*">` ≥ 4；`<text>` ≥ 1；`<marker>` ≥ 2 | `compliance_checks.svg_wellformed` |
| 3 | 文字可编辑 | 无转曲（`<text>` 数量与标签数一致） | `editable_source.text_live/text_count` |
| 4 | id 对齐 | content_map 的每个 `svg_id` 都在 SVG 里 | `compliance_checks.id_map.missing == []` |
| 5 | 溯源完整 | 每个实体有 `source.locator` + 逐字 `quote` | `content_map.entities[*].source` |
| 6 | 覆盖率 | `coverage.complete == true`（mapped == required） | `content_map.coverage` |
| 7 | 图例一致 | 图例项数 == 关系类型数 + 数据系列数 | `compliance_checks.legend_consistency` |
| 8 | 无重叠/溢出 | `overlap.pairs == 0`、`overflow.* == 0` | `compliance_checks` |
| 9 | 位图真实 | PNG 有 IHDR 宽高、`nonwhite_ratio > 0.004` | `export_artifact.png.probe` |
| 10 | PDF 真实 | 头 `%PDF-`、尾 `%%EOF`、`pages ≥ 1` | `export_artifact.pdf.probe` |
| 11 | 确定性 | 同输入两次 `svg_sha256 == svg_sha256_recheck` | `compliance_checks.determinism` |
| 12 | 契约回填 | `output_contract` 的每个键都在 result.json 根上 | 手工比对 `output_contract_echo` |
| 13 | 状态诚实 | 有缺口时 `status != "ok"`，且缺口在 `exceptions`/`pending_human` | `status` |

## C. 一键自检片段

```bash
python3 -B scripts/main.py --input /input --output /tmp/o && python3 - <<'EOF'
import json
d = json.load(open('/tmp/o/result.json'))
ck = d['compliance_checks']
print('status :', d['status'])
print('pass   :', ck['pass'], ck['failures'])
print('cov    :', d['content_map']['coverage'])
print('png    :', d['export_artifact']['png'].get('engine'), d['export_artifact']['png'].get('width'))
print('pdf    :', d['export_artifact']['pdf'].get('engine'), d['export_artifact']['pdf'].get('pages'))
print('exc    :', [e['type'] for e in d['exceptions']])
EOF
```

## D. 故障排查

| 现象 | 原因 | 处理 |
|-|-|-|
| `status=input_error` | 没找到 case/材料 | 确认 `--input` 指向含 `case.json` 或材料的目录；看 `errors` |
| `png.status=missing` | 环境无 matplotlib 且无转换器 | 装任一：`librsvg2-bin`(rsvg-convert)、`cairosvg`、`inkscape`、`libreoffice+poppler-utils`、`imagemagick` |
| `pdf.status=missing` | 同上（PDF 侧） | 同上；LibreOffice 的 Draw 过滤器即可 |
| `labels_verbatim.ok=false` | 标签在材料里找不到逐字出现 | 检查是否拼写/大小写/连字符差异，或 workorder 用了材料没有的名字；确认后进 `pending_human` |
| `id_map.missing` 非空 | SVG 与 content_map 生成不同步 | 属实现缺陷：只允许由同一 model 生成两者；重跑并比对 `svg_sha256` |
| `legend_consistency.ok=false` | 图例项与图面编码数不符 | 检查关系类型是否都进了 `legend`；新增类型需同步 `references/relation-vocab.md` |
| `overflow.text_overflow>0` | 标签比框宽 | 缩短标签或让换行阈值更小（`render.wrap` 的 `maxch`） |
| `pixel_probe.blank=true` | 导出为空白页 | 通常是转换器不支持该 SVG 特性；换引擎并记录 |
| PDF 中文缺失 | 环境无中文字体 | 装 `fonts-noto-cjk`，或改用 LibreOffice 路径（会带系统字体） |
| `pdf_text_no_text_layer` | 扫描版 PDF | 需要 OCR；本 Skill 不臆造内容，改写 `pending_human` |

## E. 最小示例（示例，非正式案例结果）

```bash
mkdir -p /tmp/demo/in/artifacts
cat > /tmp/demo/in/case.json <<'JSON'
{"case_id":"demo-001","output_contract":["editable_source","export_artifact","content_map","compliance_checks","exceptions"],
 "organizer_workorder":{"figure_title":"Demo mechanism","required_entities":["IL-6","JAK2","STAT3"],
 "required_relations":[{"from":"IL-6","to":"JAK2","type":"activation"},{"from":"JAK2","to":"STAT3","type":"activation"}]}}
JSON
printf 'IL-6 activates JAK2.\nJAK2 activates STAT3.\n' > /tmp/demo/in/artifacts/notes.md
python3 -B scripts/main.py --input /tmp/demo/in --output /tmp/demo/out
```

示意结果（**示例，非正式案例结果**，用于说明接口，不代表正式案例）：

```json
{"case_id": "demo-001", "status": "ok",
 "export_artifact": {"png": {"engine": "libreoffice-draw+pdftoppm", "width": 3212, "height": 1140},
                     "pdf": {"engine": "libreoffice-draw", "pages": 1}},
 "content_map": {"coverage": {"entity_coverage": 1.0, "complete": true}},
 "compliance_checks": {"pass": true, "failures": []},
 "exceptions": []}
```

## F. 提交前（打包）

- 包内只有 `SKILL.md`、`scripts/*.py`、`references/*.md`；无 `__pycache__`/`.pyc`/示例大图/临时目录。
- `python3 -B scripts/main.py --help` 退出码 0。
- 全 UTF-8 文本，无符号链接，无联网依赖。
- 示例与正式结果分开存放，示例明确标注「示例，非正式案例结果」。
