# concept-matching

Patient ↔ study matching for the cohort builder, split out of the cohort-builder UI. It reads the patient CUIs that [concept-extraction](../concept-extraction-dev) writes to its store. It then sorts each study's patients into **matched / excluded / not included** and ranks each group by note evidence.

This package handles matching only. Extraction is in `concept-extraction`, and display is in `cohort-builder`.

**Requires the concept-extraction v2.1 store schema**, the same pin as cohort-builder's `package.json` → `conceptExtraction`. The ontology is not copied here. It is read from concept-extraction's `ontology/data.py`, so the hierarchy always matches the extraction that produced the store.

## Origin

This package is a Python port of the matching logic in `cohort-builder` at `f9a47e9`:

| Here | cohort-builder |
|------|----------------|
| `matching/criteria.py` | `src/lib/patients.ts`: `groupsSatisfied`, `chainMatches`, `inclusionSelection`, `studyExclusionCuis`, `missingInclusion`, `passesDemographics` |
| `matching/matcher.py` | `src/lib/patients.ts`: `matchStudyForStudy`, `excludedForStudy`, `notIncludedForStudy`, plus the ranking in `src/routes/studies/[id]/+page.svelte` |
| `matching/scoring.py` | `src/lib/scoring.ts`: `inclusionEvidenceScore`, `studyInclusionGroups` |
| `matching/ontology.py` | `src/lib/ontology.ts`: canonical CUIs, disorder roll-up |
| `matching/versions.py` | `src/lib/versions.ts`: pipeline versions and roll-up exceptions |
| `matching/store.py` | `src/lib/server/liveDb.ts`: `listLivePatients` / `listLiveSummaries` (loading only, no PHI) |
| `studies/dbs_eval_v1.json` | `src/lib/liveStudies.ts` (the matchable fields) |

The UI still has its own TypeScript copy and does not call this package yet. If you change matching, change it in both places until the UI is moved over.

## How matching works

1. **Load** (`store.py`). Each patient's match-set holds their **affirmed** CUIs (`patient_cui.affirmed = 1`) plus every **disorder ancestor** of each one. Example: Young-onset PD also counts as Parkinson disease.
   - Roll-up stops at the first non-disorder edge, so findings never roll up.
   - In v2.1, mild cognitive impairment does not roll up to Dementia.
   - Negated and family-history mentions are kept as evidence but never matched on.
2. **Classify** (`criteria.py`, `matcher.py`).
   - Patients who fail the study's status or demographic constraints are dropped. An unknown age or gender fails a constraint on it.
   - Each remaining patient is then classified:
     - `not_included`: the inclusion expression is false. `missing` lists the unmet requirements, each as a list of alternative CUIs.
     - `excluded`: inclusion passes and the exclusion expression is true. `reasons` lists the exclusion CUIs present.
     - `matched`: inclusion passes and exclusion doesn't.
   - Each side of a study uses the first representation it has, as in the UI:
     1. `inclusionGroups` / `exclusionGroups`: OR of AND-groups.
     2. `inclusionOrder` with `inclusionConnectors`: a left-to-right chain of AND/OR.
     3. The union of the clauses' `selectedCuis`, combined by `inclusionMode` (AND) / `exclusionMode` (OR).
     4. Legacy flat `inclusionCuis` (all required) / `exclusionCuis` (any excludes).
3. **Score** (`scoring.py`). For each inclusion CUI, take the share of the patient's notes that mention it or a descendant, then average over the CUIs in the group. The best group gives a score from 0 to 100. Which mentions count depends on the version:
   - v1: every mention.
   - v2 and later: affirmed, patient-experiencer mentions only, skipping boilerplate (`context = "template"`, which only v2.1 stores mark).
   - Each tier is sorted by score, then by mentions. Patients without note evidence go last.

### Differences from the UI

- **Canonical CUIs.** Study CUIs are canonicalized (legacy mock CUI → ontology CUI) on every side. The UI does this only for groups and legacy CUIs. Real patients only carry ontology CUIs, so results are the same.
- **Legacy studies.** Studies that use only the legacy flat CUIs also get demographic constraints applied. The UI skips them on that path.
- **Unknown age or gender.** These fail a constraint instead of being read as `0` and `male`.
- **Measurement constraints.** `inclusionConstraints` / `exclusionConstraints` (lab thresholds) are stored by the UI but not matched there either, so they are ignored here too.

## Run

```bash
PYTHONPATH=. python -m scripts.run_matching --hospital-id <id> \
    --study studies/dbs_eval_v1.json --version v2.1 [--db PATH] [--out results.json]
```

`--study` takes a cohort-builder Study JSON (camelCase) or a list of them, and can be repeated. The store path defaults to the same env vars as the cohort-builder:

| Version | Env var | Default |
|---------|---------|---------|
| v1 | `COHORT_DB_PATH_V1` | `../concept-extraction/data/olivo_poc_v1.db` |
| v2 | `COHORT_DB_PATH` | `../concept-extraction/data/olivo_poc.db` |
| v2.1 | `COHORT_DB_PATH_V2_1` | `../concept-extraction/data/olivo_poc_v2_1.db` |

The output contains patient ids, tiers, scores, reasons and missing CUIs only. PHI (`phi_json`) is never read.

The ontology is found in this order:
1. an installed `ontology` package;
2. `$CONCEPT_EXTRACTION_DIR`;
3. the sibling checkout `../concept-extraction-dev`, then `../concept-extraction`.

Library use:

```python
from matching import Study, match_study
from matching.store import load_patients

result = match_study(Study.from_dict(study_json), load_patients("ka98", "v2.1"), "v2.1")
```

## Folder structure

- `matching/`: the package (`models`, `ontology`, `versions`, `criteria`, `scoring`, `matcher`, `store`).
- `scripts/run_matching.py`: the CLI.
- `studies/`: study definitions in cohort-builder JSON.
- `tests/`: run with `python -m pytest` from this folder. The tests use the real ontology and a temporary SQLite store.
