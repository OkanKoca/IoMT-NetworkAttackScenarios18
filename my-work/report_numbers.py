#!/usr/bin/env python3
"""
report_numbers.py
--------------------------------------------------------------------------
Produce every number the write-ups quote, in one pass, from the frozen release.

Why this exists: each figure in the report was copied by hand out of a notebook cell.
That is how the report ended up disagreeing with itself about the false-alarm rate
(0.125 in one section, 0.150 in another), quoting a split cost four times its measured
size, and printing a per-class table whose ddos row has an F1 that no precision and
recall can produce. The model was right every time; the transcription was not.

So the numbers are computed here and written to report_numbers.json, and the report quotes
that file. Two sections cannot disagree when both read the same key.

Three kinds of guard, one per way the project has actually been wrong:

  * INTERNAL CONSISTENCY -- every per-class row must satisfy F1 = 2PR/(P+R). The
    impossible ddos row existed only because nothing ever checked.
  * SCHEMA -- detector_schema.check_against_release() refuses to run against a model
    other than the released one, so these numbers cannot describe something unshipped.
  * COMPARABILITY -- paired_means() refuses to subtract two arms measured on different
    seeds. Widening the relay baseline from ten seeds to forty while grey p=0.02 stayed
    at ten made the attack's contribution come out POSITIVE: a relay dropping 2% of
    packets appearing to deliver more than one dropping nothing. Neither of the other
    two guards would have caught it.

The expensive experiments (notebook 10's twenty-seed ablation, the damage-matched
resampling) are NOT re-derived here. They run against the same frozen data and their
results do not move; paying ten minutes of compute on every invocation would only make
this script something nobody runs. They are quoted from the notebook and marked with
their source, which is what "source" means in each entry below.

Usage:
  python3 report_numbers.py                 # -> report_numbers.json next to this file
  python3 report_numbers.py --print         # also dump a human-readable summary
--------------------------------------------------------------------------
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import (StratifiedGroupKFold, StratifiedKFold,
                                     cross_val_predict, cross_val_score)

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from detector_schema import FEATURES, build_X, check_against_release  # noqa: E402

RELEASE = HERE / "day9-20072026-release" / "release"
PROBES_SRC = HERE / "day3-4-08072026-09072026-dataset" / "out_probes" / "dataset.csv"
VERSION = "v1.1"

CLASS_ORDER = ["normal", "dos", "ddos", "greyhole", "blackhole"]
# Same estimator and folds as every notebook that reports a number for them. Divergence
# here would silently describe a different model, which is the failure this file exists
# to end -- so they are stated once and reused.
RF = dict(n_estimators=300, class_weight="balanced", random_state=0)
GROUPED = StratifiedGroupKFold(5, shuffle=True, random_state=0)
SHUFFLED = StratifiedKFold(5, shuffle=True, random_state=0)
# Single-configuration classes get one group per run; attack classes get one group per
# configuration, so a fold tests intensities the model never saw (notebook 05).
SINGLE_CONFIG = {"normal", "blackhole"}


def group_ids(df):
    return df.apply(lambda r: f"{r.scenario}_run{r.run}" if r.scenario in SINGLE_CONFIG
                              else f"{r.scenario}_i{r.intensity}", axis=1)


def training_rows(df):
    """Sub-10 pkt/s DoS is an evaluation probe, not a training class: at that rate the
    flood is indistinguishable from normal, so training on it puts one vector under two
    labels. Mirrors freeze_release.training_rows."""
    return df[~((df.scenario == "dos") & (df.intensity < 10))].reset_index(drop=True)


def paired_means(arms, column):
    """Mean of `column` for each arm, over the seeds ALL arms share.

    Refuses to proceed when the arms have no seeds in common, and reports how many were
    used, because the caller is about to subtract these from each other. Subtracting
    means taken over different seed sets is not a weaker measurement, it is a wrong one:
    with the relay baseline at forty seeds (two of which collapse entirely) and grey
    p=0.02 at ten (none of which do), the attack's contribution came out positive.
    """
    common = set.intersection(*(set(a.run) for a in arms.values()))
    if not common:
        raise ValueError(f"arms {list(arms)} share no seeds; their difference is meaningless")
    return ({name: float(a[a.run.isin(common)][column].mean()) for name, a in arms.items()},
            sorted(common))


def jsonable(x):
    """NaN as null. json.dumps writes a bare NaN, which is not valid JSON and which
    strict parsers reject -- an unreadable file is a poor place to keep the numbers of
    record. null also says "not measured" where 0.0 would say "measured, and fastest"."""
    return None if pd.isna(x) else round(float(x), 2)


def per_class(y_true, y_pred):
    """Per-class precision/recall/F1, with F1 checked against its own definition."""
    rep = classification_report(y_true, y_pred, labels=CLASS_ORDER,
                                output_dict=True, zero_division=0)
    out = {}
    for cls in CLASS_ORDER:
        p, r, f1 = rep[cls]["precision"], rep[cls]["recall"], rep[cls]["f1-score"]
        expected = 0.0 if (p + r) == 0 else 2 * p * r / (p + r)
        if abs(f1 - expected) > 1e-9:
            raise AssertionError(
                f"{cls}: F1 {f1:.4f} != 2PR/(P+R) = {expected:.4f}. A table that fails "
                f"this was assembled from more than one run.")
        out[cls] = {"precision": round(p, 4), "recall": round(r, 4),
                    "f1": round(f1, 4), "support": int(rep[cls]["support"])}
    out["macro_f1_pooled"] = round(rep["macro avg"]["f1-score"], 4)
    return out


def intensity_curve(tr, pred, fa_floor):
    """Detection and correct-typing rate per attack, per intensity -- the headline curve.

    Detection is read the same way the binary view reads it: anything not 'normal' is an
    alarm. The floor is carried alongside on purpose. An arm is not undetectable when its
    curve reaches zero, it is undetectable when it reaches the rate at which the model
    alarms on normal runs anyway -- below that line the alarms are the model's ordinary
    false alarms, not detections. A curve plotted without its floor flatters the detector.
    """
    d = tr.assign(pred=pred)
    out = {"false_alarm_floor": round(fa_floor, 4)}
    for scenario in ("dos", "ddos", "greyhole", "blackhole"):
        arm = d[d.scenario == scenario]
        out[scenario] = {
            str(i): {"n": int(len(rows)),
                     "detected": round(float((rows.pred != "normal").mean()), 3),
                     "typed_correctly": round(float((rows.pred == scenario).mean()), 3)}
            for i, rows in arm.groupby("intensity")}
    return out


def binary_view(df, pred):
    """Detection read off the multiclass output: anything not 'normal' is an alarm."""
    truth = (df.label_class != "normal").astype(int)
    alarm = pd.Series(pred, index=df.index).ne("normal").astype(int)
    tn, fp, fn, tp = confusion_matrix(truth, alarm, labels=[0, 1]).ravel()
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp),
            "attack_precision": round(precision, 4), "attack_recall": round(recall, 4),
            "attack_f1": round(f1, 4),
            "false_alarm_rate": round(fp / (tn + fp), 4) if tn + fp else None}


def collect():
    meta = check_against_release(VERSION)
    df = pd.read_csv(RELEASE / f"dataset_{VERSION}.csv")
    probes = pd.read_csv(PROBES_SRC)
    tr = training_rows(df)
    X, y, g = build_X(tr), tr.label_class, group_ids(tr)

    rf = RandomForestClassifier(**RF)
    honest = cross_val_score(rf, X, y, cv=GROUPED, groups=g, scoring="f1_macro")
    optimistic = cross_val_score(rf, X, y, cv=SHUFFLED, scoring="f1_macro")
    oof = cross_val_predict(rf, X, y, cv=GROUPED, groups=g)

    # Cost of training the stealth DoS configurations rather than holding them out. The
    # report quotes this as evidence for the hold-out rule, so it is measured, not recalled.
    # Both halves of that evidence are computed: the macro-F1 and the false-alarm rate.
    # The report used to quote the pair as "12.5% -> 35%, 0.809 -> 0.741", none of which
    # any current run produces -- they predate the calibrated baseline of section 3.3.
    Xa, ya, ga = build_X(df), df.label_class, group_ids(df)
    with_stealth = cross_val_score(RandomForestClassifier(**RF), Xa, ya,
                                   cv=GROUPED, groups=ga, scoring="f1_macro")
    oof_with_stealth = cross_val_predict(RandomForestClassifier(**RF), Xa, ya,
                                         cv=GROUPED, groups=ga)
    normals_all = df[df.scenario == "normal"]
    far_with_stealth = float(pd.Series(oof_with_stealth, index=df.index)
                             [normals_all.index].ne("normal").mean())

    # Benign relay: the on-path hop with its attack switched off. R0 is a RATE, so it
    # needs no pairing and uses every seed; the delivery chain below is a DIFFERENCE, so
    # it does not get that freedom.
    fitted = RandomForestClassifier(**RF).fit(X, y)
    relay = probes[probes.scenario == "relay"]
    relay_pred = fitted.predict(build_X(relay))
    normals = tr[tr.scenario == "normal"]
    fa_floor = float(pd.Series(oof, index=tr.index)[normals.index].ne("normal").mean())
    r0 = float((relay_pred != "normal").mean())

    # The bottom of the DoS curve. These runs are held out of training, so they have no
    # out-of-fold prediction; they are read with the model fitted on all 255 training rows
    # -- the detector as shipped. Kept under its own key instead of merged into the dos
    # arm because the two halves would then come from different predictors, and a curve
    # whose points were not all measured the same way should say so in the data rather
    # than only in a sentence next to it.
    stealth = df[(df.scenario == "dos") & (df.intensity < 10)]
    stealth_pred = pd.Series(fitted.predict(build_X(stealth)), index=stealth.index)
    stealth_curve = {
        str(i): {"n": int(len(rows)),
                 "detected": round(float(stealth_pred[rows.index].ne("normal").mean()), 3),
                 "typed_correctly": round(float(stealth_pred[rows.index].eq("dos").mean()), 3)}
        for i, rows in stealth.groupby("intensity")}

    # Why those runs are held out, stated as a measurement rather than an assertion: at
    # these rates the flood moves neither of the two features that carry the volume axis.
    # Paired over the seeds the two arms share, for the reason paired_means exists.
    stealth_gap = {}
    for col in ("delivery_ratio", "total_throughput_mbps"):
        arms, seeds = paired_means({"normal": normals, "stealth_dos": stealth}, col)
        stealth_gap[col] = {**{k: round(v, 4) for k, v in arms.items()},
                            "difference": round(arms["stealth_dos"] - arms["normal"], 4),
                            "normal_std": round(float(normals[col].std()), 4),
                            "difference_in_normal_sigmas": round(
                                (arms["stealth_dos"] - arms["normal"]) / normals[col].std(), 2),
                            "seeds_used": len(seeds)}

    chain_arms = {"normal": normals,
                  "relay_p0": relay,
                  "grey_p002": tr[(tr.scenario == "greyhole") & (tr.intensity == 0.02)]}
    chain, chain_seeds = paired_means(chain_arms, "delivery_ratio")
    relay_cost = chain["relay_p0"] - chain["normal"]
    attack_gain = chain["grey_p002"] - chain["relay_p0"]
    total = chain["grey_p002"] - chain["normal"]

    # Startup lag is quoted in three places with three different pairs of numbers, all
    # of them describing a "0 ms" hold the sweep never ran -- its lowest delay is 1 ms.
    # Both the per-class medians and the MITM sweep are emitted so the report can stop
    # guessing which measurement it meant.
    lag = df.groupby("scenario").victim_startup_lag_ms.median()
    mitm = probes[probes.scenario == "mitm"]
    mitm_lag = mitm.groupby("intensity").victim_startup_lag_ms.median()

    return {
        "generated_from": {
            "release": VERSION,
            "git_commit": meta["git_commit"],
            "dataset_sha256": meta["dataset"]["sha256"],
            "model_sha256": meta["model"]["sha256"],
            "model_inputs": meta["model"]["features"],
            "probes_note": meta["probes"]["overlap_check"],
        },
        "dataset": {
            "rows": int(len(df)),
            "training_rows": int(len(tr)),
            "groups": int(g.nunique()),
            "class_distribution": df.scenario.value_counts().to_dict(),
        },
        "cross_validation": {
            "honest_grouped_macro_f1": round(float(honest.mean()), 4),
            # Spread across folds, NOT a standard error. The report quotes it without
            # saying which, and the two differ by sqrt(n_folds).
            "honest_std_across_folds": round(float(honest.std()), 4),
            "n_folds": int(GROUPED.get_n_splits()),
            "optimistic_shuffled_macro_f1": round(float(optimistic.mean()), 4),
            "optimistic_std_across_folds": round(float(optimistic.std()), 4),
            # What splitting by configuration actually costs. The report attributes a
            # drop from 0.994 to this; 0.994 was measured on the earlier noiseless
            # dataset, which no longer exists, so it cannot be one end of this comparison.
            "cost_of_grouped_split": round(float(optimistic.mean() - honest.mean()), 4),
            "macro_f1_if_stealth_dos_were_trained": round(float(with_stealth.mean()), 4),
            "cost_of_training_stealth_dos": round(
                float(honest.mean() - with_stealth.mean()), 4),
            "false_alarm_rate_if_stealth_dos_were_trained": round(far_with_stealth, 4),
        },
        "per_class_honest": per_class(y, oof),
        "binary_honest": binary_view(tr, oof),
        "detection_vs_intensity": {
            **intensity_curve(tr, oof, fa_floor),
            "dos_stealth_probe": {
                "note": "held out of training, so predicted by the model fitted on all "
                        "255 training rows rather than out-of-fold like the arms above",
                **stealth_curve,
                "separation_from_normal": stealth_gap,
            },
        },
        "relay_baseline": {
            "seeds": int(len(relay)),
            "false_alarm_floor_no_relay_no_attack": round(fa_floor, 4),
            "R0_relay_present_no_attack": round(r0, 4),
            "detection_added_by_relay_alone": round(r0 - fa_floor, 4),
            "headroom_left_for_the_attack": round(1.0 - r0, 4),
            "class_assignment": pd.Series(relay_pred).value_counts().to_dict(),
            "runs_with_total_delivery_collapse": int((relay.delivery_ratio < 0.05).sum()),
            "delivery_mean": round(float(relay.delivery_ratio.mean()), 4),
            "delivery_median": round(float(relay.delivery_ratio.median()), 4),
            "delivery_std": round(float(relay.delivery_ratio.std()), 4),
        },
        "delivery_chain": {
            "seeds_used": len(chain_seeds),
            "note": "means over the seeds all three arms share; they are subtracted",
            **{k: round(v, 4) for k, v in chain.items()},
            "relay_cost": round(relay_cost, 4),
            "attack_gain": round(attack_gain, 4),
            "share_from_attack_pct": round(abs(attack_gain) / abs(total) * 100, 1),
            "share_from_relay_pct": round(100 - abs(attack_gain) / abs(total) * 100, 1),
        },
        "victim_startup_lag_ms_median": {
            # blackhole is null, not zero: nothing arrives, so there is no lag to time.
            # Reporting it as 0.0 would say "fastest", which is how the sentinel that used
            # to live in build_dataset corrupted the timing features once already.
            "by_scenario": {k: jsonable(v) for k, v in lag.items()},
            "mitm_by_added_delay_ms": {str(k): jsonable(v) for k, v in mitm_lag.items()},
            "note": "the sweep's lowest MITM delay is 1 ms; there is no 0 ms hold",
        },
        "quoted_from_notebooks": {
            "volume_matched_typing_accuracy": {
                "value": 0.740, "std": 0.028, "n": 40, "rf_seeds": 20,
                "per_attacker_count": {"1": 0.45, "2": 0.51, "4": 1.00, "8": 1.00},
                "source": "notebook 10",
                "replaces": "the reported 92.5%, whose DoS arm and half of whose ddos "
                            "na=2 arm were training rows (release v1 probe defect)",
                "drop_attributed": {
                    "total": -0.185,
                    "from_memorised_probe_rows": -0.251,
                    "from_new_seeds": +0.070,
                    "from_averaging_over_forests": +0.006,
                    "unexplained_interaction": -0.009,
                    "source": "day10-22072026-disaggregation/disaggregation.json",
                    "reading": "the two changes that came with the fix push the number "
                               "UP; the entire decline is the defect. Control: in the "
                               "old block's ddos na=2 arm the five seeds the forest was "
                               "fitted on scored 1.000 and the five it was not scored "
                               "0.650, same configuration and same forests",
                },
            },
            "dos_vs_ddos_balanced_accuracy": {
                "unmatched": 0.662, "damage_matched": 0.475, "chance": 0.500,
                "small_sample_penalty": 0.070, "effect_of_matching": 0.117,
                "source": "notebook 10",
                "reading": "at equal damage the pair is not separable; what separated "
                           "them was how much damage was done, not how many attackers",
            },
        },
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE / "report_numbers.json"))
    ap.add_argument("--print", dest="show", action="store_true")
    args = ap.parse_args()

    nums = collect()
    Path(args.out).write_text(json.dumps(nums, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {args.out}")

    cv, b = nums["cross_validation"], nums["binary_honest"]
    r = nums["relay_baseline"]
    print(f"  honest {cv['honest_grouped_macro_f1']} +/- {cv['honest_std_across_folds']} "
          f"| optimistic {cv['optimistic_shuffled_macro_f1']} "
          f"| split costs {cv['cost_of_grouped_split']}")
    print(f"  binary TN={b['tn']} FP={b['fp']} FN={b['fn']} TP={b['tp']} "
          f"| attack-F1 {b['attack_f1']} | false alarms {b['false_alarm_rate']}")
    print(f"  relay R0={r['R0_relay_present_no_attack']} over {r['seeds']} seeds "
          f"| floor {r['false_alarm_floor_no_relay_no_attack']} "
          f"| headroom {r['headroom_left_for_the_attack']}")
    if args.show:
        print(json.dumps(nums, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
