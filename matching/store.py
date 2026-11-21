"""Read patients from the SQLite store written by concept-extraction.

Port of the patient-loading part of cohort-builder `src/lib/server/liveDb.ts`
(`listLivePatients` / `listLiveSummaries`). Read-only, de-identified fields only:
PHI (`phi_json`) is never read here.

Store contract (concept-extraction v2.1, `store/schema.sql`): `patient` rows and
`patient_cui` rows with `affirmed` (0 = negated / family-history, never matched
on) and `evidence_json` (per-mention provenance with assertion context).
"""

from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Iterator
from pathlib import Path

from matching.models import Evidence, ExtractedCui, Patient
from matching.ontology import label as ontology_label
from matching.ontology import roll_up_match_set
from matching.versions import PipelineVersion, get_version

# One store per extraction version, same env vars and defaults as the cohort-builder.
_DB_ENV = {"v1": ("COHORT_DB_PATH_V1", "olivo_poc_v1.db"),
           "v2": ("COHORT_DB_PATH", "olivo_poc.db"),
           "v2.1": ("COHORT_DB_PATH_V2_1", "olivo_poc_v2_1.db")}


def db_path(version: str | None = None) -> Path:
    env, name = _DB_ENV[get_version(version).id]
    if os.environ.get(env):
        return Path(os.environ[env])
    data = Path(__file__).resolve().parents[2] / "concept-extraction" / "data"
    return data / name


def map_race(raw: str | None) -> str:
    v = (raw or "").lower()
    return {"white": "White", "asian": "Asian", "black": "Black", "black or african american": "Black",
            "american indian or alaska native": "AI/AN",
            "native hawaiian or other pacific islander": "NH/PI", "": "Unknown"}.get(v, "Other")


def map_ethnicity(raw: str | None) -> str:
    v = (raw or "").lower()
    if v in ("hispanic", "hispanic or latino"):
        return "Hispanic"
    if v.startswith("non-hispanic"):
        return "Non-Hispanic"
    return "Unknown"


def _evidence(text: str | None) -> list[Evidence]:
    if not text:
        return []
    try:
        arr = json.loads(text)
    except json.JSONDecodeError:
        return []
    return [Evidence.from_store(e) for e in arr] if isinstance(arr, list) else []


def _connect(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise FileNotFoundError(f"extraction store not found: {path}")
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def load_patients(hospital_id: str, version: PipelineVersion | str | None = None, *,
                  path: Path | str | None = None, patient_id: str | None = None) -> Iterator[Patient]:
    """Yield the hospital's patients with their match-set and CUI evidence."""
    v = version if isinstance(version, PipelineVersion) else get_version(version)
    conn = _connect(Path(path) if path else db_path(v.id))
    try:
        sql = ("SELECT patient_id, hospital_id, age, gender, race, ethnicity, state "
               "FROM patient WHERE hospital_id = ?")
        params: list = [hospital_id]
        if patient_id:
            sql += " AND patient_id = ?"
            params.append(patient_id)
        rows = conn.execute(sql + " ORDER BY patient_id", params).fetchall()

        cuis_by_patient: dict[str, tuple[list[ExtractedCui], list[ExtractedCui]]] = {}
        for r in conn.execute(
            "SELECT patient_id, cui, label, source, native_system, native_code, evidence_json, affirmed "
            "FROM patient_cui WHERE hospital_id = ? ORDER BY patient_id, source, cui", (hospital_id,)
        ):
            aff, unaff = cuis_by_patient.setdefault(r["patient_id"], ([], []))
            (aff if r["affirmed"] else unaff).append(ExtractedCui(
                cui=r["cui"], label=r["label"] or ontology_label(r["cui"]), source=r["source"],
                native_system=r["native_system"], native_code=r["native_code"],
                evidence=_evidence(r["evidence_json"]),
            ))
    finally:
        conn.close()

    for r in rows:
        aff, unaff = cuis_by_patient.get(r["patient_id"], ([], []))
        yield Patient(
            patient_id=r["patient_id"], hospital_id=r["hospital_id"], age=r["age"],
            gender=r["gender"], race=map_race(r["race"]), ethnicity=map_ethnicity(r["ethnicity"]),
            state=r["state"],
            # Affirmed CUIs rolled UP to disorder ancestors (subsumption-aware matching).
            cuis=roll_up_match_set((d.cui for d in aff), v.no_roll_up),
            cui_detail=aff, unaffirmed_cui_detail=unaff,
        )
