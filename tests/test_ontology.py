from matching.ontology import canonical_cui, disorder_ancestors, roll_up_match_set
from matching.versions import get_version

from tests.conftest import DEMENTIA, MCI, MF, PD, YOPD


def test_subtype_rolls_up_to_parent():
    assert PD in roll_up_match_set([YOPD])


def test_findings_do_not_roll_up():
    # Motor fluctuations is a finding parented under PD: not PD itself.
    assert disorder_ancestors(MF) == []


def test_mci_rolls_up_to_dementia_except_v2_1():
    assert DEMENTIA in roll_up_match_set([MCI], get_version("v2").no_roll_up)
    assert DEMENTIA not in roll_up_match_set([MCI], get_version("v2.1").no_roll_up)


def test_canonical_cui():
    assert canonical_cui("C0030554") == "C0038868"
    assert canonical_cui(PD) == PD
