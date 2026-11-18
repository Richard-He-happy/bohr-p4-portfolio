# Criteria, reason codes and arbitration rules (v1)

This file is the normative dictionary the engine implements. `scripts/verify.py` emits these codes
verbatim; do not rename them in reports without a version bump.

## 1. Operationalizing the organizer criteria

The input snapshot supplies inclusion/exclusion criteria as free text (any key name, any nesting;
`scripts/main.py::scan` finds them). Each criterion becomes one versioned row:

| Field | Meaning |
|---|---|
| `id` | `INC-01…` for inclusion, `EXC-01…` for exclusion, in input order |
| `text` | the organizer wording, unchanged |
| `kind` | `text` / `year` / `language` / `pubtype` (auto-classified from the wording) |
| `cues` | detection tokens: content 2-grams + single terms with stopwords removed; for `year`/`language`/`pubtype` the unfiltered terms are kept because the discriminating word ("conference", "English") is itself a stopword |

`criteria.fingerprint` = first 16 hex of SHA-256 over the ordered criterion lists. Store it with
every exported label table: two runs whose fingerprints differ **must not** have their labels
pooled.

**Why cue matching instead of a learned classifier:** every decision must be explainable by a quote
a third party can find in the title/abstract. Cue matching keeps that property; it also means a
record whose relevant statement uses unanticipated vocabulary lands in `uncertain`, never in a
silently confident include.

## 2. Reason codes

**Include** — `INC-MATCH:INC-01+INC-02+…` (every inclusion criterion matched), one code per decision.

**Exclude**

| Code | Trigger | Evidence field |
|---|---|---|
| `EXC-YEAR` | record year outside the window parsed from scope/exclusion text | `metadata:year` |
| `EXC-LANG` | record language (when present) is not English/Chinese | `metadata:language` |
| `EXC-PUBTYPE` | publication type/venue matches an excluded type (conference abstract, editorial, preprint, thesis, protocol…) | `metadata:publication_type` |
| `EXC-TEXT` | a text exclusion criterion matched title/abstract | quote from that field |
| `SYS-NO-CRIT-MATCH` | no inclusion criterion matched, or coverage < 1/3 | title quote |
| `SYS-DUP` / `DUP-MERGED` | record is a removed duplicate copy | `dedup:<cluster_id>` |

**Uncertain / human**

| Code | Meaning |
|---|---|
| `SYS-NO-TITLE` | no title recoverable — nothing to screen |
| `SYS-NO-CRIT` | snapshot supplied no inclusion criteria; cannot screen |
| `UNC-PARTIAL-MATCH` | 1/3 ≤ coverage < 1: partly on-topic, needs a researcher |

Codes are additive evidence, not a ranking. A record may carry several; `reason_codes[0]` is the
primary one and is what appears in `candidates[].relevance_reason`.

## 3. Dual annotation and conflict types

Annotator **A (strict)** includes only at 100% inclusion coverage; **B (lenient)** includes from 50%
with at least one matched criterion. Both read the same evidence; only the threshold differs. They
are **rule configurations, not humans** — this is stated in `result.method_disclosure` and must
stay in any downstream report.

| A vs B | `conflict_type` | Meaning |
|---|---|---|
| include / uncertain | `threshold_policy` | record clears A but not B's evidence bar |
| include / exclude | `criteria_boundary` | one configuration saw a criterion the other did not |
| exclude / uncertain | `evidence_sparse` | nothing decisive either way |
| uncertain / uncertain | `criteria_ambiguous` | criterion wording itself is not decidable from a title/abstract |

## 4. Arbitration precedence (policy v1)

Applied in order; the first rule that fires decides `final`:

1. **Agreement** — A = B → that label. Two `uncertain` labels → `pending_human`
   (`unresolved_uncertainty`), never a silent third state.
2. **Hard exclusion** — a `year`/`language`/`pubtype` constraint fired → `exclude`
   (`hard_exclusion_precedence`). Hard constraints outrank any agreement to include.
3. **Full coverage with verbatim evidence** — 100% inclusion coverage and at least one quote from
   title/abstract → `include`.
4. **Zero coverage** → `exclude` (`no_inclusion_criterion_matched`).
5. **Otherwise** → `pending_human` (`borderline_unresolved`). Never average, never majority-vote.

`requires_human` is true when the outcome is `pending_human` or confidence < 0.5.

## 5. Dedup decision rules

Merged when **either** holds:

| Rule | Condition | Recorded basis |
|---|---|---|
| DOI identity | normalized DOIs equal, length > 7 | `identical DOI <doi>` |
| Title identity | normalized titles equal and ≥ 30 chars | `identical normalized title` |
| Fuzzy identity | title token Jaccard > 0.919 **and** same first-author surname **and** year within 1 | `fuzzy title Jaccard 0.9xx + same first author + year within 1` |

Keeper = most complete record (has abstract, DOI, authors, venue, not a preprint). Every removed
copy names its keeper and basis; `preprint_published_mix` flags a cluster mixing an archive version
with a journal version.

**False-merge guard:** pairs with 0.80 ≤ Jaccard < 0.92 are reported in
`dedup.near_misses_not_merged` with `decision: "not merged"`. This is deliberate — title similarity
alone must never merge two different studies. If a reviewer believes such a pair is one study, the
fix is a manual merge recorded against the cluster, not a lower global threshold.

## 6. Criteria version management

- `criteria.version` starts at `v1`; it changes only when the organizer wording changes.
- The engine always screens the whole snapshot against the **current** fingerprint. It never reuses
  labels produced under another fingerprint, so "screened early, criteria edited later" drift cannot
  survive a run.
- When criteria change mid-study: bump the version, re-run, and diff `counts` against the previous
  `audit.json`; records whose label flipped are exactly those with changed `matched_criteria`.
