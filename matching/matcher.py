"""Match patients against a study and sort them into result tiers.

Port of cohort-builder `matchStudyForStudy`, `excludedForStudy`,
`notIncludedForStudy` and the study page's ranking (`src/routes/studies/[id]`).

Tiers (each patient that passes status + demographics lands in exactly one):
  - matched       inclusion satisfied, no exclusion
  - excluded      inclusion satisfied, exclusion satisfied (`reasons`: exclusion CUIs present)
  - not_included  inclusion not satisfied (`missing`: unmet requirements)
Patients failing status or demographic constraints are not returned.
Each tier is ranked by evidence score, then mentions; unscored patients last.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from matching.criteria import (
    exclusion_side,
    inclusion_side,
    missing_inclusion,
    passes_demographics,
    passes_status,
)
from matching.models import Patient, Study
from matching.scoring import EvidenceScore, inclusion_evidence_score
from matching.versions import PipelineVersion, get_version

TIERS = ("matched", "excluded", "not_included")


@dataclass
class PatientMatch:
    patient_id: str
    tier: str
    score: EvidenceScore | None
    reasons: list[str] = field(default_factory=list)  # exclusion CUIs present
    missing: list[list[str]] = field(default_factory=list)  # unmet inclusion requirements


@dataclass
class StudyMatch:
    study_id: str
    version: str
    matched: list[PatientMatch] = field(default_factory=list)
    excluded: list[PatientMatch] = field(default_factory=list)
    not_included: list[PatientMatch] = field(default_factory=list)


def match_patient(study: Study, p: Patient, version: PipelineVersion | str | None = None,
                  *, score: bool = True) -> PatientMatch | None:
    """Classify one patient; None when status or demographics rule them out."""
    if not passes_status(study, p) or not passes_demographics(study, p):
        return None
    v = version if isinstance(version, PipelineVersion) else get_version(version)
    inc, exc = inclusion_side(study), exclusion_side(study)
    s = inclusion_evidence_score(study, p, v) if score else None
    if not inc.satisfied(p.cuis):
        return PatientMatch(p.patient_id, "not_included", s, missing=missing_inclusion(inc, p.cuis))
    if exc.kind != "none" and exc.satisfied(p.cuis):
        return PatientMatch(p.patient_id, "excluded", s, reasons=[c for c in exc.all_cuis if c in p.cuis])
    return PatientMatch(p.patient_id, "matched", s)


def _rank_key(m: PatientMatch):
    return (0, -m.score.score, -m.score.mentions) if m.score else (1, 0, 0)


def match_study(study: Study, patients: Iterable[Patient],
                version: PipelineVersion | str | None = None, *, score: bool = True) -> StudyMatch:
    v = version if isinstance(version, PipelineVersion) else get_version(version)
    out = StudyMatch(study.id, v.id)
    for p in patients:
        m = match_patient(study, p, v, score=score)
        if m:
            getattr(out, m.tier).append(m)
    for tier in TIERS:
        getattr(out, tier).sort(key=_rank_key)  # stable: ties keep input order
    return out
