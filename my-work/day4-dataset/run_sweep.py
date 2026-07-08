#!/usr/bin/env python3
"""
run_sweep.py
--------------------------------------------------------------------------
Generate the labeled dataset's raw FlowMonitor XMLs by sweeping each
scenario over seeds (and grey-hole over its intensity knob p), then emit a
manifest.csv that build_dataset.py consumes.

Design:
  * copy the scenario sources into ns-3's scratch/ and build ONCE, then run
    each configuration with `./ns3 run --no-build` (no per-run rebuild);
  * write each run's XML straight into raw/ via an absolute --output prefix;
  * auto-generate manifest rows (file, scenario, intensity, run) as we go.

Usage:
  python3 run_sweep.py                 # full sweep
  python3 run_sweep.py --dry-run       # print commands only
--------------------------------------------------------------------------
"""

import argparse
import os
import subprocess

# --- Paths ----------------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
MANIFEST = os.path.join(HERE, "manifest.csv")
NS3_DIR = os.path.expanduser("~/ns-3-dev")
SCEN_SRC = os.path.abspath(os.path.join(HERE, "..", "scenarios"))

# --- Sweep configuration --------------------------------------------------
N_SEEDS = 10                                     # replications per configuration
P_GRID = [round(0.1 * i, 1) for i in range(11)]  # grey-hole: 0.0, 0.1, ..., 1.0
DOS_INTENSITY = 100                              # nominal flood rate (pkt/s), fixed for now

# Scenario -> (source file, ns-3 target name). Only the functional ones (docs/07).
SCENARIOS = {
    "normal": ("IoMT-wifi_wip.cc", "IoMT-wifi_wip"),
    "dos": ("IoMT-wifi_wip_dos.cc", "IoMT-wifi_wip_dos"),
    "greyhole": ("IoMT-wifi_grey.cc", "IoMT-wifi_grey"),
}


def sh(cmd, **kw):
    """Run a command in NS3_DIR, raising on failure."""
    return subprocess.run(cmd, cwd=NS3_DIR, check=True, **kw)


def build_all():
    """Copy the latest scenario sources into scratch/ and build each once."""
    for src, _ in SCENARIOS.values():
        sh(["cp", os.path.join(SCEN_SRC, src), os.path.join(NS3_DIR, "scratch", src)])
    for _, target in SCENARIOS.values():
        print(f"[build] {target}")
        sh(["./ns3", "build", target], stdout=subprocess.DEVNULL)


def run_one(target, out_prefix, extra_args, dry):
    """Run one configuration; XML lands at out_prefix + '.xml'."""
    arg_str = " ".join([target] + extra_args + [f"--output={out_prefix}"])
    if dry:
        print(f'[dry] ./ns3 run "{arg_str}"')
        return
    sh(["./ns3", "run", "--no-build", arg_str], stdout=subprocess.DEVNULL)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="print commands, do not run")
    args = ap.parse_args()

    os.makedirs(RAW, exist_ok=True)
    if not args.dry_run:
        build_all()

    rows = []  # manifest rows
    total = N_SEEDS * (2 + len(P_GRID))
    done = 0

    for run in range(1, N_SEEDS + 1):
        # NORMAL (no intensity knob)
        name = f"normal_r{run}"
        run_one("IoMT-wifi_wip", os.path.join(RAW, name), [f"--run={run}"], args.dry_run)
        rows.append((f"raw/{name}.xml", "normal", 0, run))

        # DoS (fixed nominal intensity, seed varies)
        name = f"dos_r{run}"
        run_one("IoMT-wifi_wip_dos", os.path.join(RAW, name), [f"--run={run}"], args.dry_run)
        rows.append((f"raw/{name}.xml", "dos", DOS_INTENSITY, run))

        # Grey-hole across the p grid
        for p in P_GRID:
            name = f"greyhole_p{p}_r{run}"
            run_one("IoMT-wifi_grey", os.path.join(RAW, name),
                    [f"--p={p}", f"--run={run}"], args.dry_run)
            rows.append((f"raw/{name}.xml", "greyhole", p, run))

        done += 2 + len(P_GRID)
        print(f"[progress] seed {run}/{N_SEEDS}  ({done}/{total} runs)")

    # Write the manifest build_dataset.py consumes.
    with open(MANIFEST, "w") as fh:
        fh.write("file,scenario,intensity,run\n")
        for file, scen, inten, run in rows:
            fh.write(f"{file},{scen},{inten},{run}\n")
    print(f"\nWrote {MANIFEST} with {len(rows)} runs.")


if __name__ == "__main__":
    main()
