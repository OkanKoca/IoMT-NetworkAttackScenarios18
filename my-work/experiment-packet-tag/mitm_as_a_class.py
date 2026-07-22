#!/usr/bin/env python3
"""Train the timing-MITM as a sixth class, and ask what that class actually learns.

This is the control the tagged-timing work needs and does not have. The tag makes the
hold measurable; whether measuring it changes what a mitm class means can only be read
against a mitm class trained WITHOUT it, which is what this builds. No new simulation:
the mitm probes already exist, 80 runs over eight hold values.

The question comes from the report's section 8.4, which claims a trained mitm class
calls a relay that does nothing at all "mitm" in 80% of runs. That number is reproduced
here, and then the established probe rule is applied to it -- a configuration whose
feature vector cannot be told from the baseline is not a training class -- to see how
much of the confusion it accounts for.

The benign relay (p=0, 40 runs) is never trained on in either arm. It is the control:
it holds nothing, drops nothing, and delays nothing, so every "mitm" it collects is the
model naming a topology rather than a behaviour.

Usage:  python3 mitm_as_a_class.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import StratifiedGroupKFold, cross_val_predict
from sklearn.metrics import classification_report

HERE = Path(__file__).resolve().parent
MYWORK = HERE.parent
sys.path.insert(0, str(MYWORK))
from detector_schema import FEATURES, build_X, check_against_release  # noqa: E402

RELEASE = MYWORK / "day9-20072026-release" / "release"
PROBES = MYWORK / "day3-4-08072026-09072026-dataset" / "out_probes" / "dataset.csv"

RF = dict(n_estimators=300, class_weight="balanced", random_state=0)
CV = StratifiedGroupKFold(5, shuffle=True, random_state=0)
SINGLE_CONFIG = {"normal", "blackhole"}
CLASSES = ["normal", "dos", "ddos", "greyhole", "blackhole", "mitm"]


def group_ids(frame):
    return frame.apply(
        lambda r: f"{r.scenario}_run{r.run}" if r.scenario in SINGLE_CONFIG
                  else f"{r.scenario}_i{r.intensity}", axis=1)


def main():
    check_against_release()
    df = pd.read_csv(RELEASE / "dataset_v1.1.csv")
    probes = pd.read_csv(PROBES)

    train = df[~((df.scenario == "dos") & (df.intensity < 10))].reset_index(drop=True)
    assert len(train) == 255, f"expected the released 255 training rows, got {len(train)}"

    mitm = probes[probes.scenario == "mitm"].copy()
    mitm["label_class"] = "mitm"
    relay = probes[probes.scenario == "relay"]        # holds nothing, drops nothing

    arms = {
        "every hold value (d = 1..200)": mitm,
        "d >= 20 only (probe rule applied)": mitm[mitm.intensity >= 20],
    }

    for name, arm in arms.items():
        full = pd.concat([train, arm], ignore_index=True)
        X, y, g = build_X(full), full.label_class, group_ids(full)
        oof = cross_val_predict(RandomForestClassifier(**RF), X, y, cv=CV, groups=g)
        rep = classification_report(y, oof, labels=CLASSES, output_dict=True,
                                    zero_division=0)

        fitted = RandomForestClassifier(**RF).fit(X, y)
        called = pd.Series(fitted.predict(build_X(relay)))

        print(f"=== {name} === ({len(full)} training runs)")
        print("  " + "  ".join(f"{c} {rep[c]['f1-score']:.3f}" for c in CLASSES))
        print(f"  macro-F1 {np.mean([rep[c]['f1-score'] for c in CLASSES]):.4f}")
        print(f"  the do-nothing relay is called: {dict(called.value_counts())}")
        print(f"  ... 'mitm' in {(called == 'mitm').mean():.2f} of 40 runs")
        print(f"  ... some attack in {(called != 'normal').mean():.2f} of 40 runs\n")


if __name__ == "__main__":
    main()
