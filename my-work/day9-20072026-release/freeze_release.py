#!/usr/bin/env python3
"""
freeze_release.py
--------------------------------------------------------------------------
Turn the working state into three inspectable artifacts: a fixed dataset, a
loadable model, and the provenance needed to trust either.

Why this exists: out/dataset.csv is regenerated on every build_dataset.py run and
is git-ignored, so every number in the write-ups depends on a file that can change
without anyone noticing. It already changed three times in one day (the timing
sentinel fix, the new feature, the probe split). Freezing pins one version, records
what produced it, and makes any later change a NEW version rather than a silent
edit of the old one.

Order matters: freeze first, then fit the model on the frozen file. A model fitted
on the working copy could not be tied to a specific dataset afterwards.

Freezing is gated. The manifest asserts that the probe set was evaluated but never
trained on, and that assertion is the one thing a reader cannot verify without
re-running the whole pipeline -- so it is checked here before anything is written,
and a violation aborts the freeze (see training_overlap). v1 shipped with the claim
as a hand-written string and the string was false; v1.1 exists because of it.

Usage:
  python3 freeze_release.py --version v1.1
  python3 freeze_release.py --version v1.1 --check   # verify an existing release
--------------------------------------------------------------------------
"""

import argparse
import hashlib
import json
import platform
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

import joblib
import pandas as pd
import sklearn
from sklearn.ensemble import RandomForestClassifier

HERE = Path(__file__).resolve().parent
DATASET_SRC = HERE.parent / "day3-4-08072026-09072026-dataset" / "out" / "dataset.csv"
PROBES_SRC = HERE.parent / "day3-4-08072026-09072026-dataset" / "out_probes" / "dataset.csv"

# The model's inputs. telemetry_throughput_mbps is deliberately absent: it is constant
# across every run (zero variance), so it carries no information (notebook 02).
FEATURES = ["n_flows", "total_throughput_mbps", "max_flow_throughput_mbps",
            "max_flow_txpackets", "flow_concentration", "delivery_ratio",
            "overall_loss_ratio", "monitor_owd_ms", "monitor_pdv_ms",
            "mean_owd_ms", "mean_pdv_ms", "victim_startup_lag_ms"]


# Sub-10 pkt/s DoS is excluded from TRAINING and kept as an evaluation probe: at that
# rate the flood is indistinguishable from normal in feature space, so training on it
# puts one vector under two labels. Measured cost of training it: false alarms 12.5% ->
# 35%, macro-F1 0.809 -> 0.741. (notebook 05)
def training_rows(df):
    return df[~((df.scenario == "dos") & (df.intensity < 10))].reset_index(drop=True)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git_commit(outdir):
    """The commit that produced this release, or a marker when the tree is dirty.

    A dirty tree means the artifacts cannot be reproduced from any commit, which is
    exactly the situation the provenance record exists to expose -- so record it
    rather than silently pinning the last clean commit.

    outdir is excluded from the check. The claim being recorded is "this commit's code
    and inputs produced these files", and the files themselves are necessarily
    uncommitted while they are being written -- counting them would make the marker
    unconditional, which is the same as not having one.
    """
    def git(*args):
        return subprocess.run(["git", *args], cwd=HERE, capture_output=True,
                              text=True, check=True).stdout.strip()

    try:
        rev = git("rev-parse", "HEAD")
        # The exclusion is anchored with (top) and given a path relative to the repo
        # root. A bare ":!<path>" resolves against the working directory, so an absolute
        # path silently matches nothing -- the exclusion looks applied and is not.
        rel = Path(outdir).resolve().relative_to(Path(git("rev-parse", "--show-toplevel")))
        return rev + ("+dirty" if git("status", "--porcelain", "--",
                                      f":(exclude,top){rel}") else "")
    except (subprocess.CalledProcessError, FileNotFoundError, ValueError):
        return "unknown"


def build_X(frame):
    """Model input. Mirrors notebooks 01/05/08 exactly -- if these diverge, every
    reported number stops describing the released model."""
    X = frame[FEATURES].copy()
    # A fully denied victim path has no delay to report, so timing is NaN there. The
    # missingness is itself signal ("the path was fully denied"), so it is imputed to 0
    # and flagged, rather than dropped.
    X["monitor_missing"] = frame["monitor_owd_ms"].isna().astype(int)
    return X.fillna(0.0)


def training_overlap(probes, train):
    """Probe rows whose model input is identical to a row the model was fitted on.

    The released manifest claims the probe set was evaluated but never trained on. That
    claim used to be a hand-written string, and it was wrong: the volume-matched DoS arm
    re-ran dos rate200 at the training seeds, so ten "probe" rows were byte-identical
    copies of ten training rows, and the out-of-sample check they supported was in-sample.
    Nothing caught it because nothing ever compared the two files.

    Comparison is on build_X output rather than the raw columns, for two reasons: it is
    the vector the model actually sees, and it has no NaNs -- a merge on raw columns would
    silently miss duplicates, since NaN never equals NaN.

    Returns the offending pairs (probe run_id, training run_id) as a DataFrame; empty
    means the claim holds.
    """
    key = list(build_X(train).columns)
    p = build_X(probes).assign(probe_run_id=probes.run_id.values)
    t = build_X(train).assign(train_run_id=train.run_id.values,
                              train_scenario=train.scenario.values)
    hits = p.merge(t, on=key, how="inner")
    return hits[["probe_run_id", "train_run_id", "train_scenario"]]


