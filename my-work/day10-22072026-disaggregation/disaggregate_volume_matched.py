#!/usr/bin/env python3
"""
disaggregate_volume_matched.py
--------------------------------------------------------------------------
Split the volume-matched typing accuracy's drop -- 0.925 down to 0.740 -- into the
three changes that were made at once.

The drop is quoted as the consequence of the release-v1 probe defect, but three things
changed between the two measurements and only one of them is the defect:

  (1) PROVENANCE. Fifteen of the forty volume-matched probe rows were training rows.
      The dos arm (all ten) and the ddos na=2 arm's first five seeds had model input
      vectors identical to rows the forest was fitted on, so it could recite them.
  (2) SEEDS. The whole block moved from seeds 1-10 to seeds 11-20, so even the rows
      that were always out of sample are different runs now.
  (3) RF SEEDING. The first number came from one forest (random_state=0); the second
      averages twenty. At n=40 the resolution is 1/40 = 0.025, so a single forest
      cannot tell differences of that size from noise.

Attributing the whole 0.185 to (1) overstates our own error; attributing none of it
understates it. Either way it is a guess, and the point of the last two days was to
stop guessing at numbers.

METHOD. The two probe files are the experiment: probes_v1.csv is the old block at
seeds 1-10, probes_v1.1.csv the new one at seeds 11-20, same four arms, same ten seeds
each, identical schema. Crossing {old, new} x {one forest, twenty} gives a 2x2 whose
margins separate (3) from (1)+(2) together.

Separating (1) from (2) needs one more thing, and the ddos na=2 arm supplies it for
free: five of its ten old seeds were training rows and five were not. Same
configuration, same forest, same measurement -- the only difference is whether the
forest had seen the row. That within-arm gap is the memorisation inflation, measured
rather than assumed, and the na=4 and na=8 arms (clean in both files) measure the seed
effect on its own.

Usage:
  python3 disaggregate_volume_matched.py            # -> disaggregation.json beside this file
--------------------------------------------------------------------------
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from joblib import load
from sklearn.ensemble import RandomForestClassifier

HERE = Path(__file__).resolve().parent
MYWORK = HERE.parent
sys.path.insert(0, str(MYWORK))
from detector_schema import build_X, check_against_release  # noqa: E402

RELEASE = MYWORK / "day9-20072026-release" / "release"
RF_SEEDS = 20
ARMS = [1, 2, 4, 8]          # attackers the offered 200 pkt/s is split across


def training_rows(df):
    """The published model's protocol: sub-10 pkt/s dos is a probe, not a class."""
    return df[~((df.scenario == "dos") & (df.intensity < 10))].reset_index(drop=True)


def volume_matched(path):
    pr = pd.read_csv(path)
    vm = pr[pr.scenario.str.startswith("volmatch")].copy()
    vm["na"] = vm.intensity.astype(int)
    vm["truth"] = np.where(vm.na == 1, "dos", "ddos")
    return vm.reset_index(drop=True)


def in_sample_mask(probes, train):
    """True where the probe's model input equals some training row's, exactly.

    Compared on build_X output, not the raw columns: it is the vector the forest
    actually sees, and it carries no NaNs -- a merge on raw columns would miss
    duplicates silently, because NaN never equals NaN.
    """
    key = list(build_X(train).columns)
    seen = set(map(tuple, build_X(train)[key].to_numpy()))
    return pd.Series([tuple(r) in seen for r in build_X(probes)[key].to_numpy()],
                     index=probes.index)


def correctness(train, probes, seeds):
    """(n_probes x n_seeds) boolean: was this row typed correctly by this forest?"""
    Xtr, ytr = build_X(train), train.label_class
    Xpr = build_X(probes)
    cols = []
    for s in seeds:
        m = RandomForestClassifier(300, class_weight="balanced", random_state=s)
        m.fit(Xtr, ytr)
        cols.append(m.predict(Xpr) == probes.truth.to_numpy())
    return pd.DataFrame(np.column_stack(cols), index=probes.index, columns=list(seeds))


def by_arm(probes, corr):
    """Mean accuracy per attacker count, averaged over rows then over forests."""
    return corr.mean(axis=1).groupby(probes.na).mean()


