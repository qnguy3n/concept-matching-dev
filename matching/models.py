"""Data shapes for matching: patients (from the extraction store) and studies.

`Study.from_dict` reads the cohort-builder's Study JSON (camelCase), so a study
exported from the UI can be matched here without conversion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Connector = Literal["AND", "OR"]


@dataclass
class Evidence:
    """Provenance of one CUI mention (see concept-extraction store `evidence_json`)."""

    kind: str  # 'note' | 'structured'
    doc_id: str | None = None
    doc_date: str | None = None
    negated: bool | None = None
    experiencer: str | None = None  # 'patient' | 'family'
    quantifier: str | None = None
    temporality: str | None = None
    context: str | None = None  # 'template' = boilerplate (v2.1)
    # Text fields; only needed for display.
    doc_title: str | None = None
    snippet: str | None = None
    matched_text: str | None = None
    start: int | None = None
    end: int | None = None

    @classmethod
    def from_store(cls, e: dict[str, Any]) -> Evidence:
        return cls(**{k: e.get(k) for k in cls.__dataclass_fields__})


@dataclass
class ExtractedCui:
    cui: str
    label: str | None
    source: str  # 'structured' | 'unstructured'
    native_system: str | None = None
    native_code: str | None = None
    evidence: list[Evidence] = field(default_factory=list)


@dataclass
class Patient:
    patient_id: str
    hospital_id: str
    age: int | None = None
    gender: str | None = None
    race: str | None = None  # normalized, see store.map_race
    ethnicity: str | None = None  # normalized, see store.map_ethnicity
    state: str | None = None
    status: str = "living"
    # Match-set: affirmed CUIs rolled up to their disorder ancestors.
    cuis: set[str] = field(default_factory=set)
    # Affirmed mentions, and negated / family-history ones (never matched on).
    cui_detail: list[ExtractedCui] = field(default_factory=list)
    unaffirmed_cui_detail: list[ExtractedCui] = field(default_factory=list)


@dataclass
class Clause:
    phrase: str
    cuis: list[str]
    selected_cuis: list[str]


@dataclass
class Study:
    """The matchable part of a cohort-builder Study.

    Inclusion is taken from the first representation present, in the UI's order of
    precedence: `inclusion_groups` (OR of AND-groups) → `inclusion_order` chain with
    per-CUI connectors → union of clause selections combined by `inclusion_mode` →
    legacy flat `inclusion_cuis` (all required). Exclusion likewise; a patient is
    excluded when the exclusion expression is satisfied.
    """

    id: str
    name: str = ""
    patient_status: str = "either"  # 'living' | 'deceased' | 'either'
    inclusion_cuis: list[str] = field(default_factory=list)
    exclusion_cuis: list[str] = field(default_factory=list)
    inclusion_clauses: list[Clause] | None = None
    exclusion_clauses: list[Clause] | None = None
    inclusion_mode: Connector = "AND"
    exclusion_mode: Connector = "OR"
    inclusion_connectors: dict[str, Connector] = field(default_factory=dict)
    exclusion_connectors: dict[str, Connector] = field(default_factory=dict)
    inclusion_order: list[str] | None = None
    exclusion_order: list[str] | None = None
    inclusion_groups: list[list[str]] | None = None
    exclusion_groups: list[list[str]] | None = None
    age_min: int | None = None
    age_max: int | None = None
    gender: str | None = None
    races: list[str] | None = None
    ethnicities: list[str] | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Study:
        def clauses(key: str) -> list[Clause] | None:
            raw = d.get(key)
            if raw is None:
                return None
            return [Clause(c.get("phrase", ""), c.get("cuis", []), c.get("selectedCuis", [])) for c in raw]

        return cls(
            id=d["id"],
            name=d.get("name", ""),
            patient_status=d.get("patientStatus", "either"),
            inclusion_cuis=d.get("inclusionCuis", []),
            exclusion_cuis=d.get("exclusionCuis", []),
            inclusion_clauses=clauses("inclusionClauses"),
            exclusion_clauses=clauses("exclusionClauses"),
            inclusion_mode=d.get("inclusionMode") or "AND",
            exclusion_mode=d.get("exclusionMode") or "OR",
            inclusion_connectors=d.get("inclusionConnectors") or {},
            exclusion_connectors=d.get("exclusionConnectors") or {},
            inclusion_order=d.get("inclusionOrder"),
            exclusion_order=d.get("exclusionOrder"),
            inclusion_groups=d.get("inclusionGroups"),
            exclusion_groups=d.get("exclusionGroups"),
            age_min=d.get("ageMin"),
            age_max=d.get("ageMax"),
            gender=d.get("genderConstraint"),
            races=d.get("raceConstraint"),
            ethnicities=d.get("ethnicityConstraint"),
        )
