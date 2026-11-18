---
name: systematic-screening-audit
description: Run an auditable systematic literature screening on an organizer record snapshot - criteria operationalization with version fingerprint, query log, DOI/title/fuzzy dedup with merge basis, title/abstract inclusion-exclusion with reason codes and verbatim evidence quotes, dual-annotator conflict arbitration, count-closure audit chain, and a reusable label/arbitration/audit export. Use for systematic or scoping review screening, PRISMA-style record triage, duplicate merging, inclusion-exclusion labelling, or when a reviewer must reproduce why N records became k.
version: 1.0.0
---

# systematic-screening-audit

## 1. Purpose and scope

Turn a research question plus a record snapshot into an auditable screening result: every record
gets an include/exclude/unresolved label, a reason code tied to a criterion, and a verbatim quote
from its own title or abstract; every stage count closes; every merge and every disagreement is
recorded. The deliverable answers "why did 1832 records become 47" without narration.

In scope: criteria, query logging, dedup, title/abstract screening, dual annotation, arbitration,
audit chain, process metrics. Out of scope: full-text appraisal, data extraction, meta-analysis,
manuscript writing, any claim of global recall (no live database).

## 2. When to use / not use

Use when the case supplies criteria plus a record set (JSON/JSONL/CSV/TSV exports, any key names).
Not for PDF/XLSX-only record sets, full-text appraisal, or as a substitute for researcher judgement
on borderline papers — those land in `pending_human` by design.

## 3. Runtime contract

- Input `/input` (read-only): `case.json` + `task.md` + `artifacts/` + any material files.
- Output `/app/output`: `result.json` + CSVs + JSON logs. Work dir `/app/work` is not required.
- Offline, standard library only, no network, no CWD dependence (`Path(__file__)`).
- Budgets: 64 model requests, 900 s, 16384 tokens/response. The pipeline is CPU-only and finishes in
  well under a second per case.
- **A legal partial `result.json` is written before any screening**, and every failure path exits 0.

## 4. Input discovery

Semantic, never key-name based: the case is `/input/case.json` (else the first `**/case*.json`);
criteria are any dict key containing `include`/`inclusion`/`exclude`/`exclusion` with a list value; scope is any dict under
`scope|search_scope|organizer_supplied_scope|constraints`; the question is the longest of
`research_question|question|topic|task_instruction|objective|aim|instruction`; records are any
`json/jsonl/ndjson` objects carrying a title/abstract/DOI, or `csv/tsv` rows with the same. Field
aliases (title, abstract, authors, year, venue, doi, url, source_db, language, pubtype, id, query_id,
retrieved_at) are matched case-insensitively. Details: `references/io-schema.md` §1.

## 5. Output contract

`result.json` carries every input `output_contract` key with its name unchanged (unknown keys kept,
missing values `null`/`[]`/`{}`), plus `case_id`, `status` (`ok|partial|insufficient_evidence|
input_error`), `sources`, `uncertainty`, `pending_human`, `errors`, `degradations`, `changes`,
`runtime`, and the substantive sections `candidates`, `queries`, `screening`, `dedup`, `arbitration`,
`counts`, `audit`, `coverage`, `metrics`, `criteria`. Artifacts: `candidates.csv`,
`screening_labels.csv`, `arbitration.csv`, `query_log.json`, `dedup_log.json`, `audit.json`.
Field-by-field table: `references/io-schema.md` §2-3.

## 6. Core workflow

1. Parse case; discover criteria, scope, question; write partial result.
2. Operationalize criteria into `INC-nn`/`EXC-nn` rows with cue tokens, version `v1`, SHA-256
   fingerprint (typed criteria keep discriminating words even when those are stopwords).
3. Log queries: one entry per `query_id` on records with db, hits, retrieved_at, status;
   unreturned queries are `not_executed_offline`, never faked.
4. Dedup: DOI → normalized title → fuzzy title (>0.919) with same first author and year within 1.
   Keeper = most complete record; each removal records its basis; 0.80–0.92 pairs are exported as
   *not merged* (false-merge guard).
5. Screen: match inclusion cues and exclusion constraints, take verbatim quotes, compute coverage,
   emit strict (A) and lenient (B) labels with reason codes, score, confidence, flags.
6. Arbitrate: agreement → that label; hard exclusion → exclude; full coverage with verbatim evidence
   → include; zero coverage → exclude; else `pending_human` (two `uncertain` labels are never averaged).
7. Audit `retrieved = unique + duplicates` and `screened = include + exclude + pending`; report
   `partial` with an error entry if either fails.
8. Emit ranked candidates, label table, arbitration table, logs, process metrics.

## 7. Rubric mapping (task §2 → field / check / artifact)

