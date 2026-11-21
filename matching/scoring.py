"""Evidence scoring: rank matched patients by how consistently notes support inclusion.

Port of cohort-builder `src/lib/scoring.ts` (`inclusionEvidenceScore`).
"""

from __future__ import annotations

from dataclasses import dataclass

from matching.criteria import inclusion_groups
from matching.models import Evidence, Patient, Study
from matching.ontology import disorder_ancestors
from matching.versions import PipelineVersion, get_version


@dataclass(frozen=True)
class EvidenceScore:
    # 0–100: mean over the group's inclusion CUIs of the share of notes affirming it
    # (best OR-group wins).
    score: int
    # Notes that affirm at least one inclusion CUI of that group.
    supporting_notes: int
    # Notes with any extracted concept.
    total_notes: int
    # Counted mentions of the group's inclusion CUIs (tie-break).
    mentions: int


def _counts(ev: Evidence, assertion_aware: bool) -> bool:
    if ev.kind != "note" or not ev.doc_id:
        return False
    if not assertion_aware:
        return True
    return not (ev.negated or (ev.experiencer and ev.experiencer != "patient") or ev.context == "template")


def inclusion_evidence_score(study: Study, p: Patient,
                             version: PipelineVersion | str | None = None) -> EvidenceScore | None:
    """Score a patient against a study's inclusion concepts.

    A mention counts for an inclusion CUI when its concept is that CUI or a
    descendant (same subsumption as matching). Which mentions count depends on the
    version: v1 every note mention; v2 only affirmed, patient-experiencer ones;
    v2.1 also skips boilerplate. Returns None without note evidence or inclusion CUIs.
    """
    v = version if isinstance(version, PipelineVersion) else get_version(version)
    groups = inclusion_groups(study)
    if not groups:
        return None

    all_notes = {ev.doc_id for d in p.cui_detail + p.unaffirmed_cui_detail for ev in d.evidence
                 if ev.kind == "note" and ev.doc_id}
    if not all_notes:
        return None

    details = p.cui_detail if v.assertion_aware else p.cui_detail + p.unaffirmed_cui_detail
    notes_for: dict[str, set[str]] = {}
    mentions_for: dict[str, int] = {}
    for target in {c for g in groups for c in g}:
        notes: set[str] = set()
        mentions = 0
        for d in details:
            if d.cui != target and target not in disorder_ancestors(d.cui, v.no_roll_up):
                continue
            for ev in d.evidence:
                if _counts(ev, v.assertion_aware):
                    notes.add(ev.doc_id)  # type: ignore[arg-type]
                    mentions += 1
        notes_for[target] = notes
        mentions_for[target] = mentions

    best: EvidenceScore | None = None
    for group in groups:
        supporting = set().union(*(notes_for[c] for c in group))
        share = sum(len(notes_for[c]) / len(all_notes) for c in group) / len(group)
        cand = EvidenceScore(
            score=round(share * 100),
            supporting_notes=len(supporting),
            total_notes=len(all_notes),
            mentions=sum(mentions_for[c] for c in group),
        )
        if best is None or (cand.score, cand.mentions) > (best.score, best.mentions):
            best = cand
    return best
