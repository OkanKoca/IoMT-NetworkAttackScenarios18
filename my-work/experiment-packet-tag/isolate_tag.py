#!/usr/bin/env python3
"""Does the true end-to-end delay stamp let the detector tell a MALICIOUS relay from a
BENIGN one -- the separation the flow-level features structurally cannot make?

This is the retrain the tagged-timing work was built for (report options 1 + 4). It runs
against a FRESH sweep produced by the instrumented scenarios (my-work/experiment-packet-tag/
sweep), not the frozen v1.1 dataset: every run now carries the source-stamp-to-monitor
delay (e2e_delay_*), which victim_startup_lag_ms only estimated with one noisy sample.

Two questions, two blocks:

  A. DESCRIPTIVE -- the make-or-break. If the stamp works, the benign relay (p=0: holds
     nothing, drops nothing) sits near normal on e2e delay, while the timing-MITM rises
     with its hold. If the stamp does NOT separate them here, no classifier will downstream,
     and the honest thing is to report that.

  B. CLASSIFICATION -- mitm trained as a class, benign relay held out as the control, exactly
     as mitm_as_a_class.py did, but comparing two feature sets on the SAME rows and labels:
       * tag-free : the 12 released FEATURES (reproduces section 8.4's benign-relay alarm)
       * tag      : FEATURES + the e2e delay stamp
     The number that matters is how often the do-nothing relay is still called an attack.
     Tag-free it was ~0.80 called 'mitm' (0.45 with the probe rule); the tag has to move it.

Usage:  python3 isolate_tag.py
        (build the datasets first: run_sweep.py --outroot sweep, then build_dataset.py on
         sweep/manifest.csv -> sweep/out and sweep/manifest_probes.csv -> sweep/out_probes)
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
from detector_schema import FEATURES, build_X  # noqa: E402

SWEEP = HERE / "sweep"
TRAIN_CSV = SWEEP / "out" / "dataset.csv"
PROBE_CSV = SWEEP / "out_probes" / "dataset.csv"

# The stamp features build_dataset now emits. median is the robust centre (the mean is
# dragged by congestion spikes); p95 carries the tail a hold widens.
E2E = ["e2e_delay_median_ms", "e2e_delay_mean_ms", "e2e_delay_p95_ms"]
EXTENDED = FEATURES + E2E

RF = dict(n_estimators=300, class_weight="balanced", random_state=0)
CV = StratifiedGroupKFold(5, shuffle=True, random_state=0)
SINGLE_CONFIG = {"normal", "blackhole"}
CLASSES = ["normal", "dos", "ddos", "greyhole", "blackhole", "mitm"]


def group_ids(frame):
    """Group whole configs together so no config straddles the CV split (docs/05)."""
    return frame.apply(
        lambda r: f"{r.scenario}_run{r.run}" if r.scenario in SINGLE_CONFIG
                  else f"{r.scenario}_i{r.intensity}", axis=1)


def descriptive(train, mitm, relay):
    """Per-class central e2e delay, next to the old estimate, so the stamp's separation is
    visible before any model sees it."""
    print("=== A. DESCRIPTIVE: e2e delay vs the old startup-lag estimate (ms, medians) ===")
    print(f"  {'class':<22}{'n':>5}{'e2e_median':>12}{'e2e_mean':>10}{'startup_lag':>13}")
    rows = [("normal", train[train.scenario == "normal"]),
            ("dos (rate>=10)", train[train.scenario == "dos"]),
            ("ddos", train[train.scenario == "ddos"]),
            ("greyhole (all p)", train[train.scenario == "greyhole"]),
            ("blackhole", train[train.scenario == "blackhole"]),
            ("BENIGN relay (p=0)", relay),
            ("mitm d>=20", mitm[mitm.intensity >= 20]),
            ("mitm d<20", mitm[mitm.intensity < 20])]
    for name, g in rows:
        print(f"  {name:<22}{len(g):>5}{g.e2e_delay_median_ms.median():>12.2f}"
              f"{g.e2e_delay_mean_ms.median():>10.2f}{g.victim_startup_lag_ms.median():>13.2f}")
    print()


def arm(name, full, controls, feats):
    """One feature set: honest grouped-CV report + what the fitted model calls each benign
    relay control. Two controls are passed so the residual can be read: a benign relay at the
    FAR node (STA8) genuinely loses packets to distance, while one at a NEAR node (STA5) does
    not, so comparing the two tells a tag failure apart from the detector reading real loss."""
    X, y, g = build_X(full, feats=feats), full.label_class, group_ids(full)
    oof = cross_val_predict(RandomForestClassifier(**RF), X, y, cv=CV, groups=g)
    rep = classification_report(y, oof, labels=CLASSES, output_dict=True, zero_division=0)

    fitted = RandomForestClassifier(**RF).fit(X, y)

    print(f"  --- {name} ({len(feats)} features) ---")
    print("    " + "  ".join(f"{c} {rep[c]['f1-score']:.3f}" for c in CLASSES))
    print(f"    macro-F1 {np.mean([rep[c]['f1-score'] for c in CLASSES]):.4f}")
    for cname, cdf in controls.items():
        called = pd.Series(fitted.predict(build_X(cdf, feats=feats)))
        print(f"    [{cname}] {dict(called.value_counts())}")
        print(f"        'mitm' {(called == 'mitm').mean():.2f}  "
              f"'greyhole' {(called == 'greyhole').mean():.2f}  "
              f"any-attack {(called != 'normal').mean():.2f}  of {len(cdf)}")
    print()


def block_c(train, mitm, relay8):
    """Option 1, literal: a detector whose negative class IS the benign relay (not normal),
    positive class the malicious relay. Held out as a control (block B), a benign relay has no
    bucket to fall into and MUST be called normal or an attack; trained as the negative class,
    the model can learn what a harmless relay looks like. Position is fixed at STA8 so distance
    is not the separator: benign relay, grey-hole and mitm are all the STA8 relay here.

    Reported per feature set: how often a benign relay is still called malicious (the false
    alarm), and recall split by mechanism -- grey-hole (drops, a delivery signal the tag does
    not touch) vs mitm (holds, exactly what the tag makes visible)."""
    benign = relay8.copy()
    benign["y"] = "benign_relay"
    grey8 = train[train.scenario == "greyhole"].copy()  # malicious drops, @ STA8
    grey8["y"] = "malicious_relay"
    mitm8 = mitm[mitm.intensity >= 20].copy()            # malicious holds, @ STA8
    mitm8["y"] = "malicious_relay"
    full = pd.concat([benign, grey8, mitm8], ignore_index=True)
    # Group whole configs: benign per run, grey per drop-prob, mitm per hold -- so no config
    # straddles the split.
    g = full.apply(lambda r: f"benign_r{r.run}" if r.y == "benign_relay"
                   else f"{r.scenario}_i{r.intensity}", axis=1)
    cv = StratifiedGroupKFold(4, shuffle=True, random_state=0)

    print("=== C. Option 1 literal: malicious-relay vs benign-relay, position fixed @ STA8 ===")
    print(f"  (benign {len(benign)}, malicious {len(grey8)+len(mitm8)} = grey {len(grey8)} + mitm {len(mitm8)})\n")
    for name, feats in [("tag-free", FEATURES), ("tag (+ e2e stamp)", EXTENDED)]:
        X, y = build_X(full, feats=feats), full.y
        oof = pd.Series(cross_val_predict(RandomForestClassifier(**RF), X, y, cv=cv, groups=g),
                        index=full.index)
        fa = (oof[full.y == "benign_relay"] == "malicious_relay").mean()
        rec_grey = (oof[full.scenario == "greyhole"] == "malicious_relay").mean()
        rec_mitm = (oof[(full.scenario == "mitm")] == "malicious_relay").mean()
        print(f"  --- {name} ({len(feats)} features) ---")
        print(f"    benign relay FALSE ALARM (called malicious): {fa:.2f}")
        print(f"    malicious recall:  grey-hole {rec_grey:.2f}   mitm {rec_mitm:.2f}\n")


def main():
    if not TRAIN_CSV.exists() or not PROBE_CSV.exists():
        sys.exit(f"datasets not built yet:\n  {TRAIN_CSV}\n  {PROBE_CSV}\n"
                 "Run build_dataset.py on the sweep manifests first.")
    train_all = pd.read_csv(TRAIN_CSV)
    probes = pd.read_csv(PROBE_CSV)

    # Same stealth-DoS exclusion as the release: sub-10 pkt/s DoS is inside the noise floor,
    # so training it is label noise (docs/14).
    train = train_all[~((train_all.scenario == "dos") & (train_all.intensity < 10))].reset_index(drop=True)

    mitm = probes[probes.scenario == "mitm"].copy()
    mitm["label_class"] = "mitm"
    relay8 = probes[probes.scenario == "relay"]  # p=0 benign relay at STA8 (far node)
    relay5 = probes[(probes.scenario == "relaypos") & (probes.intensity == 5)]  # p=0 at STA5 (near)
    controls = {"benign relay STA8 (far, lossy)": relay8,
                "benign relay STA5 (near, clean)": relay5}

    descriptive(train, mitm, relay8)

    print("=== B. mitm as a class, benign relay held out as control (probe rule: d>=20) ===")
    full = pd.concat([train, mitm[mitm.intensity >= 20]], ignore_index=True)
    print(f"  ({len(full)} training runs; controls: STA8={len(relay8)}, STA5={len(relay5)} runs)\n")
    arm("tag-free (12 released features)", full, controls, FEATURES)
    arm("tag (+ e2e delay stamp)", full, controls, EXTENDED)

    block_c(train, mitm, relay8)


if __name__ == "__main__":
    main()
