#!/usr/bin/env python3
"""
freeze_instrumented.py
--------------------------------------------------------------------------
Freeze the INSTRUMENTED variant (v1.2) as a SEPARATE artifact alongside the
canonical passive release (v1.1). It does not touch v1.1.

Why a second release rather than a new canonical one: the passive detector
(v1.1) reads only what a flow monitor sees from outside the path -- no device
cooperates, no packet is touched. The instrumented variant adds three columns
derived from an end-to-end send timestamp (a SeqTsSizeHeader the victim app
stamps and the relay must preserve). That is a different measurement modality:
it assumes cooperative instrumentation, and -- being an application-layer field
a real timing-MITM could strip -- it even assumes the attacker's cooperation.
So it is published as an explicitly-scoped extension, not as a replacement.

What it buys, measured (mitm_sixclass.py, sixclass_results.json): with the stamp
the relay's hold becomes a real axis, MITM promotes to a sixth trained class at
F1 0.929, and the benign-relay-called-MITM error collapses 0.47 -> 0.03. What it
does NOT buy: macro-F1 is unchanged (0.775 tag vs 0.781 tag-free) and a benign
on-path relay's involuntary loss stays indistinguishable from a mild grey-hole.

The provenance gate is the same as freeze_release: the probe set must be one the
model was never fitted on, checked by input-vector equality before anything is
written. Here the MITM sweep is split -- d>=20 ms promoted into training, d<20 ms
kept as an evaluation probe -- so the gate also guards that split.

Usage:
  python3 freeze_instrumented.py                 # cut v1.2 into release/
  python3 freeze_instrumented.py --check         # verify an existing v1.2
--------------------------------------------------------------------------
"""

import argparse
import json
import platform
import sys
from datetime import date
from pathlib import Path

import joblib
import pandas as pd
import sklearn
from sklearn.ensemble import RandomForestClassifier

# Reuse the canonical release's provenance helpers verbatim, so v1.1 and v1.2 are
# hashed and git-stamped by exactly the same code.
from freeze_release import sha256, git_commit, training_rows

HERE = Path(__file__).resolve().parent
MYWORK = HERE.parent
sys.path.insert(0, str(MYWORK))
from detector_schema import FEATURES, build_X  # noqa: E402

# The tagged sweep -- the same scenarios re-run with the send stamp carried across
# the relay, isolated from the frozen passive sweep.
SWEEP = MYWORK / "experiment-packet-tag" / "sweep"
DATASET_SRC = SWEEP / "out" / "dataset.csv"
PROBES_SRC = SWEEP / "out_probes" / "dataset.csv"

# The three e2e-delay summaries the stamp makes measurable. e2e_delivered_n is a
# count, not a feature. These extend, they do not replace, the passive FEATURES.
E2E = ["e2e_delay_median_ms", "e2e_delay_mean_ms", "e2e_delay_p95_ms"]
INSTR_FEATURES = FEATURES + E2E

# The probe rule the sixclass evaluation used: below 20 ms the hold sits inside the
# benign/grey-relay footprint, so those runs stay probes; at and above 20 ms the
# hold is a separable axis and the runs are trainable as the MITM class.
MITM_TRAIN_MS = 20


def build_frames():
    """The instrumented training frame and the probe frame it must not overlap.

    Training = the five passive classes (sub-10 dos still excluded, as in v1.1)
    plus the MITM runs at d>=20 ms, relabeled `mitm`. Probes = everything else in
    the probe file, including the sub-20 MITM runs held out by the probe rule.
    """
    tr = pd.read_csv(DATASET_SRC)
    pr = pd.read_csv(PROBES_SRC)

    mitm = pr[pr.scenario == "mitm"].copy()
    mitm["label_class"] = "mitm"
    mitm_train = mitm[mitm.intensity >= MITM_TRAIN_MS]

    dataset = pd.concat([tr, mitm_train], ignore_index=True)   # frozen as dataset_v1.2
    probes = pr.drop(mitm_train.index).reset_index(drop=True)  # frozen as probes_v1.2
    return dataset, probes


def instr_overlap(probes, train):
    """Probe rows whose instrumented model input equals a training row's.

    Same idea and same guarantee as freeze_release.training_overlap, but over the
    extended feature set the instrumented model actually sees -- comparing on the
    12-feature vector could miss a duplicate that the three e2e columns separate,
    or flag one they do not. Returns the offending (probe, training) pairs.
    """
    key = list(build_X(train, feats=INSTR_FEATURES).columns)
    p = build_X(probes, feats=INSTR_FEATURES).assign(probe_run_id=probes.run_id.values)
    t = build_X(train, feats=INSTR_FEATURES).assign(train_run_id=train.run_id.values,
                                                    train_scenario=train.label_class.values)
    hits = p.merge(t, on=key, how="inner")
    return hits[["probe_run_id", "train_run_id", "train_scenario"]]


