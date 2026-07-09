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
N_SEEDS = 10                                     # seeds for dos / greyhole / blackhole
NORMAL_SEEDS = 40                                # more normal runs: the binary detector's
                                                 # negative class is otherwise tiny (~10 vs ~215)
# grey-hole intensity: p = 0.1 .. 0.9. Excludes BOTH endpoints on purpose:
#  * p=0.0 drops nothing -> byte-for-byte identical to the normal baseline (would be the
#    same feature vector under two labels).
#  * p=1.0 drops everything -> byte-for-byte identical to the blackhole class (feature
#    duplicate). The blackhole scenario already covers the full-denial (p=1) endpoint, so
#    the delivery-axis curve is: grey p=0.1..0.9 (greyhole) + blackhole as the p=1 point.
# This keeps every class feature-distinct.
P_GRID = [round(0.1 * i, 1) for i in range(1, 10)]
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
    missing = [src for src, _ in SCENARIOS.values()
               if not os.path.exists(os.path.join(SCEN_SRC, src))]
    if missing:
        raise FileNotFoundError(f"Missing scenario source(s) in {SCEN_SRC}: {missing}")
    for src, _ in SCENARIOS.values():
        dst = os.path.join(NS3_DIR, "scratch", src)
        if os.path.exists(dst):
            print(f"[copy] overwriting scratch/{src}")
        sh(["cp", os.path.join(SCEN_SRC, src), dst])
    for _, target in SCENARIOS.values():
        print(f"[build] {target}")
        sh(["./ns3", "build", target], stdout=subprocess.DEVNULL)


def run_one(target, out_prefix, extra_args, dry, force):
    """Run one configuration; XML lands at out_prefix + '.xml'.

    Idempotent: skips a run whose XML already exists (unless --force), so an
    interrupted sweep resumes without redoing the expensive DDoS runs.
    """
    arg_str = " ".join([target] + extra_args + [f"--output={out_prefix}"])
    if dry:
        print(f'[dry] ./ns3 run "{arg_str}"')
        return
    if not force and os.path.exists(out_prefix + ".xml"):
        return
    sh(["./ns3", "run", "--no-build", arg_str], stdout=subprocess.DEVNULL)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="print commands, do not run")
    ap.add_argument("--force", action="store_true", help="re-run even if the XML exists")
    args = ap.parse_args()

    os.makedirs(RAW, exist_ok=True)
    if not args.dry_run:
        build_all()

    rows = []  # manifest rows

    def do(target, name, extra_args, scenario, intensity, run):
        run_one(target, os.path.join(RAW, name), extra_args, args.dry_run, args.force)
        rows.append((f"raw/{name}.xml", scenario, intensity, run))

    # NORMAL — baseline, seeds only (no intensity knob). More seeds than the
    # attacks so the detector's negative class is not starved.
    for run in range(1, NORMAL_SEEDS + 1):
        do("IoMT-wifi_wip", f"normal_r{run}", [f"--run={run}"], "normal", 0, run)

    # DoS — sweep the flood rate (intensity), seeds each.
    for rate in DOS_RATES:
        for run in range(1, N_SEEDS + 1):
            do("IoMT-wifi_wip_dos", f"dos_rate{rate}_r{run}",
               [f"--rate={rate}", f"--run={run}"], "dos", rate, run)

    # DDoS — sweep the flooder count (intensity), fewer seeds (expensive).
    for na in DDOS_NATTACKERS_GRID:
        for run in range(1, DDOS_SEEDS + 1):
            do("IoMT-wifi_ddos", f"ddos_na{na}_r{run}",
               [f"--nattackers={na}", f"--run={run}"], "ddos", na, run)

    # Blackhole — single point (delivery axis is already swept by grey-hole).
    for run in range(1, N_SEEDS + 1):
        do("IoMT-wifi_black", f"blackhole_r{run}", [f"--run={run}"], "blackhole", BLACKHOLE_INTENSITY, run)

    # Grey-hole — sweep the drop probability p (intensity), seeds each.
    for p in P_GRID:
        for run in range(1, N_SEEDS + 1):
            do("IoMT-wifi_grey", f"greyhole_p{p}_r{run}",
               [f"--p={p}", f"--run={run}"], "greyhole", p, run)
        print(f"[progress] grey p={p} done ({len(rows)} rows so far)")

    # Write the manifest build_dataset.py consumes.
    with open(MANIFEST, "w") as fh:
        fh.write("file,scenario,intensity,run\n")
        for file, scen, inten, run in rows:
            fh.write(f"{file},{scen},{inten},{run}\n")
    print(f"\nWrote {MANIFEST} with {len(rows)} runs.")


if __name__ == "__main__":
    main()
