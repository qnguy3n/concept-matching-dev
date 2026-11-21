import json
from pathlib import Path

from matching.criteria import chain_matches, groups_satisfied
from matching.matcher import match_patient, match_study
from matching.models import Clause, Study

from tests.conftest import DEMENTIA, DYSK, LEVODOPA, MCI, MF, PD, PSP, YOPD, patient

DBS = Study.from_dict(json.loads((Path(__file__).parents[1] / "studies/dbs_eval_v1.json").read_text()))


def tier(study, p, version="v2"):
    m = match_patient(study, p, version, score=False)
    return m.tier if m else None


def test_groups_and_chain_primitives():
    assert groups_satisfied([["a", "b"], ["c"]], {"c"})
    assert not groups_satisfied([["a", "b"], ["c"]], {"a"})
    # (a OR b) AND c
    assert chain_matches(["a", "b", "c"], {"b": "OR", "c": "AND"}, {"b", "c"}, "AND")
    assert not chain_matches(["a", "b", "c"], {"b": "OR", "c": "AND"}, {"a"}, "AND")


def test_dbs_tiers():
    assert tier(DBS, patient("p", [PD, LEVODOPA, DYSK])) == "matched"
    assert tier(DBS, patient("p", [YOPD, LEVODOPA, MF])) == "matched"  # subtype rolls up
    m = match_patient(DBS, patient("p", [PD, LEVODOPA, DYSK, PSP]), score=False)
    assert m.tier == "excluded" and m.reasons == [PSP]
    m = match_patient(DBS, patient("p", [PD]), score=False)
    assert m.tier == "not_included"
    assert m.missing == [[LEVODOPA], [MF, DYSK]]


def test_mci_excluded_as_dementia_only_before_v2_1():
    cuis = [PD, LEVODOPA, DYSK, MCI]
    assert tier(DBS, patient("p", cuis, version="v2"), "v2") == "excluded"
    assert tier(DBS, patient("p", cuis, version="v2.1"), "v2.1") == "matched"


def test_clause_mode_and_legacy():
    clauses = [Clause("PD on levodopa", [PD, LEVODOPA], [PD, LEVODOPA])]
    any_of = Study("s", inclusion_clauses=clauses, inclusion_mode="OR")
    assert tier(any_of, patient("p", [LEVODOPA])) == "matched"
    all_of = Study("s", inclusion_clauses=clauses)
    m = match_patient(all_of, patient("p", [LEVODOPA]), score=False)
    assert m.tier == "not_included" and m.missing == [[PD]]

    legacy = Study("s", inclusion_cuis=[PD], exclusion_cuis=[DEMENTIA, PSP])
    assert tier(legacy, patient("p", [PD])) == "matched"
    assert tier(legacy, patient("p", [PD, PSP])) == "excluded"
    assert tier(Study("s", inclusion_cuis=["C0030554"]), patient("p", [PSP])) == "matched"  # canonicalized


def test_status_and_demographics_filter_out():
    s = Study("s", inclusion_cuis=[PD], age_min=40, gender="female")
    assert tier(s, patient("p", [PD], age=60, gender="female")) == "matched"
    assert tier(s, patient("p", [PD], age=30, gender="female")) is None
    assert tier(s, patient("p", [PD], age=None, gender="female")) is None
    assert tier(s, patient("p", [PD], age=60, gender="male")) is None
    assert tier(Study("s", inclusion_cuis=[PD], patient_status="deceased"), patient("p", [PD])) is None


def test_match_study_ranks_by_score():
    from tests.conftest import note
    weak = patient("weak", [PD, LEVODOPA, DYSK], evidence={PD: [note("d1")]},
                   unaffirmed={DYSK: [note("d2"), note("d3")]})
    strong = patient("strong", [PD, LEVODOPA, DYSK],
                     evidence={PD: [note("d1"), note("d2")], LEVODOPA: [note("d1")], DYSK: [note("d2")]})
    none = patient("none", [PD, LEVODOPA, DYSK])
    res = match_study(DBS, [none, weak, strong])
    assert [m.patient_id for m in res.matched] == ["strong", "weak", "none"]
