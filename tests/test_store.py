import json
import sqlite3

from matching.matcher import match_study
from matching.models import Study
from matching.store import load_patients

from tests.conftest import DEMENTIA, MCI, PD, YOPD

SCHEMA = """
CREATE TABLE patient (hospital_id TEXT, patient_id TEXT, mrn_hash TEXT, age INTEGER, gender TEXT,
  race TEXT, ethnicity TEXT, state TEXT, phi_json TEXT, deid_json TEXT, updated_at TEXT);
CREATE TABLE patient_cui (hospital_id TEXT, patient_id TEXT, cui TEXT, label TEXT, source TEXT,
  native_system TEXT, native_code TEXT, evidence_json TEXT, affirmed INTEGER);
"""


def make_store(path):
    db = sqlite3.connect(path)
    db.executescript(SCHEMA)
    db.executemany("INSERT INTO patient (hospital_id, patient_id, age, gender, race, ethnicity) "
                   "VALUES (?,?,?,?,?,?)",
                   [("h1", "a", 70, "male", "white", "Non-Hispanic or Latino"),
                    ("h1", "b", 65, "female", None, None),
                    ("h2", "c", 50, "male", None, None)])
    ev = json.dumps([{"kind": "note", "doc_id": "n1", "negated": False, "experiencer": "patient"}])
    db.executemany("INSERT INTO patient_cui VALUES (?,?,?,?,?,?,?,?,?)",
                   [("h1", "a", YOPD, None, "unstructured", None, None, ev, 1),
                    ("h1", "a", MCI, None, "unstructured", None, None, ev, 1),
                    ("h1", "b", PD, None, "unstructured", None, None, ev, 0),
                    ("h2", "c", PD, None, "structured", "icd10", "G20", None, 1)])
    db.commit()
    db.close()


def test_load_patients(tmp_path):
    path = tmp_path / "store.db"
    make_store(path)
    a, b = load_patients("h1", "v2", path=path)
    assert a.patient_id == "a" and a.race == "White" and a.ethnicity == "Non-Hispanic"
    assert {YOPD, PD, MCI, DEMENTIA} <= a.cuis
    assert a.cui_detail[0].label  # filled from the ontology
    assert a.cui_detail[0].evidence[0].doc_id == "n1"
    assert b.cuis == set() and b.unaffirmed_cui_detail[0].cui == PD  # negated: never matched

    (a21,) = load_patients("h1", "v2.1", path=path, patient_id="a")
    assert DEMENTIA not in a21.cuis


def test_end_to_end(tmp_path):
    path = tmp_path / "store.db"
    make_store(path)
    res = match_study(Study("s", inclusion_cuis=[PD]), load_patients("h1", "v2", path=path))
    assert [m.patient_id for m in res.matched] == ["a"]
    assert [m.patient_id for m in res.not_included] == ["b"]
