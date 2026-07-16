#!/usr/bin/env python3
"""
run_sweep.py
--------------------------------------------------------------------------
Generate the labeled dataset's raw FlowMonitor XMLs by sweeping each
scenario over seeds (and each attack over its intensity knob), then emit a
manifest.csv that build_dataset.py consumes.

Design:
  * copy the scenario sources into ns-3's scratch/ and build ONCE;
  * run the configurations IN PARALLEL across CPU cores. Each run is an
    independent simulation (its own seed + its own absolute --output), so the
    sweep is "embarrassingly parallel". Runs invoke the COMPILED BINARY directly
    (build/scratch/ns3.*-<target>-default with LD_LIBRARY_PATH=build/lib) instead
    of the ./ns3 wrapper -> no wrapper-level lock/reconfigure contention between
    concurrent runs. Each run also executes inside a private temp cwd so the
    scenarios' hardcoded relative side-files (pcap, network-anim*.xml) cannot
    collide across workers. The FlowMonitor XML we keep goes to an absolute
    --output path in raw/, untouched by cwd.
  * the manifest is pure metadata (file, scenario, intensity, run), derived from
    the planned-run list independently of execution order/outcome.

Note on memory: each run holds a FlowMonitor in RAM, but measured peak RSS is only
~65 MB even for the heaviest runs (ddos na8, dos rate1000) -- so ~390 MB for 6
concurrent workers. Memory is no longer the constraint it was on the old 2.5 GB
box; --jobs may be set to the core count. Runtime is dominated by the flood tail
(dos rate1000 ~99 s, ddos na8 ~53 s) while most runs cost ~20 s. (docs/18)

Usage:
  python3 run_sweep.py                 # full sweep, 4 parallel workers
  python3 run_sweep.py --jobs 6        # one worker per core
  python3 run_sweep.py --dry-run       # print the planned runs only (no side effects)
  python3 run_sweep.py --force         # re-run even if an XML already exists
--------------------------------------------------------------------------
"""

import argparse
import glob
import os
import subprocess
import sys
import tempfile
from collections import namedtuple
from multiprocessing import Pool

# --- Paths ----------------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
MANIFEST = os.path.join(HERE, "manifest.csv")
NS3_DIR = os.path.expanduser("~/ns-3-dev")
SCEN_SRC = os.path.abspath(os.path.join(HERE, "..", "scenarios"))
BUILD_LIB = os.path.join(NS3_DIR, "build", "lib")          # shared libs for the raw binary
BUILD_SCRATCH = os.path.join(NS3_DIR, "build", "scratch")  # compiled scenario binaries

# --- Sweep configuration --------------------------------------------------
N_SEEDS = 10                                     # seeds for dos / greyhole / blackhole
NORMAL_SEEDS = 40                                # more normal runs: the binary detector's
                                                 # negative class is otherwise tiny (~10 vs ~215)
# grey-hole intensity: the drop probability p. Excludes BOTH endpoints on purpose:
#  * p=0.0 drops nothing -> byte-for-byte identical to the normal baseline (would be the
#    same feature vector under two labels).
#  * p=1.0 drops everything -> byte-for-byte identical to the blackhole class (feature
#    duplicate). The blackhole scenario already covers the full-denial (p=1) endpoint, so
#    the delivery-axis curve is: grey p=0.02..0.9 (greyhole) + blackhole as the p=1 point.
# This keeps every class feature-distinct.
#
# The 0.02/0.05 points exist because the baseline now HAS a delivery noise floor
# (0.968 +/- 0.034, docs/18). Against it, grey p=0.1 sits ~2.8 sigma out, p=0.05
# ~1.4 sigma, p=0.02 ~0.6 sigma -- so the grey arm's detection collapse happens
# BELOW p=0.1 and the old 0.1..0.9 grid could not see it. These two points are
# where the delivery-axis curve actually bends. (Cheap: low-p runs are the fast
# ones.) No DoS equivalent is needed -- rate10 already sits inside the noise.
P_GRID = [0.02, 0.05] + [round(0.1 * i, 1) for i in range(1, 10)]
DOS_RATES = [10, 20, 50, 100, 200, 500, 1000]    # DoS intensity: flood rate (pkt/s)
DDOS_NATTACKERS_GRID = [1, 2, 3, 5, 8]           # DDoS intensity: number of flooders
DDOS_SEEDS = 5                                   # fewer seeds — DDoS runs are expensive
BLACKHOLE_INTENSITY = 1.0                        # single point (= grey-hole p=1 endpoint)

