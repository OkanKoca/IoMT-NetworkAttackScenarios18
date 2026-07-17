#!/usr/bin/env python3
"""
calibrate_normal.py
--------------------------------------------------------------------------
The gate that must pass BEFORE the full dataset is regenerated.

probe_heavy.py answers "at what imaging load does the medium congest?" with the
rate held exactly fixed. This answers the follow-on question: with that rate now
RANDOMIZED per run (as the shipped scenarios will have it), does the normal
baseline actually look the way the dataset needs it to?

It runs the normal scenario over many seeds and checks four criteria, which
between them say "the baseline is a realistic noise floor, not a constant, and
not so degraded that it drowns the attacks":

  1. n_flows takes >= 3 distinct values  -- the structural artefact is gone. A
     normal run used to ALWAYS have exactly 2 flows while every attack had >= 3,
     which handed the detector a free, intensity-independent "attack?" flag.
  2. delivery std > 0.01                 -- a real delivery noise floor exists.
  3. delivery mean in [0.95, 1.0]        -- and it is a FLOOR, not saturation:
     if normal already lost 20% of its packets, a stealthy attack's loss would be
     invisible for the wrong reason (drowned, not stealthy).
  4. throughput CV > 0.05                -- the Stage-1 gain is not regressed.

Usage:
  python3 calibrate_normal.py --heavy 20 --spread 0.2 --seeds 15
--------------------------------------------------------------------------
"""

import argparse
import glob
import os
import subprocess
import sys
import tempfile
from multiprocessing import Pool

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw_calib")
NS3_DIR = os.path.expanduser("~/ns-3-dev")
SCEN_SRC = os.path.abspath(os.path.join(HERE, "..", "scenarios"))
DATASET_DIR = os.path.abspath(os.path.join(HERE, "..", "day3-4-08072026-09072026-dataset"))
BUILD_LIB = os.path.join(NS3_DIR, "build", "lib")
BUILD_SCRATCH = os.path.join(NS3_DIR, "build", "scratch")

sys.path.insert(0, DATASET_DIR)
from build_dataset import parse_xml, run_features  # noqa: E402

TARGET = "IoMT-wifi_wip"
SOURCES = ["IoMT-wifi_wip.cc", "iomt-noise.h"]


def binary_path():
    matches = glob.glob(os.path.join(BUILD_SCRATCH, f"ns3.*-{TARGET}-default"))
    if not matches:
        raise FileNotFoundError(f"No compiled binary for '{TARGET}'. Build first.")
    return matches[0]


def build():
    for src in SOURCES:
        subprocess.run(["cp", os.path.join(SCEN_SRC, src),
                        os.path.join(NS3_DIR, "scratch", src)], cwd=NS3_DIR, check=True)
    print(f"[build] {TARGET}")
    subprocess.run(["./ns3", "build", TARGET], cwd=NS3_DIR, check=True,
                   stdout=subprocess.DEVNULL)


def run_job(job):
    heavy, spread, seed, force = job
    name = f"calib_h{heavy}_s{spread}_r{seed}"
    out_prefix = os.path.join(RAW, name)
    if not force and os.path.exists(out_prefix + ".xml"):
        return (name, seed, "skip")
    cmd = [binary_path(), f"--run={seed}", f"--heavy={heavy}",
           f"--heavyspread={spread}", f"--output={out_prefix}"]
    env = dict(os.environ, LD_LIBRARY_PATH=BUILD_LIB)
    with tempfile.TemporaryDirectory(prefix="ns3calib_") as cwd:
        proc = subprocess.run(cmd, cwd=cwd, env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        return (name, seed, "FAIL", proc.stderr.decode(errors="replace"))
    return (name, seed, "ok")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--heavy", type=float, default=20.0, help="imaging gateway base Mbps")
    ap.add_argument("--spread", type=float, default=0.2, help="per-run fractional rate spread")
    ap.add_argument("--seeds", type=int, default=15)
    ap.add_argument("--jobs", type=int, default=5)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    os.makedirs(RAW, exist_ok=True)
    build()
    jobs = [(args.heavy, args.spread, s, args.force) for s in range(1, args.seeds + 1)]
    print(f"Calibrating: normal x {args.seeds} seeds, "
          f"imaging {args.heavy} Mbps +/-{args.spread * 100:.0f}%")

    fails = []
    with Pool(args.jobs) as pool:
        for i, r in enumerate(pool.imap_unordered(run_job, jobs), 1):
            if r[2] == "FAIL":
                fails.append((r[0], r[3]))
            print(f"[{i}/{len(jobs)}] {r[2]:4s} {r[0]}")
    if fails:
        for name, err in fails:
            print(f"  FAIL {name}: {err.strip().splitlines()[-1] if err.strip() else ''}")

    rows = []
    for s in range(1, args.seeds + 1):
        xml = os.path.join(RAW, f"calib_h{args.heavy}_s{args.spread}_r{s}.xml")
        if os.path.exists(xml):
            rows.append(run_features(parse_xml(xml),
                                     {"scenario": "normal", "intensity": 0, "run": s}))
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(HERE, "calib_results.csv"), index=False)

    d, t, f = df["delivery_ratio"], df["total_throughput_mbps"], df["n_flows"]
    thr_cv = t.std() / t.mean()
    checks = [
        ("n_flows spreads (>=3 distinct)", len(f.unique()) >= 3, f"values={sorted(f.unique())}"),
        ("delivery std > 0.01", d.std() > 0.01, f"std={d.std():.4f}"),
        ("delivery mean in [0.95, 1.0]", 0.95 <= d.mean() <= 1.0, f"mean={d.mean():.4f}"),
        ("throughput CV > 0.05", thr_cv > 0.05, f"CV={thr_cv:.4f}"),
    ]
    print(f"\n=== Baseline calibration: {len(df)} normal runs "
          f"@ imaging {args.heavy} Mbps +/-{args.spread * 100:.0f}% ===")
    print(f"delivery : mean={d.mean():.4f} std={d.std():.4f} "
          f"min={d.min():.4f} max={d.max():.4f}")
    print(f"           exactly 1.0 in {(d == 1.0).sum()}/{len(d)} runs")
    print(f"throughput: mean={t.mean():.4f} std={t.std():.4f} CV={thr_cv:.4f}")
    print(f"n_flows   : {f.value_counts().sort_index().to_dict()}")
    print(f"owd_ms    : mean={df['control_owd_ms'].mean():.3f} std={df['control_owd_ms'].std():.3f}")
    print(f"pdv_ms    : mean={df['control_pdv_ms'].mean():.3f} std={df['control_pdv_ms'].std():.3f}")
    print("\nAcceptance criteria:")
    for name, ok, detail in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name:32s} {detail}")
    print("\n" + ("ALL PASS -> cleared to wire the remaining scenarios and regenerate."
                  if all(c[1] for c in checks) else
                  "NOT CLEARED -> adjust imaging rate / queue size / subset odds and re-run."))


if __name__ == "__main__":
    main()
