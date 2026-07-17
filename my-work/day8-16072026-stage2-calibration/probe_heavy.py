#!/usr/bin/env python3
"""
probe_heavy.py
--------------------------------------------------------------------------
Locate the CONGESTION KNEE of the ward: how hard the imaging/video gateway has
to push before the medium saturates and the medical path starts losing packets.

Why this exists
---------------
The baseline's delivery ratio is deterministically 1.0, which is what flattens
the detection-vs-intensity curve. Link-error injection cannot fix it: 802.11 ARQ
retransmits a corrupted frame away, turning link noise into delay rather than
loss. The one mechanism that does produce a real delivery noise floor is
CONGESTION -- a queue overflowing when the medium is busy drops packets that ARQ
never gets to retry.

Congestion only starts once the offered load approaches the medium's capacity,
and that capacity is not a number we can safely assume: every flow here is
STA -> AP -> STA, so each byte crosses the air twice, and rate adaptation moves
the ceiling around. So the rate is MEASURED here before the full dataset is
regenerated, rather than guessed and discovered to be wrong 235 runs later.

What it does
------------
Sweeps --heavy (the imaging gateway's offered Mbps) over the NORMAL scenario
only, at --heavyspread=0 so each run's rate is exactly known, and reports what
the ward looks like at each rate.

Reading the result
------------------
The knee is the lowest rate where victim-path delivery leaves 1.0 WITHOUT
collapsing. The target regime for the dataset is:
  * delivery mean ~0.95-1.0 with std > ~0.01   -> a real noise floor
  * NOT delivery << 0.9                        -> saturation would drown the
                                                  attacks we are trying to detect
Once found, the imaging rate is set to that knee and given a per-run spread, so
runs land on both sides of it and delivery comes out spread instead of constant.

Usage:
  python3 probe_heavy.py                  # full probe
  python3 probe_heavy.py --jobs 3         # fewer workers
  python3 probe_heavy.py --dry-run
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
RAW = os.path.join(HERE, "raw")
NS3_DIR = os.path.expanduser("~/ns-3-dev")
SCEN_SRC = os.path.abspath(os.path.join(HERE, "..", "scenarios"))
DATASET_DIR = os.path.abspath(os.path.join(HERE, "..", "day3-4-08072026-09072026-dataset"))
BUILD_LIB = os.path.join(NS3_DIR, "build", "lib")
BUILD_SCRATCH = os.path.join(NS3_DIR, "build", "scratch")

# The feature extractor is shared with the real pipeline on purpose: the probe
# must measure the same numbers the dataset will, or its knee is meaningless.
sys.path.insert(0, DATASET_DIR)
from build_dataset import parse_xml, run_features  # noqa: E402

TARGET = "IoMT-wifi_wip"
SOURCES = ["IoMT-wifi_wip.cc", "iomt-noise.h"]

# Offered load of the imaging gateway, in Mbps, while ON. Spans "quiet ward" to
# "clearly oversubscribed": a first probe at 12 Mbps still delivered its full
# offered average with the victim path at delivery 1.0, so the knee is above it.
HEAVY_GRID = [0, 8, 15, 20, 25, 30, 35, 40]
SEEDS = [1, 2, 3]


def binary_path():
    matches = glob.glob(os.path.join(BUILD_SCRATCH, f"ns3.*-{TARGET}-default"))
    if not matches:
        raise FileNotFoundError(f"No compiled binary for '{TARGET}'. Build first.")
    return matches[0]


def build():
    for src in SOURCES:
        path = os.path.join(SCEN_SRC, src)
        if not os.path.exists(path):
            raise FileNotFoundError(f"Missing source: {path}")
        subprocess.run(["cp", path, os.path.join(NS3_DIR, "scratch", src)],
                       cwd=NS3_DIR, check=True)
    print(f"[build] {TARGET}")
    subprocess.run(["./ns3", "build", TARGET], cwd=NS3_DIR, check=True,
                   stdout=subprocess.DEVNULL)


def run_job(job):
    """Run one (heavy, seed) configuration. Mirrors run_sweep.py's isolation rules:
    raw binary (no ./ns3 wrapper lock), private temp cwd, absolute --output."""
    heavy, seed, force = job
    name = f"probe_h{heavy}_r{seed}"
    out_prefix = os.path.join(RAW, name)
    if not force and os.path.exists(out_prefix + ".xml"):
        return (name, heavy, seed, "skip")
    cmd = [binary_path(), f"--run={seed}", f"--heavy={heavy}", "--heavyspread=0",
           f"--output={out_prefix}"]
    env = dict(os.environ, LD_LIBRARY_PATH=BUILD_LIB)
    with tempfile.TemporaryDirectory(prefix="ns3probe_") as cwd:
        proc = subprocess.run(cmd, cwd=cwd, env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        return (name, heavy, seed, "FAIL", proc.stderr.decode(errors="replace"))
    return (name, heavy, seed, "ok")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", type=int, default=5)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    jobs = [(h, s, args.force) for h in HEAVY_GRID for s in SEEDS]
    print(f"Planned {len(jobs)} runs: heavy={HEAVY_GRID} x seeds={SEEDS}")
    if args.dry_run:
        return

    os.makedirs(RAW, exist_ok=True)
    build()

    fails = []
    with Pool(args.jobs) as pool:
        for i, r in enumerate(pool.imap_unordered(run_job, jobs), 1):
            status = r[3]
            if status == "FAIL":
                fails.append((r[0], r[4]))
            print(f"[{i}/{len(jobs)}] {status:4s} {r[0]}")
    if fails:
        print("\nFailures:")
        for name, err in fails:
            last = err.strip().splitlines()[-1] if err.strip() else "(no stderr)"
            print(f"  {name}: {last}")

    # --- Aggregate -------------------------------------------------------
    rows = []
    for heavy in HEAVY_GRID:
        for seed in SEEDS:
            xml = os.path.join(RAW, f"probe_h{heavy}_r{seed}.xml")
            if not os.path.exists(xml):
                continue
            feats = run_features(parse_xml(xml),
                                 {"scenario": "normal", "intensity": heavy, "run": seed})
            feats["heavy_mbps"] = heavy
            rows.append(feats)
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(HERE, "probe_results.csv"), index=False)

    agg = df.groupby("heavy_mbps").agg(
        n=("delivery_ratio", "size"),
        delivery_mean=("delivery_ratio", "mean"),
        delivery_std=("delivery_ratio", "std"),
        delivery_min=("delivery_ratio", "min"),
        loss_mean=("overall_loss_ratio", "mean"),
        thr_mean=("total_throughput_mbps", "mean"),
        owd_mean=("control_owd_ms", "mean"),
        pdv_mean=("control_pdv_ms", "mean"),
        nflows=("n_flows", lambda s: sorted(s.unique())),
    )
    print("\n=== Congestion probe: victim path vs imaging gateway load ===")
    with pd.option_context("display.width", 200, "display.max_columns", 20,
                           "display.float_format", lambda v: f"{v:.4f}"):
        print(agg.to_string())
    print("\nKnee = lowest heavy_mbps where delivery_mean leaves 1.0 without collapsing.")
    print(f"Wrote {os.path.join(HERE, 'probe_results.csv')}")


if __name__ == "__main__":
    main()
