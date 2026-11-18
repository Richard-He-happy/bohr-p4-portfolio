# MathML → LaTeX 映射与符号约定

本文件描述 `scripts/formula_core.py` 实际使用的确定性映射。原则：**保持元素顺序与嵌套，不猜字形**。任何未能映射的节点输出 `\square` 并写入 `flags`/`uncertainties`，绝不产出“看起来像”的猜测符号。

## 1. 结构元素

| MathML | LaTeX | 说明 |
|---|---|---|
| `mfrac(a,b)` | `\frac{a}{b}` | 分子分母各加 `{}`（原子不再包一层） |
| `msub(b,s)` | `b_{s}` | 基为多字符时加 `{}` |
| `msup(b,e)` | `b^{e}` | 同上；`e` 为 `mi` 且文本为 `e`/`10` 时按常数处理（见 §4） |
| `msubsup(b,s,e)` | `b_{s}^{e}` | 子脚本缺失时退化为单侧 |
| `msqrt(x)` | `\sqrt{x}` | 多个子节点按顺序拼接 |
| `mroot(x,n)` | `\sqrt[n]{x}` | 子节点不足记 `mroot_arity` |
| `mfenced(open,close)` | `\left( … \right)` | 分隔符取元素属性，缺省 `(` `)` |
| `mtable` 2 列多行 | `\begin{cases} … \end{cases}` | 记 `mtable_as_cases`（可能是分段函数，也可能是两列矩阵，需人工确认） |
| `mtable` 其他 | `\begin{matrix} … \end{matrix}` | 记 `mtable_as_matrix` |
| `munder(b,x)` | `b_{x}` | |
| `mover(b,x)` | `b^{x}`；若 x 为 `^ ~ ¯` 则 `\overline{b}` | 记 `accent_normalized` |
| `munderover(b,lo,hi)` | `b_{lo}^{hi}` | 基不是 `\sum/\prod/\int/lim/…` 时记 `munderover_nonbigop` |
| `mrow/mstyle/mpadded/mphantom/menclose/mtd/math` | 透明：按顺序拼接子节点 | |
| `mspace/none/prescripts` | 空串 | |
| `semantics` | 优先 `annotation[encoding=application/x-tex]` 原文 | `latex_source=mml_annotation` |
| `mtext` | `\text{…}` | `_`、`%` 转义 |
| `mmultiscripts` 等未列为分支的元素 | `\square` + `flags` | 不猜测 |

## 2. 记号元素

- `mi`：单字符 → 原样（希腊字母映射为 `\alpha` 等）；多字符 → `\mathrm{...}`；函数名（`sin cos tan log ln exp max min lim sup inf det arg gcd`）→ `\sin` 等，并记入 `formulas[].operators` 而非 `symbols`。
- `mn`：数字原样，去内部空格（千位分隔另见 `indicator_checks`）。
- `mo`：查 `OPS` 表；未命中但对每个字符可映射时逐字符映射，否则 `\square`。

`OPS` 覆盖：`- + = < > * / , ; ( ) [ ] | × · ± ≤ ≥ ≠ ≈ ∼ ∝ → ∑ ∏ ∫ √ ° % _`。

## 3. 希腊字母

`α β γ δ ε ζ η θ ι κ λ μ ν ξ ο π ρ σ τ υ φ χ ψ ω` 与 `Γ Δ Θ Λ Ξ Π Σ Υ Φ Ψ Ω` 映射为对应命令；`ϵ→\epsilon`、`ϕ→\phi`、`∂→\partial`。其余字母（如 `ϱ`）→ `\square` 并记 flag。

## 4. 符号表抽取规则

1. **变量**：`mi` 原子，以及 `msub/msup/msubsup` 的 `mi` 基。`msub` 取下标（`k_{B}`），`msup` 取上标（`c^{2}`），`msubsup` 两者都取。
2. **自然常数**：`msup` 基为 `e` 或 `10` 时不产出变量，继续遍历指数（`e^{kt}` 产出 `k`、`t`）。
3. **算子**：函数名、`∂`/`∇`/`d`（微分）单列，不要求变量表覆盖。
4. `plain` 字段是去掉 `\mathrm{}`、`{}`、`^`、`_`、反斜杠后的可检索形式（`k_{B}` → `kB`），用于在正文中定位定义。

## 5. 未支持/需人工确认的信号（看 `flags`）

`unmapped:<元素名>`、`mfrac_arity`、`mroot_arity`、`msub_arity`/`msup_arity`/`msubsup_arity`、`max_nesting_depth`、`mtable_as_cases`、`mtable_as_matrix`、`munderover_nonbigop`、`accent_normalized`、`empty_mtable`、`placeholder_square`、`xml_unparsed`、`unbalanced_braces`、`empty_latex`、`mtable` 宽度为 2 被判为 cases 但实为两列矩阵的情况。

出现 `placeholder_square` 的公式 `status=needs_review`，且该处必在 `uncertainties` 中有对应条目。
