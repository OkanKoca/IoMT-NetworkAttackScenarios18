"""The detector's input schema, defined once.

Why this file exists: the feature list used to be copy-pasted into every notebook, and
the copies drifted. Notebooks 02-07 were written before victim_startup_lag_ms existed and
carry an 11-name list (12 model inputs); notebooks 08-10 were written after and carry a
12-name list (13 inputs); the released model takes 13. Nothing was wrong with the model --
measured either way the honest CV lands at 0.786 vs 0.787 -- but every reported number
silently belonged to one generation or the other, and a per-class table ended up assembled
from both, with an F1 column that no single run could produce.

So the list lives here and is imported. Drift now requires editing this file, which is a
decision rather than an accident.

The released manifest is treated as the authority, not this file: check_against_release()
compares the two and raises on any mismatch. A schema that agrees with itself proves
nothing -- what matters is that the notebooks describe the model that was actually shipped.

Usage from a notebook (the my-work/ parent has to be importable):

    import sys; sys.path.insert(0, "..")          # or the repo-relative equivalent
    from detector_schema import FEATURES, build_X, check_against_release
    check_against_release()                        # fails loudly on drift
    X = build_X(df)
"""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
RELEASE = HERE / "day9-20072026-release" / "release"

# telemetry_throughput_mbps is deliberately absent: it does not separate the classes
# (ANOVA p=0.79). It was once excluded as "zero variance", which was true of the older
# noiseless dataset and stopped being true once the baseline gained noise (CV 0.15) --
# the exclusion survived, the reason for it did not.
FEATURES = ["n_flows", "total_throughput_mbps", "max_flow_throughput_mbps",
            "max_flow_txpackets", "flow_concentration", "delivery_ratio",
            "overall_loss_ratio", "monitor_owd_ms", "monitor_pdv_ms",
            "mean_owd_ms", "mean_pdv_ms", "victim_startup_lag_ms"]

# What the model actually receives: FEATURES plus the missingness flag build_X derives.
MODEL_INPUTS = FEATURES + ["monitor_missing"]


def build_X(frame, allow_missing=()):
    """The model's input matrix, built the one way it is built anywhere.

    A fully denied victim path has no delay to report, so its timing columns are NaN. The
    missingness is itself signal ("the path was fully denied"), so it is flagged in a
    column and then imputed to 0, rather than the row being dropped.

    allow_missing names columns the caller knows are absent from this frame, which are
    then treated as entirely missing (NaN -> 0). It exists for one case: the upstream
    study's published FlowMonitor data, which predates some of our features. Passing a
    name here is a claim that the feature is UNMEASURABLE in that source, not a way to
    quiet a typo -- so anything not named is still required, and its absence still raises.
    """
    missing = [c for c in FEATURES if c not in frame.columns]
    unexpected = [c for c in missing if c not in allow_missing]
    if unexpected:
        raise KeyError(f"frame is missing required feature(s): {unexpected}. "
                       f"If they are genuinely unmeasurable in this source, name them in "
                       f"allow_missing; otherwise regenerate the frame.")
    X = frame.reindex(columns=FEATURES).copy()
    X["monitor_missing"] = frame["monitor_owd_ms"].isna().astype(int)
    return X.fillna(0.0)


def check_against_release(version="v1.1"):
    """Raise unless this schema matches the released model's, in content and in order.

    Order matters as much as content: scikit-learn matches training columns to prediction
    columns positionally, so a reordered list loads without complaint and predicts
    nonsense. Returns the manifest so callers can report which version they agree with.
    """
    path = RELEASE / f"MANIFEST_{version}.json"
    if not path.exists():
        raise FileNotFoundError(f"no released manifest at {path}; freeze a release first")
    meta = json.loads(path.read_text())
    shipped = meta["model"]["features"]
    if shipped != MODEL_INPUTS:
        raise ValueError(
            f"schema does not match release {version}.\n"
            f"  released: {shipped}\n"
            f"  here    : {MODEL_INPUTS}\n"
            f"Every number computed from this schema would describe a model that was "
            f"never shipped. Reconcile before reporting anything.")
    return meta
