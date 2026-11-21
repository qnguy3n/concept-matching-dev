"""Match a hospital's patients from the extraction store against one or more studies.

    PYTHONPATH=. python -m scripts.run_matching --hospital-id ka98 \
        --study studies/dbs_eval_v1.json [--version v2.1] [--db PATH] [--out results.json]

`--study` takes a cohort-builder Study JSON object or a list of them (camelCase,
as stored by the UI). Output: per study, the matched / excluded / not_included
tiers, each ranked by evidence score. De-identified ids only; no PHI is read.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from matching.matcher import TIERS, match_study
from matching.models import Study
from matching.store import load_patients
from matching.versions import DEFAULT_PIPELINE_VERSION, PIPELINE_VERSIONS


def _studies(paths: list[str]) -> list[Study]:
    out = []
    for p in paths:
        data = json.loads(Path(p).read_text())
        out += [Study.from_dict(d) for d in (data if isinstance(data, list) else [data])]
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--hospital-id", required=True)
    ap.add_argument("--study", action="append", required=True, help="Study JSON file (repeatable)")
    ap.add_argument("--version", default=DEFAULT_PIPELINE_VERSION, choices=list(PIPELINE_VERSIONS))
    ap.add_argument("--db", help="Store path (default: per-version env var / sibling concept-extraction)")
    ap.add_argument("--out", help="Write JSON here instead of stdout")
    args = ap.parse_args(argv)

    patients = list(load_patients(args.hospital_id, args.version, path=args.db))
    results = [asdict(match_study(s, patients, args.version)) for s in _studies(args.study)]
    for r in results:
        counts = ", ".join(f"{t}={len(r[t])}" for t in TIERS)
        print(f"{r['study_id']} [{r['version']}] {len(patients)} patients: {counts}", file=sys.stderr)

    text = json.dumps(results, indent=2)
    if args.out:
        Path(args.out).write_text(text)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
