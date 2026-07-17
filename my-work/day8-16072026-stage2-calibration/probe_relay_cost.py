#!/usr/bin/env python3
"""
probe_relay_cost.py — how much of the grey-hole's delivery deficit is the ATTACK,
and how much is just the relay being in the path?

The grey-hole victim path goes sensor -> AP -> relay -> AP -> monitor: four trips
through the air, where a normal run's path takes two. Under a congested medium
that extra hop is not free, so a grey-hole run loses packets even when the attack
drops nothing. That loss belongs to the topology, not the attack -- and if it goes
unmeasured it inflates how detectable the weakest grey-hole settings look.

This runs the grey-hole scenario with p=0 (relay forwards everything) to measure
the relay's own cost. It is a DIAGNOSTIC, not training data: the runs are written
here, never into the dataset's raw/ directory, and p=0 is not a class -- a relay
that forwards everything is not an attack.

Read the result as: grey delivery at any p should be compared against the p=0
baseline, not against normal.
"""

import glob
import os
import subprocess
import sys
import tempfile
from multiprocessing import Pool

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw_relay")
NS3_DIR = os.path.expanduser("~/ns-3-dev")
DATASET_DIR = os.path.abspath(os.path.join(HERE, "..", "day3-4-08072026-09072026-dataset"))
BUILD_LIB = os.path.join(NS3_DIR, "build", "lib")
BUILD_SCRATCH = os.path.join(NS3_DIR, "build", "scratch")

sys.path.insert(0, DATASET_DIR)
from build_dataset import parse_xml, run_features  # noqa: E402

SEEDS = range(1, 11)


def run_job(seed):
    name = f"relay_p0_r{seed}"
    out = os.path.join(RAW, name)
    if os.path.exists(out + ".xml"):
        return (name, "skip")
    binary = glob.glob(os.path.join(BUILD_SCRATCH, "ns3.*-IoMT-wifi_grey-default"))[0]
    cmd = [binary, "--p=0", f"--run={seed}", f"--output={out}"]
    env = dict(os.environ, LD_LIBRARY_PATH=BUILD_LIB)
    with tempfile.TemporaryDirectory(prefix="ns3relay_") as cwd:
        proc = subprocess.run(cmd, cwd=cwd, env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    return (name, "ok" if proc.returncode == 0 else "FAIL")


def main():
    os.makedirs(RAW, exist_ok=True)
    with Pool(5) as pool:
        for name, status in pool.imap_unordered(run_job, SEEDS):
            print(f"  {status:4s} {name}")

    rows = [run_features(parse_xml(os.path.join(RAW, f"relay_p0_r{s}.xml")),
                         {"scenario": "greyhole", "intensity": 0.0, "run": s})
            for s in SEEDS if os.path.exists(os.path.join(RAW, f"relay_p0_r{s}.xml"))]
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(HERE, "relay_cost_results.csv"), index=False)

    ds = pd.read_csv(os.path.join(DATASET_DIR, "out", "dataset.csv"))
    nrm = ds[ds.scenario == "normal"].delivery_ratio
    p0 = df.delivery_ratio

    print(f"\n=== Relay's own cost ({len(df)} runs, attack disabled) ===")
    print(f"normal      (1 relay-free path) : {nrm.mean():.4f} +/- {nrm.std():.4f}")
    print(f"grey p=0    (relay forwards all): {p0.mean():.4f} +/- {p0.std():.4f}")
    print(f"-> relay hop costs {nrm.mean() - p0.mean():.4f} delivery, "
          f"{(nrm.mean() - p0.mean()) / nrm.std():.2f} sigma of the normal baseline")

    print("\n=== How much of each grey setting is attack vs relay? ===")
    print(f"{'p':>6s} {'delivery':>9s} {'vs normal':>10s} {'vs p=0 base':>12s}")
    for p in sorted(ds[ds.scenario == "greyhole"].intensity.unique()):
        dv = ds[(ds.scenario == "greyhole") & (ds.intensity == p)].delivery_ratio.mean()
        print(f"{p:6.2f} {dv:9.4f} {(nrm.mean() - dv) / nrm.std():9.2f}s "
              f"{(p0.mean() - dv) / p0.std():11.2f}s")
    print("\n'vs normal' overstates the attack: it charges the relay's hop to the attacker.")
    print("'vs p=0 base' is the attack's own effect.")


if __name__ == "__main__":
    main()