def freeze(version, outdir):
    outdir.mkdir(parents=True, exist_ok=True)
    ds_path = outdir / f"dataset_{version}.csv"
    pr_path = outdir / f"probes_{version}.csv"
    model_path = outdir / f"detector_{version}.joblib"

    shutil.copy2(DATASET_SRC, ds_path)
    shutil.copy2(PROBES_SRC, pr_path)

    df = pd.read_csv(ds_path)
    pr = pd.read_csv(pr_path)
    tr = training_rows(df)
    X, y = build_X(tr), tr.label_class

    # Refuse to cut a release whose probe set is not what the manifest will say it is.
    # This is a gate, not a warning: the manifest's provenance claim is the one thing a
    # reader cannot check without re-running the pipeline, so it has to be true by
    # construction rather than by intent.
    overlap = training_overlap(pr, tr)
    if len(overlap):
        print(f"REFUSING TO FREEZE: {len(overlap)} probe rows have the same model input as "
              f"a training row, so they were trained on.\n", file=sys.stderr)
        print(overlap.to_string(index=False), file=sys.stderr)
        print("\nFix the sweep (usually a probe arm sharing a configuration AND a seed "
              "with the training grid), regenerate, then freeze again.", file=sys.stderr)
        sys.exit(1)

    # Same estimator and seed as every notebook that reports a number for it.
    model = RandomForestClassifier(n_estimators=300, class_weight="balanced", random_state=0)
    model.fit(X, y)
    joblib.dump(model, model_path)

    meta = {
        "version": version,
        "frozen_on": date.today().isoformat(),
        "git_commit": git_commit(outdir),
        "dataset": {
            "file": ds_path.name,
            "sha256": sha256(ds_path),
            "rows": int(len(df)),
            "class_distribution": df.scenario.value_counts().to_dict(),
        },
        "probes": {
            "file": pr_path.name,
            "sha256": sha256(pr_path),
            "rows": int(len(pr)),
            # Stated as a checked result, not an intention: freeze() exits non-zero if
            # any probe row's model input matches a training row's (see training_overlap).
            "note": "evaluated only, never trained on",
            "overlap_check": f"0 of {len(pr)} probe input vectors match any of "
                             f"{len(tr)} training input vectors (verified at freeze time)",
        },
        "model": {
            "file": model_path.name,
            "sha256": sha256(model_path),
            "estimator": "RandomForestClassifier(n_estimators=300, "
                         "class_weight='balanced', random_state=0)",
            "features": FEATURES + ["monitor_missing"],
            "classes": sorted(y.unique().tolist()),
            "training_rows": int(len(tr)),
            "excluded_from_training": "dos with intensity < 10 (kept as evaluation probe)",
        },
        # joblib files are version-sensitive: loading under a different scikit-learn can
        # fail or, worse, load and behave differently. They also execute code on load, so
        # only open ones you produced.
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
    """Re-hash the released files and compare against the manifest."""
    meta = json.loads((outdir / f"MANIFEST_{version}.json").read_text())
    ok = True
    for key in ("dataset", "probes", "model"):
        path = outdir / meta[key]["file"]
        if not path.exists():
            print(f"  MISSING  {path.name}")
            ok = False
            continue
        actual = sha256(path)
        match = actual == meta[key]["sha256"]
        ok &= match
        print(f"  {'ok      ' if match else 'CHANGED '} {path.name}")
    if sklearn.__version__ != meta["environment"]["scikit_learn"]:
        print(f"  WARNING  scikit-learn is {sklearn.__version__}, release used "
              f"{meta['environment']['scikit_learn']} -- the model may not load faithfully")

    # Re-check the provenance claim, not just the hashes. A hash proves the files are the
    # ones that were frozen; it says nothing about whether the note on them is true.
    ds = outdir / meta["dataset"]["file"]
    pr = outdir / meta["probes"]["file"]
    if ds.exists() and pr.exists():
        overlap = training_overlap(pd.read_csv(pr), training_rows(pd.read_csv(ds)))
        print(f"  {'ok      ' if not len(overlap) else 'FAILED  '} probes never trained on"
              f"{'' if not len(overlap) else f' ({len(overlap)} overlapping rows)'}")
        if len(overlap):
            print(overlap.to_string(index=False))
        ok &= not len(overlap)
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="v1")
    ap.add_argument("--outdir", default=str(HERE / "release"))
    ap.add_argument("--check", action="store_true", help="verify an existing release")
    args = ap.parse_args()
    outdir = Path(args.outdir)

    if args.check:
        print(f"Verifying release {args.version}:")
        sys.exit(0 if check(args.version, outdir) else 1)

    meta = freeze(args.version, outdir)
    print(f"Froze release {args.version} -> {outdir}")
    print(f"  dataset : {meta['dataset']['rows']} runs  {meta['dataset']['sha256'][:16]}...")
    print(f"  probes  : {meta['probes']['rows']} runs  {meta['probes']['sha256'][:16]}...")
    print(f"  model   : {meta['model']['training_rows']} training rows, "
          f"{len(meta['model']['classes'])} classes")
    print(f"  commit  : {meta['git_commit']}")
    print(f"\n  class distribution: {meta['dataset']['class_distribution']}")


if __name__ == "__main__":
    main()