# Scenario -> (source file, ns-3 target name). The functional attacks (docs/07).
SCENARIOS = {
    "normal": ("IoMT-wifi_wip.cc", "IoMT-wifi_wip"),
    "dos": ("IoMT-wifi_wip_dos.cc", "IoMT-wifi_wip_dos"),
    "greyhole": ("IoMT-wifi_grey.cc", "IoMT-wifi_grey"),
    "ddos": ("IoMT-wifi_ddos.cc", "IoMT-wifi_ddos"),
    "blackhole": ("IoMT-wifi_black.cc", "IoMT-wifi_black"),
}

# Shared headers the scenarios #include. Copied into scratch/ alongside the .cc
# files (a scratch source finds a header in its own directory), so per-run noise
# lives in one place instead of being duplicated across the five scenarios.
SHARED_HEADERS = ["iomt-noise.h"]

# One planned run: what build_dataset.py needs (scenario/intensity/run) plus how to
# launch it (target binary + CLI args). The manifest and the job list both derive from these.
Spec = namedtuple("Spec", "target name extra_args scenario intensity run")


def sh(cmd, **kw):
    """Run a command in NS3_DIR, raising on failure."""
    return subprocess.run(cmd, cwd=NS3_DIR, check=True, **kw)


def build_all():
    """Copy the latest scenario sources into scratch/ and build each once.

    Sources are authored in ../scenarios/ and copied into scratch/; we never edit
    in scratch/ directly, so overwriting it is expected. Two guards make failures
    legible: (1) verify every source exists up front so a typo/missing file raises
    a clear error naming the file, not a cryptic `cp` failure mid-loop; (2) announce
    each overwrite so a stray hand-edit in scratch/ can't vanish unnoticed.
    """
    sources = [src for src, _ in SCENARIOS.values()] + SHARED_HEADERS
    missing = [s for s in sources if not os.path.exists(os.path.join(SCEN_SRC, s))]
    if missing:
        raise FileNotFoundError(f"Missing scenario source(s) in {SCEN_SRC}: {missing}")
    for src in sources:
        dst = os.path.join(NS3_DIR, "scratch", src)
        if os.path.exists(dst):
            print(f"[copy] overwriting scratch/{src}")
        sh(["cp", os.path.join(SCEN_SRC, src), dst])
    for _, target in SCENARIOS.values():
        print(f"[build] {target}")
        sh(["./ns3", "build", target], stdout=subprocess.DEVNULL)


def binary_path(target):
    """Locate the compiled binary for a scratch target (version-agnostic glob)."""
    matches = glob.glob(os.path.join(BUILD_SCRATCH, f"ns3.*-{target}-default"))
    if not matches:
        raise FileNotFoundError(
            f"No compiled binary for '{target}' in {BUILD_SCRATCH}. Build first (build_all).")
    return matches[0]