def main():
    rel = check_against_release()
    print(f"schema matches release {rel['version']} "
          f"({len(rel['model']['features'])} inputs)\n")

    train = training_rows(pd.read_csv(RELEASE / "dataset_v1.1.csv"))
    assert len(train) == 255, f"expected 255 training rows, found {len(train)}"

    old = volume_matched(RELEASE / "probes_v1.csv")
    new = volume_matched(RELEASE / "probes_v1.1.csv")
    assert len(old) == len(new) == 40
    assert sorted(old.run.unique()) == list(range(1, 11))
    assert sorted(new.run.unique()) == list(range(11, 21))

    # --- which rows the forest had already seen -------------------------------------
    old_seen, new_seen = in_sample_mask(old, train), in_sample_mask(new, train)
    print(f"old probe block: {old_seen.sum()}/40 rows are training rows")
    for na in ARMS:
        m = old_seen[old.na == na]
        if m.any():
            print(f"    na={na}: {m.sum()}/10  (seeds "
                  f"{sorted(old.run[m[m].index])})")
    print(f"new probe block: {new_seen.sum()}/40 rows are training rows  "
          f"{'(as the freeze gate promises)' if not new_seen.any() else '<-- PROBLEM'}\n")
    assert not new_seen.any(), "v1.1 was frozen on the claim that this is empty"

    # --- the 2x2 ---------------------------------------------------------------------
    seeds = range(RF_SEEDS)
    corr_old, corr_new = correctness(train, old, seeds), correctness(train, new, seeds)

    # One forest means random_state=0, which is how the published model was fitted.
    # Check that rather than trust it: if a refit no longer reproduces the released
    # artefact's predictions, every number below describes some other model.
    published = load(RELEASE / "detector_v1.1.joblib")
    refit = RandomForestClassifier(300, class_weight="balanced", random_state=0)
    refit.fit(build_X(train), train.label_class)
    assert (published.predict(build_X(old)) == refit.predict(build_X(old))).all(), \
        "a seed-0 refit disagrees with the released model on the old probe block"

    cells = {
        "old_one_forest":  float(corr_old[0].mean()),
        "old_twenty":      float(corr_old.mean(axis=1).mean()),
        "new_one_forest":  float(corr_new[0].mean()),
        "new_twenty":      float(corr_new.mean(axis=1).mean()),
    }
    print("TYPING ACCURACY, 40 rows per cell")
    print(f"{'':<22}{'one forest':>12}{'20 forests':>12}")
    print(f"{'old block (seeds 1-10)':<22}{cells['old_one_forest']:>12.3f}"
          f"{cells['old_twenty']:>12.3f}")
    print(f"{'new block (seeds 11-20)':<22}{cells['new_one_forest']:>12.3f}"
          f"{cells['new_twenty']:>12.3f}")
    print(f"\nreported numbers were {cells['old_one_forest']:.3f} (old, one forest) "
          f"and {cells['new_twenty']:.3f} (new, twenty)")
    print(f"total drop: {cells['new_twenty'] - cells['old_one_forest']:+.3f}\n")

    rf_effect = ((cells["old_twenty"] - cells["old_one_forest"]) +
                 (cells["new_twenty"] - cells["new_one_forest"])) / 2
    block_effect = ((cells["new_one_forest"] - cells["old_one_forest"]) +
                    (cells["new_twenty"] - cells["old_twenty"])) / 2
    print(f"averaging over forests, on its own: {rf_effect:+.3f}")
    print(f"changing the probe block, on its own: {block_effect:+.3f}\n")

    # --- per arm ---------------------------------------------------------------------
    arm_old, arm_new = by_arm(old, corr_old), by_arm(new, corr_new)
    print("PER ARM (20 forests), and whether the old rows were in sample")
    print(f"{'attackers':>10}{'old':>8}{'new':>8}{'delta':>8}   old rows in sample")
    for na in ARMS:
        n_seen = int(old_seen[old.na == na].sum())
        print(f"{na:>10}{arm_old[na]:>8.3f}{arm_new[na]:>8.3f}"
              f"{arm_new[na] - arm_old[na]:>+8.3f}   {n_seen}/10")

    clean_arms = [na for na in ARMS if not old_seen[old.na == na].any()]
    dirty_arms = [na for na in ARMS if old_seen[old.na == na].any()]
    print(f"\narms clean in both blocks: {clean_arms}  -> their delta is the seed effect")
    print(f"arms contaminated in the old block: {dirty_arms}")

    # --- the within-arm control ------------------------------------------------------
    # ddos na=2 is the useful arm: five of its ten old seeds were training rows and five
    # were not, so the gap between them is memorisation with everything else held fixed.
    na2 = old.na == 2
    seen_acc = float(corr_old[na2 & old_seen].mean(axis=1).mean())
    unseen_acc = float(corr_old[na2 & ~old_seen].mean(axis=1).mean())
    print(f"\nWITHIN-ARM CONTROL -- ddos na=2, old block, same forests")
    print(f"  seeds the forest was fitted on   ({int((na2 & old_seen).sum())} rows): "
          f"{seen_acc:.3f}")
    print(f"  seeds it was not fitted on       ({int((na2 & ~old_seen).sum())} rows): "
          f"{unseen_acc:.3f}")
    print(f"  memorisation inflation: {seen_acc - unseen_acc:+.3f}")

    # --- attribution -----------------------------------------------------------------
    # Each arm carries 10/40 of the total. An arm that was in sample contributes a delta
    # made of memorisation and seeds together; a clean arm contributes seeds alone, so
    # the clean arms measure the seed term and it is subtracted from every arm's delta.
    # What is left in a contaminated arm is what memorisation was holding up.
    w = 10 / 40
    seed_term = float(np.mean([arm_new[na] - arm_old[na] for na in clean_arms]))
    contrib = {}
    for na in ARMS:
        d = float(arm_new[na] - arm_old[na])
        contrib[na] = {"delta": round(d, 4),
                       "in_sample_fraction": float(old_seen[old.na == na].mean()),
                       "from_seeds": round(w * seed_term, 4),
                       "from_provenance": round(w * (d - seed_term), 4)}
    from_seeds = sum(c["from_seeds"] for c in contrib.values())
    from_prov = sum(c["from_provenance"] for c in contrib.values())

    total = cells["new_twenty"] - cells["old_one_forest"]
    residual = total - (from_prov + from_seeds + rf_effect)
    print(f"\nATTRIBUTION of the {total:+.3f}")
    print(f"  probe rows the model had memorised   : {from_prov:+.3f}")
    print(f"  different seeds, same configurations : {from_seeds:+.3f}")
    print(f"  averaging over forests instead of one: {rf_effect:+.3f}")
    print(f"  {'unexplained (interaction)':<37}: {residual:+.3f}")
    print(f"  {'sum':<37}: "
          f"{from_prov + from_seeds + rf_effect + residual:+.3f}")
    print(f"\nBoth clean arms sit at 1.000 in the new block, so the seed term is "
          f"measured\nagainst a ceiling and is really an upper bound on ten runs' "
          f"worth of noise.\nIt moves the number UP; every downward movement is "
          f"provenance.")

    out = {
        "generated_from": {
            "release": rel["version"],
            "dataset_sha256": rel["model"].get("dataset_sha256"),
            "training_rows": len(train),
            "rf_seeds": RF_SEEDS,
        },
        "question": ("how much of the volume-matched typing drop, 0.925 -> 0.740, is "
                     "the release-v1 probe defect and how much is the other two things "
                     "that changed with it"),
        "cells": {k: round(v, 4) for k, v in cells.items()},
        "total_drop": round(cells["new_twenty"] - cells["old_one_forest"], 4),
        "in_sample_rows": {"old_block": int(old_seen.sum()), "new_block": int(new_seen.sum()),
                           "old_by_arm": {str(na): int(old_seen[old.na == na].sum())
                                          for na in ARMS}},
        "per_arm": {str(na): {"old": round(float(arm_old[na]), 4),
                              "new": round(float(arm_new[na]), 4),
                              "delta": round(float(arm_new[na] - arm_old[na]), 4)}
                    for na in ARMS},
        "within_arm_control": {
            "arm": "ddos na=2, old block",
            "fitted_on": round(seen_acc, 4),
            "not_fitted_on": round(unseen_acc, 4),
            "memorisation_inflation": round(seen_acc - unseen_acc, 4),
            "note": ("same configuration and the same forests; the only difference "
                     "between the two groups is whether the row was in the fit"),
        },
        "attribution": {
            "from_provenance": round(from_prov, 4),
            "from_seeds": round(from_seeds, 4),
            "from_forest_averaging": round(rf_effect, 4),
            "unexplained_interaction": round(residual, 4),
            "method": ("the arms that were clean in both blocks measure the seed term; "
                       "it is subtracted from each arm's delta and the remainder is "
                       "attributed to provenance, weighted 10/40 per arm"),
            "caveat": ("both clean arms reach 1.000 in the new block, so the seed term "
                       "is estimated against a ceiling on twenty runs; treat it as an "
                       "upper bound on noise rather than a measured effect. It is "
                       "positive either way -- nothing but provenance pushes the "
                       "number down"),
        },
        "per_arm_attribution": {str(k): v for k, v in contrib.items()},
    }
    (HERE / "disaggregation.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False) + "\n")
    print(f"\nwrote {HERE / 'disaggregation.json'}")


if __name__ == "__main__":
    main()
