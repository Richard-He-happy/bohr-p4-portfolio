# Minimal call example (EXAMPLE — not an official case result)

> **All data below is a hand-written fixture created to show the interface.** It is not a platform
> case, not an official answer, and every record, DOI and number is invented for illustration.

## 1. Input

`/input/case.json`

```json
{
  "case_id": "example-001",
  "task_instruction": "Which home-based interventions reduce asthma exacerbations in children under 12?",
  "organizer_supplied_scope": {"db": "PubMed", "years": "2010-2024", "lang": "English"},
  "include_criteria": ["children under 12 with asthma", "home-based intervention", "exacerbation outcome"],
  "exclude_criteria": ["conference abstract", "language other than English", "published before 2010"],
  "output_contract": {"candidates": {"type": "array"}, "queries": {"type": "array"},
                      "screening": {"type": "array"}, "counts": {"type": "object"},
                      "coverage": {"type": "object"}}
}
```

`/input/artifacts/records.jsonl` — 5 records (abridged): two copies of one trial (same DOI, one from
PubMed and one from Embase with a slightly different title), one adult-COPD record, one conference
abstract on the right topic, one telemonitoring trial.

## 2. Call

```bash
python3 scripts/main.py -i /input -o /app/output        # run
python3 scripts/main.py -i /input -o /app/output --check # verify the run
```

## 3. Output (EXAMPLE)

`counts`

```json
{"retrieved_total": 5, "unique_after_dedup": 4, "duplicates_removed": 1, "screened_total": 5,
 "include": 2, "exclude": 3, "pending_human": 0, "conflicts": 0}
```

`dedup.clusters`

```json
[{"cluster_id": "D001", "keeper": "P1", "members": ["P1", "P1b"],
  "basis": ["identical DOI 10.1000/ja.2018.001"], "preprint_published_mix": false,
  "reason_codes": ["DUP-DOI"]}]
```

`screening` (one row per record, abridged to the decisive fields)

| record | A | B | final | reason_codes | coverage |
|---|---|---|---|---|---|
| P1 | include | include | include | `INC-MATCH:INC-01+INC-02+INC-03` | 1.0 |
| P1b | exclude | exclude | exclude | `DUP-MERGED` | 0.0 |
| P2 | exclude | exclude | exclude | `SYS-NO-CRIT-MATCH` | 0.33 |
| P3 | exclude | exclude | exclude | `EXC-PUBTYPE` | 1.0 |
| P4 | include | include | include | `INC-MATCH:INC-01+INC-02+INC-03` | 1.0 |

`candidates[0]`

```json
{"rank": 1, "id": "P1", "title": "Home-based environmental intervention reduces asthma exacerbations in children: a randomized trial",
 "authors": ["Smith J", "Lee K"], "year": 2018, "venue": "Journal of Asthma", "doi": "10.1000/ja.2018.001",
 "source_db": "PubMed", "query_id": "Q1", "retrieved_at": "2024-03-01",
 "relevance_score": 0.9, "relevance_reason": "INC-MATCH:INC-01+INC-02+INC-03",
 "evidence_snippet": "We randomized 120 children under 12 with asthma to a home-based environmental intervention.",
 "evidence_locator": "abstract:chars[0:118]", "metadata_confidence": 0.75, "flags": []}
```

Files produced: `result.json`, `candidates.csv`, `screening_labels.csv`, `arbitration.csv`,
`query_log.json`, `dedup_log.json`, `audit.json` (+ `verification_report.json` after `--check`).

## 4. Reading the example correctly

- P1b is **not** a separate study: the DOI is identical, so it is merged and counted once in
  `screened_total` while still appearing in `screening` with `DUP-MERGED` (audit trail, not a label).
- P3 matches all three inclusion criteria but carries a conference-abstract publication type, so the
  hard exclusion wins. This is the case where a naive relevance ranker would wrongly include it.
- P2 matches one criterion only (the word "asthma" appears), so coverage is 1/3 and it is excluded
  with `SYS-NO-CRIT-MATCH`; nothing is fabricated to justify the exclusion beyond its own title.
- κ(A,B) = 1.0 here because the fixture is small and unambiguous; real snapshots produce conflicts
  and those land in `arbitration.csv` with `requires_human`.

## 5. Maintenance

- Versions: skill `1.0.0`, criteria scheme `v1` (`references/criteria-codes.md`), Python ≥ 3.8,
  standard library only, no network.
- To change screening behaviour, edit the thresholds in `scripts/verify.py::scr` **and** bump
  `criteria.version` so exported labels remain distinguishable.
- Re-run `python3 scripts/main.py --check` after any edit; it fails loudly if the contract, evidence
  quotes, traceability or count closure break.