def run_job(job):
    """Run ONE configuration as an isolated subprocess; return a status tuple.

    Runs at module scope (picklable) so multiprocessing workers can call it. Returns
    (name, "ok"|"skip") on success, or (name, "FAIL", stderr) on a non-zero exit.

    Parallel-safe by construction:
      * invokes the compiled binary directly (no ./ns3 wrapper -> no wrapper-level
        lock/reconfigure contention between concurrent runs);
      * runs inside a private temp cwd, so the scenarios' hardcoded relative side-files
        (pcap, network-anim*.xml) land in isolation and cannot clobber each other;
      * the FlowMonitor XML we keep is written to an absolute --output path in raw/.
    Idempotent: an existing XML is skipped (unless force) so an interrupted sweep resumes.
    """
    target, name, extra_args, force = job
    out_prefix = os.path.join(RAW, name)
    if not force and os.path.exists(out_prefix + ".xml"):
        return (name, "skip")
    env = dict(os.environ, LD_LIBRARY_PATH=BUILD_LIB)
    cmd = [binary_path(target), *extra_args, f"--output={out_prefix}"]
    with tempfile.TemporaryDirectory(prefix="ns3run_") as cwd:
        proc = subprocess.run(cmd, cwd=cwd, env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        return (name, "FAIL", proc.stderr.decode(errors="replace"))
    return (name, "ok")


def build_specs():
    """Enumerate every planned run. This list defines BOTH what to run and the manifest."""
    specs = []
    # NORMAL — baseline, seeds only (no intensity knob). More seeds than the attacks so the
    # detector's negative class is not starved.
    for run in range(1, NORMAL_SEEDS + 1):
        specs.append(Spec("IoMT-wifi_wip", f"normal_r{run}", [f"--run={run}"], "normal", 0, run))
    # DoS — sweep the flood rate (intensity), seeds each.
    for rate in DOS_RATES:
        for run in range(1, N_SEEDS + 1):
            specs.append(Spec("IoMT-wifi_wip_dos", f"dos_rate{rate}_r{run}",
                              [f"--rate={rate}", f"--run={run}"], "dos", rate, run))
    # DDoS — sweep the flooder count (intensity), fewer seeds (expensive).
    for na in DDOS_NATTACKERS_GRID:
        for run in range(1, DDOS_SEEDS + 1):
            specs.append(Spec("IoMT-wifi_ddos", f"ddos_na{na}_r{run}",
                              [f"--nattackers={na}", f"--run={run}"], "ddos", na, run))
    # Blackhole — single point (delivery axis is already swept by grey-hole).
    for run in range(1, N_SEEDS + 1):
        specs.append(Spec("IoMT-wifi_black", f"blackhole_r{run}",
                          [f"--run={run}"], "blackhole", BLACKHOLE_INTENSITY, run))
    # Grey-hole — sweep the drop probability p (intensity), seeds each.
    for p in P_GRID:
        for run in range(1, N_SEEDS + 1):
            specs.append(Spec("IoMT-wifi_grey", f"greyhole_p{p}_r{run}",
                              [f"--p={p}", f"--run={run}"], "greyhole", p, run))
    return specs


def write_manifest(specs):
    """Write the metadata manifest build_dataset.py consumes (independent of run outcome)."""
    with open(MANIFEST, "w") as fh:
        fh.write("file,scenario,intensity,run\n")
        for s in specs:
            fh.write(f"raw/{s.name}.xml,{s.scenario},{s.intensity},{s.run}\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="print the planned runs, no side effects")
    ap.add_argument("--force", action="store_true", help="re-run even if the XML exists")
    ap.add_argument("--jobs", type=int, default=4,
                    help="parallel workers (default 4; use 1 for serial/debug, fewer to cap RAM)")
    args = ap.parse_args()

    specs = build_specs()
    print(f"Planned {len(specs)} runs.")

    if args.dry_run:
        for s in specs:
            print(f"[dry] {s.target} {' '.join(s.extra_args)} --output=raw/{s.name}")
        return

    os.makedirs(RAW, exist_ok=True)
    build_all()                 # serial, once, before any parallel run
    for s in specs:             # fail fast if a binary is missing, before spinning up the pool
        binary_path(s.target)
    write_manifest(specs)

    jobs = [(s.target, s.name, s.extra_args, args.force) for s in specs]
    n_ok = n_skip = 0
    fails = []
    with Pool(args.jobs) as pool:
        for i, result in enumerate(pool.imap_unordered(run_job, jobs), 1):
            name, status = result[0], result[1]
            if status == "ok":
                n_ok += 1
            elif status == "skip":
                n_skip += 1
            else:
                fails.append((name, result[2]))
            print(f"[{i}/{len(jobs)}] {status:4s} {name}")

    print(f"\nDone: {n_ok} ran, {n_skip} skipped, {len(fails)} failed ({args.jobs} workers).")
    print(f"Wrote {MANIFEST} with {len(specs)} runs.")
    if fails:
        print("Failures (last stderr line):")
        for name, detail in fails:
            last = detail.strip().splitlines()[-1] if detail.strip() else "(no stderr)"
            print(f"  {name}: {last}")
        sys.exit(1)


if __name__ == "__main__":
    main()
