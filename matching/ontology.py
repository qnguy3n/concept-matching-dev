"""Ontology helpers for matching: CUI canonicalization and disorder roll-up.

Port of cohort-builder `src/lib/ontology.ts`. The concept set itself is NOT
copied here: it is read from concept-extraction's `ontology/data.py`, the single
source of truth (the cohort-builder's `ontology.generated.ts` is exported from
the same file). concept-extraction is found as an installed `ontology` package,
else at `$CONCEPT_EXTRACTION_DIR`, else at the sibling `../concept-extraction-dev`
or `../concept-extraction` checkout.

Subsumption: a patient coded "Parkinson disease" must match a "Parkinsonism"
criterion. Each patient's match-set is rolled UP to its disorder ancestors
(`roll_up_match_set`), so the matcher itself only tests set membership.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path

_SIBLINGS = ("concept-extraction-dev", "concept-extraction")


def _load_concepts() -> list[dict]:
    try:
        from ontology.data import CONCEPTS  # type: ignore[import-not-found]
        return CONCEPTS
    except ImportError:
        pass
    root = Path(__file__).resolve().parents[2]
    candidates = [os.environ.get("CONCEPT_EXTRACTION_DIR")] + [str(root / s) for s in _SIBLINGS]
    for d in candidates:
        if d and (Path(d) / "ontology" / "data.py").exists():
            sys.path.insert(0, d)
            from ontology.data import CONCEPTS  # type: ignore[import-not-found]
            return CONCEPTS
    raise ImportError(
        "concept-extraction ontology not found: install concept-extraction, set "
        "CONCEPT_EXTRACTION_DIR, or check it out next to concept-matching-dev"
    )


@lru_cache(maxsize=1)
def concepts_by_cui() -> dict[str, dict]:
    return {c["cui"]: c for c in _load_concepts()}


@lru_cache(maxsize=1)
def _children() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for c in concepts_by_cui().values():
        if c.get("parent"):
            out.setdefault(c["parent"], []).append(c["cui"])
    return out


def label(cui: str) -> str | None:
    c = concepts_by_cui().get(cui)
    return c["label"] if c else None


# Legacy cohort-builder mock CUIs superseded by a different ontology CUI for the
# same concept. Study criteria are canonicalized to the ontology code so both
# sides of matching speak the same CUI.
MOCK_TO_ONTOLOGY: dict[str, str] = {
    "C0030554": "C0038868",  # Progressive supranuclear palsy
    "C0024183": "C0393571",  # Multiple system atrophy
    "C0014534": "C0472349",  # Drug-resistant epilepsy
    "C1306006": "C0027873",  # Neuromyelitis optica (NMOSD)
    "C0085584": "C0009088",  # Cluster headache
}


def canonical_cui(cui: str) -> str:
    return MOCK_TO_ONTOLOGY.get(cui, cui)


def canonicalize_cuis(cuis: Iterable[str]) -> list[str]:
    """Canonicalize and de-duplicate, keeping first-seen order."""
    return list(dict.fromkeys(canonical_cui(c) for c in cuis))


def descendants(cui: str) -> set[str]:
    """All transitive descendants (excludes the CUI itself)."""
    out: set[str] = set()
    stack = list(_children().get(cui, []))
    while stack:
        x = stack.pop()
        if x in out:
            continue
        out.add(x)
        stack.extend(_children().get(x, []))
    return out


def disorder_ancestors(cui: str, no_roll_up: frozenset[str] = frozenset()) -> list[str]:
    """Disorder-only ancestor chain (excludes the CUI itself).

    Roll-up stops at the first non-disorder edge, so loose groupings (a finding
    parented under a disorder family, e.g. Photophobia under Headache) don't
    create false matches. A CUI in `no_roll_up` neither rolls up nor is rolled
    past (v2.1: MCI is not Dementia).
    """
    by_cui = concepts_by_cui()
    node = by_cui.get(cui)
    out: list[str] = []
    if not node or node["cat"] != "disorder" or cui in no_roll_up:
        return out
    seen = {cui}
    while node and node.get("parent"):
        p = by_cui.get(node["parent"])
        if not p or p["cat"] != "disorder" or p["cui"] in seen:
            break
        out.append(p["cui"])
        seen.add(p["cui"])
        if p["cui"] in no_roll_up:
            break
        node = p
    return out


def roll_up_match_set(cuis: Iterable[str], no_roll_up: frozenset[str] = frozenset()) -> set[str]:
    """A patient's extracted CUIs plus every disorder ancestor of each."""
    cuis = list(cuis)
    out = set(cuis)
    for c in cuis:
        out.update(disorder_ancestors(c, no_roll_up))
    return out
