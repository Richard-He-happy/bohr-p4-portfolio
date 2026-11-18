# Page outline template (reusable)

The generated deck is one projection of this outline. Roles are ordered by the paper's **contribution**, not by its section order, so a Results-first paper still yields a motivation-first talk.

## 1. Role sequence and what each page must carry

| # | role | source preference (section keywords) | content on the page | evidence locator |
|---|---|---|---|---|
| 1 | `title` | paper title block, p.1 | paper title, authors/affiliation line | p.1 |
| 2 | `motivation` | introduction, background, abstract | the problem and why it is hard, 3 sentences max | p.X / Section |
| 3 | `approach` | abstract, introduction, method | what this paper does, in the authors' own wording ("we propose…") | p.X / Section |
| 4 | `method` | method, experiment | data, setting, procedure | p.X / Section |
| 5.. | `evidence` | Figure N / Table N captions + nearest result sentences | one figure or table per page: caption clause as claim, 2 result sentences | `Figure N, p.X` |
| .. | `discussion` | discussion, result | what the result means, interpretations the paper itself states | p.X / Section |
| .. | `limitation` | discussion, limitation | what the authors say does not hold yet | p.X / Section |
| .. | `conclusion` | conclusion, discussion | the takeaway claim | p.X / Section |
| .. | `thanks` (n ≥ 14) | acknowledgements | acknowledgement line, or author line if none | p.X |

## 2. Slide-count budget (`plan(n)`)

Start from `title, motivation, approach, method, discussion, limitation` + tail `conclusion` (+ `thanks` if n ≥ 14) and give the remaining slots to `evidence`. When the count is too small, drop roles in this fixed order — limitation → discussion → method → approach → motivation — so that the mainline (title → problem → evidence → conclusion) is the last thing standing. Below n = 4 the deck is title + motivation (+ conclusion).

Rules of thumb: 2–3 min per content page at a 15-minute talk; evidence pages should be ≥ 30 % of the deck when the paper has figures/tables.

## 3. Per-page limits (checked automatically)

- exactly **one claim** per page — the claim is a verbatim clause of the anchoring sentence;
- **≤ 5 bullets**, **≤ 190 characters** each (checked in `compliance_checks.overflow`);
- bullets are **prefix cuts at clause boundaries** (`, ` `; ` `. ` ` and ` ` — `) of paper sentences — never paraphrases, so numbers/units/method names stay byte-identical;
- every page needs **≥ 1 evidence item** and **non-empty notes**;
- figure/table pages state the id on the page (`Figure 1: …`) so the spoken reference and the paper's numbering agree.

## 4. Notes pattern

`If asked, cite <locator>; <locator>. Next: <next page role>.`
Optional second sentence when the paper offers an unused corroborating sentence. Notes never repeat bullet text (token overlap ≤ 0.6).

## 5. Example projection (12 slides, 3 figures)

```
1 title        Deep Residual Learning for Small-Sample Crop Disease Detection
2 motivation   Why this matters              (3 bullets, p.1 / Abstract)
3 approach     Our approach                  (3 bullets, p.1 / Abstract)
4 method       How the work was done         (3 bullets, p.1 / 2 Method)
5 discussion   What it means                 (3 bullets, p.1 / 4 Discussion)
6 limitation   Limits and open questions     (3 bullets, p.1 / 5 Limitations)
7 evidence     Figure 1: Accuracy vs training set size
8 evidence     Figure 2: Confusion matrix on the test split
9 evidence     Table 1: Comparison with baselines
10 evidence    Key evidence 1                (extra result sentences)
11 evidence    Key evidence 2
12 conclusion  Takeaways
```

## 6. Reuse notes

The outline is paper-independent. To adapt it to another venue, change only: role labels (`LBL` in `scripts/main.py`), the drop order in `plan(n)`, and the per-page bullet cap. Keep the one-claim-per-page rule and the locator requirement — they are what makes the deck auditable.
