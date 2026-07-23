#!/usr/bin/env python3
"""Six-class detector with the timing-MITM promoted to a trained class (tagged pipeline).

Q1(a): now that the e2e stamp makes the hold measurable, does adding MITM as a sixth class
give a clean detector on the EXISTING tagged sweep, with no new simulation? Produces the
per-class table, the confusion matrix, the MITM detection-vs-intensity curve, and a per-fold
MITM F1 spread -- the spread is what decides whether option (b), a light top-up of more MITM
configs, is needed: MITM d>=20 is only 4 config-groups, the same few-group fragility ddos has.

Writes sixclass_results.json for the figures. No new sweep: reads sweep/out + sweep/out_probes.
"""
import sys
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import StratifiedGroupKFold, cross_val_predict
from sklearn.metrics import classification_report, confusion_matrix, f1_score

HERE = Path(__file__).resolve().parent
MYWORK = HERE.parent
sys.path.insert(0, str(MYWORK))
from detector_schema import FEATURES, build_X  # noqa: E402

SWEEP = HERE / "sweep"
E2E = ["e2e_delay_median_ms", "e2e_delay_mean_ms", "e2e_delay_p95_ms"]
EXTENDED = FEATURES + E2E
RF = dict(n_estimators=300, class_weight="balanced", random_state=0)
CV = StratifiedGroupKFold(5, shuffle=True, random_state=0)
SINGLE = {"normal", "blackhole"}
CLASSES = ["normal", "dos", "ddos", "greyhole", "blackhole", "mitm"]


def groups(df):
    return df.apply(lambda r: f"{r.scenario}_run{r.run}" if r.scenario in SINGLE
                    else f"{r.scenario}_i{r.intensity}", axis=1)


def macro_f1(y, pred):
    rep = classification_report(y, pred, labels=CLASSES, output_dict=True, zero_division=0)
    return np.mean([rep[c]["f1-score"] for c in CLASSES]), rep


def main():
    tr = pd.read_csv(SWEEP / "out" / "dataset.csv")
    pr = pd.read_csv(SWEEP / "out_probes" / "dataset.csv")
    train = tr[~((tr.scenario == "dos") & (tr.intensity < 10))].reset_index(drop=True)
    mitm = pr[pr.scenario == "mitm"].copy()
    mitm["label_class"] = "mitm"
    mitm_tr = mitm[mitm.intensity >= 20]          # probe rule: sub-20 is inside the noise
    full = pd.concat([train, mitm_tr], ignore_index=True)
    y, g = full.label_class, groups(full)

    # Headline: tag vs tag-free, so the reader sees what promoting MITM costs/gains.
    oof_tag = pd.Series(cross_val_predict(RandomForestClassifier(**RF),
                        build_X(full, feats=EXTENDED), y, cv=CV, groups=g), index=full.index)
    oof_free = pd.Series(cross_val_predict(RandomForestClassifier(**RF),
                         build_X(full, feats=FEATURES), y, cv=CV, groups=g), index=full.index)
    macro_tag, rep_tag = macro_f1(y, oof_tag)
    macro_free, rep_free = macro_f1(y, oof_free)
    cm = confusion_matrix(y, oof_tag, labels=CLASSES)

    print(f"6-class detector ({len(full)} runs): tag macro-F1 {macro_tag:.4f} | "
          f"tag-free {macro_free:.4f}")
    print(f"  {'class':<10}{'P':>7}{'R':>7}{'F1(tag)':>9}{'F1(free)':>10}{'n':>6}")
    for c in CLASSES:
        n = int((y == c).sum())
        print(f"  {c:<10}{rep_tag[c]['precision']:>7.3f}{rep_tag[c]['recall']:>7.3f}"
              f"{rep_tag[c]['f1-score']:>9.3f}{rep_free[c]['f1-score']:>10.3f}{n:>6}")

    # Per-fold MITM F1 spread -- the (b) decision. 4 config-groups over 5 folds means a fold
    # can hold no MITM test group; the spread across folds says how fragile the estimate is.
    fold_mitm = []
    Xtag = build_X(full, feats=EXTENDED)
    for tri, tei in CV.split(Xtag, y, groups=g):
        m = RandomForestClassifier(**RF).fit(Xtag.iloc[tri], y.iloc[tri])
        yy = y.iloc[tei]
        if (yy == "mitm").any():
            p = pd.Series(m.predict(Xtag.iloc[tei]), index=yy.index)
            fold_mitm.append(f1_score(yy == "mitm", p == "mitm"))
    print(f"\n  MITM per-fold F1: {[round(f,3) for f in fold_mitm]}  "
          f"(folds with MITM present: {len(fold_mitm)}/5)")
    print(f"  spread: mean {np.mean(fold_mitm):.3f}  min {min(fold_mitm):.3f}  "
          f"max {max(fold_mitm):.3f}")

    # MITM detection-vs-intensity: OOF where trained (d>=20), fitted-probe below it.
    fitted = RandomForestClassifier(**RF).fit(Xtag, y)
    curve = []
    for d in sorted(mitm.intensity.unique()):
        if d >= 20:
            mask = (full.label_class == "mitm") & (full.intensity == d)
            pred = oof_tag[mask]
        else:
            pred = pd.Series(fitted.predict(build_X(mitm[mitm.intensity == d], feats=EXTENDED)))
        curve.append(dict(d=float(d), n=int(len(pred)), trained=bool(d >= 20),
                          detect=float((pred != "normal").mean()),
                          typed_mitm=float((pred == "mitm").mean())))
    print("\n  MITM detection-vs-intensity (d ms | detect | typed-mitm | trained):")
    for r in curve:
        print(f"    d={r['d']:>6.0f}  detect {r['detect']:.2f}  mitm {r['typed_mitm']:.2f}"
              f"  {'train' if r['trained'] else 'probe'}")

    out = dict(macro_tag=macro_tag, macro_free=macro_free, n_runs=len(full),
               classes=CLASSES, confusion=cm.tolist(),
               per_class={c: {k: rep_tag[c][k] for k in ("precision", "recall", "f1-score")}
                          for c in CLASSES},
               mitm_fold_f1=fold_mitm, curve=curve)
    (HERE / "sixclass_results.json").write_text(json.dumps(out, indent=2))
    print(f"\n  wrote sixclass_results.json")


if __name__ == "__main__":
    main()
