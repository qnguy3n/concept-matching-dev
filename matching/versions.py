"""Pipeline versions: which extraction store is read and which mentions count.

Port of the data part of cohort-builder `src/lib/versions.ts` (the browser
persistence of the selected version stays in the UI).
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Mild cognitive impairment: a child of Dementia in the ontology, but not dementia.
MCI = "C0338656"


@dataclass(frozen=True)
class PipelineVersion:
    id: str
    label: str
    extraction: str
    scoring: str
    # Mentions without assertion context are all counted (v1) or only affirmed,
    # patient-experiencer, non-template mentions (v2+).
    assertion_aware: bool = True
    # CUIs whose disorder roll-up stops at themselves.
    no_roll_up: frozenset[str] = field(default_factory=frozenset)


PIPELINE_VERSIONS: dict[str, PipelineVersion] = {
    v.id: v
    for v in [
        PipelineVersion(
            id="v1",
            label="v1 · CUI only",
            extraction="CUI extraction only — every mention counts (no negation, family history, "
            "quantifier or temporality)",
            scoring="Note share over all mentions of the inclusion concepts",
            assertion_aware=False,
        ),
        PipelineVersion(
            id="v2",
            label="v2 · CUI + context",
            extraction="CUI extraction + assertion enrichment — negation (incl. form answers), "
            "family history, quantifier, temporality",
            scoring="Note share over affirmed, patient-experiencer mentions only",
        ),
        PipelineVersion(
            id="v2.1",
            label="v2.1 · context + boilerplate",
            extraction="v2 + form answers after a time qualifier, nested-match removal, "
            "boilerplate-sentence suppression; MCI does not roll up to Dementia",
            scoring="Note share over affirmed, patient-experiencer, non-boilerplate mentions only",
            no_roll_up=frozenset({MCI}),
        ),
    ]
}

DEFAULT_PIPELINE_VERSION = "v2"


def get_version(version_id: str | None = None) -> PipelineVersion:
    vid = version_id or DEFAULT_PIPELINE_VERSION
    try:
        return PIPELINE_VERSIONS[vid]
    except KeyError:
        raise ValueError(f"unknown pipeline version {vid!r}; expected one of {list(PIPELINE_VERSIONS)}")
