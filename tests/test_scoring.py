from matching.models import Study
from matching.scoring import inclusion_evidence_score

from tests.conftest import PD, YOPD, note, patient

STUDY = Study("s", inclusion_cuis=[PD])


def test_none_without_note_evidence():
    assert inclusion_evidence_score(STUDY, patient("p", [PD])) is None


def test_share_of_notes_with_descendants():
    p = patient("p", [YOPD], evidence={YOPD: [note("d1")]}, unaffirmed={PD: [note("d2")]})
    s = inclusion_evidence_score(STUDY, p, "v2")
    assert (s.score, s.supporting_notes, s.total_notes, s.mentions) == (50, 1, 2, 1)


def test_version_decides_which_mentions_count():
    p = patient("p", [PD], evidence={PD: [note("d1"), note("d2", experiencer="family"),
                                          note("d3", context="template")]},
                unaffirmed={PD: [note("d4", negated=True)]})
    assert inclusion_evidence_score(STUDY, p, "v1").score == 100  # every mention
    # v2+: affirmed patient mentions only; template mentions are skipped whenever
    # marked (only v2.1 stores mark them), as in the cohort-builder.
    assert inclusion_evidence_score(STUDY, p, "v2").score == 25
    assert inclusion_evidence_score(STUDY, p, "v2.1").score == 25
