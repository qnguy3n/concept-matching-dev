"""Eligibility expressions: compile a Study's criteria and evaluate them on a CUI set.

Port of the clause-aware matching in cohort-builder `src/lib/patients.ts`
(`groupsSatisfied`, `chainMatches`, `inclusionSelection`, `missingInclusion`,
`studyExclusionCuis`, `passesDemographics`).

Every representation compiles to one `Expr`: a function of the patient's CUI
match-set. Study CUIs are canonicalized once at compile time (the UI does so for
groups and legacy CUIs only; for the CUIs real patients carry this is the same).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from matching.models import Clause, Connector, Patient, Study
from matching.ontology import canonical_cui, canonicalize_cuis

Expr = Callable[[set[str]], bool]


def _union(clauses: list[Clause] | None) -> list[str]:
    return list(dict.fromkeys(c for cl in clauses or [] for c in cl.selected_cuis))


def groups_satisfied(groups: list[list[str]], cuis: set[str]) -> bool:
    """DNF: true when any non-empty group has all its CUIs present."""
    return any(g and all(c in cuis for c in g) for g in groups)


def chain_matches(ordered: list[str], connectors: dict[str, Connector], cuis: set[str],
                  default_op: Connector) -> bool:
    """Fold an ordered CUI list left to right with the connector placed before each CUI."""
    if not ordered:
        return True
    acc = ordered[0] in cuis
    for cui in ordered[1:]:
        b = cui in cuis
        acc = (acc and b) if connectors.get(cui, default_op) == "AND" else (acc or b)
    return acc


@dataclass(frozen=True)
class Side:
    """One side (inclusion or exclusion) of a study, in its effective representation."""

    kind: str  # 'groups' | 'chain' | 'mode' | 'none'
    cuis: tuple[str, ...] = ()
    groups: tuple[tuple[str, ...], ...] = ()
    mode: Connector = "AND"
    connectors: tuple[tuple[str, Connector], ...] = ()

    def satisfied(self, cuis: set[str]) -> bool:
        if self.kind == "groups":
            return groups_satisfied([list(g) for g in self.groups], cuis)
        if self.kind == "chain":
            return chain_matches(list(self.cuis), dict(self.connectors), cuis, self.mode)
        if self.kind == "mode":
            f = all if self.mode == "AND" else any
            return f(c in cuis for c in self.cuis)
        return True

    @property
    def all_cuis(self) -> list[str]:
        if self.kind == "groups":
            return list(dict.fromkeys(c for g in self.groups for c in g))
        return list(self.cuis)


def _uses_clauses(s: Study) -> bool:
    return bool(s.inclusion_clauses or s.exclusion_clauses or s.inclusion_groups or s.exclusion_groups)


def _side(s: Study, groups, order, clauses, mode: Connector, connectors, legacy: list[str],
          legacy_mode: Connector) -> Side:
    if not _uses_clauses(s):
        # Legacy flat CUIs: every inclusion CUI required (AND); any exclusion CUI excludes (OR).
        legacy = canonicalize_cuis(legacy)
        return Side("mode", cuis=tuple(legacy), mode=legacy_mode) if legacy else Side("none")
    if groups and any(groups):
        return Side("groups", groups=tuple(tuple(canonicalize_cuis(g)) for g in groups if g))
    if order:
        conns = tuple((canonical_cui(k), v) for k, v in connectors.items())
        return Side("chain", cuis=tuple(canonicalize_cuis(order)), mode=mode, connectors=conns)
    sel = canonicalize_cuis(_union(clauses))
    return Side("mode", cuis=tuple(sel), mode=mode) if sel else Side("none")


def inclusion_side(s: Study) -> Side:
    return _side(s, s.inclusion_groups, s.inclusion_order, s.inclusion_clauses, s.inclusion_mode,
                 s.inclusion_connectors, s.inclusion_cuis, legacy_mode="AND")


def exclusion_side(s: Study) -> Side:
    return _side(s, s.exclusion_groups, s.exclusion_order, s.exclusion_clauses, s.exclusion_mode,
                 s.exclusion_connectors, s.exclusion_cuis, legacy_mode="OR")


def inclusion_groups(s: Study) -> list[list[str]]:
    """A study's inclusion CUIs as OR-of-AND groups, whichever representation it uses
    (used by evidence scoring; port of `studyInclusionGroups`)."""
    if s.inclusion_groups and any(s.inclusion_groups):
        return [canonicalize_cuis(g) for g in s.inclusion_groups if g]
    if s.inclusion_order:
        return [canonicalize_cuis(s.inclusion_order)]
    if s.inclusion_clauses:
        return [canonicalize_cuis(_union(s.inclusion_clauses))]
    return [canonicalize_cuis(s.inclusion_cuis)] if s.inclusion_cuis else []


def missing_inclusion(side: Side, cuis: set[str]) -> list[list[str]]:
    """Why a patient fails inclusion: unmet requirements, each a list of alternative
    CUIs (one CUI = required; several = any one of them would do)."""
    if side.kind == "groups":
        groups = [list(g) for g in side.groups]
        common = [c for c in groups[0] if all(c in g for g in groups)]
        out = [[c] for c in common if c not in cuis]
        rest = [[c for c in g if c not in common] for g in groups]
        if all(rest) and not any(all(c in cuis for c in g) for g in rest):
            out.append(list(dict.fromkeys(c for g in rest for c in g if c not in cuis)))
        return out
    missing = [c for c in side.cuis if c not in cuis]
    if not missing:
        return []
    return [missing] if side.kind == "mode" and side.mode == "OR" else [[c] for c in missing]


def passes_status(s: Study, p: Patient) -> bool:
    return s.patient_status == "either" or p.status == s.patient_status


def passes_demographics(s: Study, p: Patient) -> bool:
    """Unknown age/gender fails a constraint on it (the UI treats them as 0 / male)."""
    if s.age_min is not None and (p.age is None or p.age < s.age_min):
        return False
    if s.age_max is not None and (p.age is None or p.age > s.age_max):
        return False
    if s.gender and p.gender != s.gender:
        return False
    if s.races and p.race not in s.races:
        return False
    if s.ethnicities and p.ethnicity not in s.ethnicities:
        return False
    return True