def freeze(version, outdir):
    outdir.mkdir(parents=True, exist_ok=True)
    ds_path = outdir / f"dataset_{version}.csv"
    pr_path = outdir / f"probes_{version}.csv"
    model_path = outdir / f"detector_{version}_instrumented.joblib"

    dataset, probes = build_frames()
    dataset.to_csv(ds_path, index=False)
    probes.to_csv(pr_path, index=False)

    tr = training_rows(dataset)                      # drops sub-10 dos, keeps mitm
    X, y = build_X(tr, feats=INSTR_FEATURES), tr.label_class

    # Same gate as v1.1: refuse to cut a release whose probe set was trained on.
    overlap = instr_overlap(probes, tr)
    if len(overlap):
        print(f"REFUSING TO FREEZE: {len(overlap)} probe rows have the same instrumented "
              f"model input as a training row, so they were trained on.\n", file=sys.stderr)
        print(overlap.to_string(index=False), file=sys.stderr)
        print("\nUsually a probe arm sharing a configuration AND a seed with the training "
              "grid, or the MITM d>=20 split leaking. Fix the sweep, regenerate, freeze again.",
              file=sys.stderr)
        sys.exit(1)

    model = RandomForestClassifier(n_estimators=300, class_weight="balanced", random_state=0)
    model.fit(X, y)
    joblib.dump(model, model_path)

    meta = {
        "version": version,
        "variant": "instrumented",
        "canonical_release": "v1.1",
        "frozen_on": date.today().isoformat(),
        "git_commit": git_commit(outdir),
        # The extra assumption a reader must weigh before trusting any number here.
        "measurement_note": "Not a passive flow-monitor model. Adds three columns derived "
                            "from an application-layer send timestamp (SeqTsSizeHeader) that "
                            "the victim stamps and the relay preserves. Assumes cooperative "
                            "end-to-end instrumentation; a real timing-MITM could strip the "
                            "header. v1.1 remains the canonical passive release.",
        "dataset": {
            "file": ds_path.name,
            "sha256": sha256(ds_path),
            "rows": int(len(dataset)),
            "class_distribution": dataset.label_class.value_counts().to_dict(),
        },
        "probes": {
            "file": pr_path.name,
            "sha256": sha256(pr_path),
            "rows": int(len(probes)),
            "note": "evaluated only, never trained on (verified at freeze time)",
            "overlap_check": f"0 of {len(probes)} probe input vectors match any of "
                             f"{len(tr)} training input vectors",
        },
        "model": {
            "file": model_path.name,
            "sha256": sha256(model_path),
            "estimator": "RandomForestClassifier(n_estimators=300, "
                         "class_weight='balanced', random_state=0)",
            "features": INSTR_FEATURES + ["monitor_missing"],
            "classes": sorted(y.unique().tolist()),
            "training_rows": int(len(tr)),
            "mitm_promotion": f"MITM runs at d>={MITM_TRAIN_MS} ms trained as the sixth class; "
                              f"d<{MITM_TRAIN_MS} ms kept as an evaluation probe",
            "excluded_from_training": "dos with intensity < 10 (kept as evaluation probe)",
            # The honest numbers live in the notebook that computes them, not here.
            "honest_eval": "mitm_sixclass.py / sixclass_results.json: grouped-CV macro-F1 "
                           "0.775 (tag) vs 0.781 (tag-free); MITM F1 0.929; typing knee d~30 ms",
        },
        "environment": {
            "python": platform.python_version(),
            "scikit_learn": sklearn.__version__,
            "pandas": pd.__version__,
            "joblib": joblib.__version__,
        },
    }
    (outdir / f"MANIFEST_{version}.json").write_text(json.dumps(meta, indent=2) + "\n")
    return meta


def check(version, outdir):
    meta = json.loads((outdir / f"MANIFEST_{version}.json").read_text())
    ok = True
    for key in ("dataset", "probes", "model"):
        path = outdir / meta[key]["file"]
        if not path.exists():
            print(f"  MISSING  {path.name}"); ok = False; continue
        match = sha256(path) == meta[key]["sha256"]
        ok &= match
        print(f"  {'ok      ' if match else 'CHANGED '} {path.name}")
    if sklearn.__version__ != meta["environment"]["scikit_learn"]:
        print(f"  WARNING  scikit-learn is {sklearn.__version__}, release used "
              f"{meta['environment']['scikit_learn']} -- the model may not load faithfully")

    ds = outdir / meta["dataset"]["file"]
    pr = outdir / meta["probes"]["file"]
    if ds.exists() and pr.exists():
        overlap = instr_overlap(pd.read_csv(pr), training_rows(pd.read_csv(ds)))
        print(f"  {'ok      ' if not len(overlap) else 'FAILED  '} probes never trained on"
              f"{'' if not len(overlap) else f' ({len(overlap)} overlapping rows)'}")
        if len(overlap):
            print(overlap.to_string(index=False))
        ok &= not len(overlap)
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="v1.2")
    ap.add_argument("--outdir", default=str(HERE / "release"))
    ap.add_argument("--check", action="store_true", help="verify an existing release")
    args = ap.parse_args()
    outdir = Path(args.outdir)

    if args.check:
        print(f"Verifying instrumented release {args.version}:")
        sys.exit(0 if check(args.version, outdir) else 1)

    meta = freeze(args.version, outdir)
    print(f"Froze instrumented release {args.version} -> {outdir}")
    print(f"  dataset : {meta['dataset']['rows']} runs  {meta['dataset']['sha256'][:16]}...")
    print(f"  probes  : {meta['probes']['rows']} runs  {meta['probes']['sha256'][:16]}...")
    print(f"  model   : {meta['model']['training_rows']} training rows, "
          f"{len(meta['model']['classes'])} classes ({', '.join(meta['model']['classes'])})")
    print(f"  commit  : {meta['git_commit']}")
    print(f"\n  class distribution: {meta['dataset']['class_distribution']}")


if __name__ == "__main__":
    main()
