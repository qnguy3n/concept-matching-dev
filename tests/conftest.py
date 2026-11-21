from matching.models import Evidence, ExtractedCui, Patient
from matching.ontology import roll_up_match_set
from matching.versions import get_version

PD, YOPD, LEVODOPA, MF, DYSK = "C0030567", "C0270724", "C0007297", "OLV0000001", "C0013384"
DEMENTIA, MCI, PSP = "C0497327", "C0338656", "C0038868"


def note(doc, **kw):
    return Evidence(kind="note", doc_id=doc, **kw)


def patient(pid, cuis=(), *, version="v2", evidence=None, unaffirmed=None, **kw):
    """`evidence`: {cui: [Evidence]} for affirmed CUIs; `unaffirmed` likewise."""
    evidence = evidence or {}
    aff = [ExtractedCui(c, None, "unstructured", evidence=evidence.get(c, [])) for c in cuis]
    unaff = [ExtractedCui(c, None, "unstructured", evidence=e) for c, e in (unaffirmed or {}).items()]
    return Patient(pid, "h1", cuis=roll_up_match_set(cuis, get_version(version).no_roll_up),
                   cui_detail=aff, unaffirmed_cui_detail=unaff, **kw)
