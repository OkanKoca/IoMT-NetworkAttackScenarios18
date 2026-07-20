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

Usage:
  python3 freeze_release.py --version v1
  python3 freeze_release.py --version v1 --check   # verify an existing release
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


def git_commit():
    """The commit that produced this release, or a marker when the tree is dirty.

    A dirty tree means the artifacts cannot be reproduced from any commit, which is
    exactly the situation the provenance record exists to expose -- so record it
    rather than silently pinning the last clean commit.
    """
    try:
        rev = subprocess.run(["git", "rev-parse", "HEAD"], cwd=HERE, capture_output=True,
                             text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=HERE,
                               capture_output=True, text=True, check=True).stdout.strip()
        return rev + ("+dirty" if dirty else "")
    except (subprocess.CalledProcessError, FileNotFoundError):
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


def freeze(version, outdir):
    outdir.mkdir(parents=True, exist_ok=True)
    ds_path = outdir / f"dataset_{version}.csv"
    pr_path = outdir / f"probes_{version}.csv"
    model_path = outdir / f"detector_{version}.joblib"

    shutil.copy2(DATASET_SRC, ds_path)
    shutil.copy2(PROBES_SRC, pr_path)

    df = pd.read_csv(ds_path)
    tr = training_rows(df)
    X, y = build_X(tr), tr.label_class

    # Same estimator and seed as every notebook that reports a number for it.
    model = RandomForestClassifier(n_estimators=300, class_weight="balanced", random_state=0)
    model.fit(X, y)
    joblib.dump(model, model_path)

    meta = {
        "version": version,
        "frozen_on": date.today().isoformat(),
        "git_commit": git_commit(),
        "dataset": {
            "file": ds_path.name,
            "sha256": sha256(ds_path),
            "rows": int(len(df)),
            "class_distribution": df.scenario.value_counts().to_dict(),
        },
        "probes": {
            "file": pr_path.name,
            "sha256": sha256(pr_path),
            "rows": int(len(pd.read_csv(pr_path))),
            "note": "evaluated only, never trained on",
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