| Rubric item | Where it is satisfied |
|---|---|
| Task completion (closed loop) | `criteria` → `queries` → `dedup` → `screening` → `arbitration` → `candidates`, each with counts |
| Result correctness | `screening[].matched_criteria` + `evidence[]` quotes; labels re-derivable from criteria |
| Result completeness | every stage present; `screening[]` includes removed duplicates (`DUP-MERGED`) |
| Verifiability | `queries[]` (db/raw/hits/retrieved_at), `dedup[].basis`, per-record `evidence_locator`, `audit.closure`; `--check` re-proves all of it |
| Quality gain | `metrics.kappa_A_B`, `criteria_traceability`, `evidence_rate`, `human_review_load`; no accuracy claim without gold labels (`metrics.note`) |
| Efficiency gain | `metrics.records_per_second`, `human_review_load` = (pending + conflicts)/screened |
| Innovation | criteria fingerprint + full re-screen, reason-code dictionary, conflict typing, audit closure (`references/criteria-codes.md`) |
| Trigger / ease of use | one command, `--help`, `--check`; no configuration required |
| Stability | deterministic; identical input → identical counts; no randomness, no clock in decisions |
| Exception handling | §10 table; `errors`/`uncertainty`/`pending_human` populated honestly |
| Ecosystem | `references/` protocol, code dictionary, schema, example; CSV tables reusable in any review |

## 8. Evidence and locator rules

Every include, every text exclusion and every boundary judgement stores `quote` copied verbatim from
`title` or `abstract`, plus `locator` (`title:chars[a:b]` / `abstract:chars[a:b]`). Quotes are never
paraphrased and never assembled across sentences: if no sentence contains the cue, the span is cut
around the cue instead. `main.py --check` re-reads the source records and re-tests each quote; a
quote that does not appear verbatim is reported as a failure, and the record is not rewritten to
make it pass.

## 9. Conflicts and human confirmation

A = strict (100% inclusion coverage), B = lenient (≥50%). They are **rule configurations, not human
annotators**; `method_disclosure` says so in every result. Conflict types: `threshold_policy`,
`criteria_boundary`, `evidence_sparse`, `criteria_ambiguous`. Precedence is fixed
(`references/criteria-codes.md` §4). Unresolved items go to `pending_human` with a reason — never
silently to include or exclude. The included set needs researcher sign-off.

## 10. Exception and degradation table

| Situation | Handling |
|---|---|
| `case.json` missing / invalid JSON | try other `case*.json`; else `status: input_error`, errors logged, contract unknown → `[]` payload, exit 0 |
| no records parsed | `status: insufficient_evidence`, `candidates: []`, uncertainty explains; nothing invented |
| abstract missing | record still screened on title; flag `NO_ABSTRACT`, confidence ≤0.35, coverage-weighted score down |
| DOI missing | dedup falls back to normalized title and fuzzy+author rules; flag `NO_DOI` |
| encoding/mojibake | decode utf-8-sig→utf-8→gb18030→cp1252; cp1252-repair applied only when it reduces replacement chars |
| mixed export formats | per-file readers for json/jsonl/ndjson/csv/tsv with delimiter sniffing; one bad file logs an error and the run continues |
| criteria absent | every record `SYS-NO-CRIT` → `pending_human`; status partial |
| two annotators deadlocked | rule precedence then `pending_human`; never averaged |
| count closure fails | error entry + `status: partial`; numbers left as computed |
| output dir unwritable | fallback `./output` used; no crash |

## 11. Budget and checkpoints

Partial result is on disk within milliseconds; screening is linear and memory-bound. If interrupted,
`result.json` is already valid JSON with `status: partial` and an explanation.

## 12. Self-check

```bash
python3 scripts/main.py -i /input -o /app/output          # run
python3 scripts/main.py --check -i /input -o /app/output  # verify
```
`--check` asserts: contract keys backfilled, case_id preserved, status in enum, artifacts present,
candidates traceable to source records with well-formed DOIs, every evidence quote verbatim, both
count identities, candidates ≡ included labels, dedup cluster integrity, arbitration row validity,
CSV row count. It writes `verification_report.json` and always exits 0.

## 13. Minimal example

`references/examples.md` holds a hand-written fixture with its command and an example output
excerpt. **It is labelled as an example, not an official case result.** Short form:

```bash
python3 scripts/main.py -i /input -o /app/output
# -> [done] status=ok include=2 exclude=3 pending=0 candidates=2
```

## 14. Files, versions and maintenance

| File | Role |
|---|---|
| `SKILL.md` | this contract |
| `scripts/main.py` | CLI: run pipeline, `--check`; contract backfill; artifact writers |
| `scripts/verify.py` | shared deterministic core (normalization, discovery, criteria, dedup, screening, arbitration) + `check()` |
| `references/criteria-codes.md` | reason-code dictionary, conflict taxonomy, arbitration precedence, dedup rules, criteria versioning |
| `references/io-schema.md` | input discovery, output schema, audit identities, status semantics |
| `references/examples.md` | labelled example, maintenance notes |

Version 1.0.0; criteria scheme v1; Python ≥ 3.8; standard library only. Behaviour changes require
bumping `criteria.version` in `verify.py::bcr` and re-running `--check`. Known limits: PDF/XLSX
records and full-text screening are not supported; recall is not estimable from a finite snapshot;
"dual annotation" is rule-based, so inter-annotator agreement is a policy-consistency measure, not a
human reliability estimate.
