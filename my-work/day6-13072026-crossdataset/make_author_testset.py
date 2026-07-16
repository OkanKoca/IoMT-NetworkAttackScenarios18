#!/usr/bin/env python3
"""
make_author_testset.py
--------------------------------------------------------------------------
Build a *cross-dataset test set* from the upstream study's own published
FlowMonitor XML outputs (git remote `upstream` = ramamr33/IoMT-...,
Zenodo 10.5281/zenodo.16747386).

Purpose: evaluate a detector that was *trained on our regenerated simulations*
against the original study's independent data. This is a generalization /
domain-shift probe, NOT additional training data — the author's outputs are
never mixed into training.

Design choice — reuse, don't reimplement:
  Feature vectors are produced by the SAME parser used for our own dataset
  (../day3-4.../build_dataset.py), invoked as a subprocess. Writing a second
  parser here would let the feature *definitions* drift, which would make any
  cross-dataset comparison meaningless. The only thing this script adds is
  (a) pulling the author XMLs out of the `upstream` git ref onto disk, and
  (b) a manifest that labels each file by its source folder.

Topology note (why some features are structurally different, not a bug):
  The author's network is a different topology from ours (9 flows/run vs 2-6;
  per-STA echo servers on ports 8070-8130 + MQTT 8883 + echo port 9). Our
  role ports (relay_in 7070, telemetry 9090) do not exist there, so the parser's
  PORT_ROLE fallback yields telemetry_throughput = 0 and a pump-only
  delivery_ratio. These gaps are intentional and documented, not patched.

Usage:
  python3 make_author_testset.py            # extract + manifest + parse
  python3 make_author_testset.py --no-extract   # reuse XMLs already on disk

Outputs (all git-ignored, regenerate from this script):
  raw_author/author_<class>_seed<n>.xml   extracted author FlowMonitor XMLs
  manifest_author.csv                     file,scenario,intensity,run
  out/flows.csv, out/dataset.csv          parsed, same schema as our dataset
--------------------------------------------------------------------------
"""

import argparse
import csv
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
BUILDER = os.path.join(REPO, "my-work", "day3-4-08072026-09072026-dataset", "build_dataset.py")

# Upstream git ref holding the published FlowMonitor outputs.
UPSTREAM_REF = "upstream/main"

# Source-folder class -> the wifi_wip file prefix inside "FlowMonitor Results/<dir>/".
# Only the top-level wifi_wip variants are used (the _shs subfolders are the
# Hexoskin/Bluetooth topology, a different base than our wifi_wip scenarios).
SOURCES = {
    # class      (subdir,      "<prefix>-seed<n>.xml")
    "normal":    ("normal",    "flowmonitor-IoMT-wifi_wip_blocksec3-mitm"),
    "dos":       ("dos",       "flowmonitor-IoMT-wifi_wip_blocksec_dos3-mitm"),
    "ddos":      ("ddos",      "flowmonitor-IoMT-wifi_wip_blocksec_ddos3-mitm"),
    "blackhole": ("blackhole", "flowmonitor-IoMT-wifi_wip_blocksec_black3-blackhole"),
    "mitm":      ("mitm",      "flowmonitor-IoMT-wifi_wip_blocksec_mitm2_sec10-mitm"),
    "mqtt":      ("mqtt",      "flowmonitor-IoMT-wifi_wip_blocksec_mqtt3-mqtt"),
}
SEEDS = range(1, 11)  # the study publishes 10 seeds per class


def git_show(ref_path):
    """Return the bytes of `ref_path` from the git object store (no checkout)."""
    return subprocess.run(
        ["git", "-C", REPO, "show", ref_path],
        check=True, stdout=subprocess.PIPE,
    ).stdout


def extract(rawdir):
    os.makedirs(rawdir, exist_ok=True)
    n = 0
    for cls, (subdir, prefix) in SOURCES.items():
        for s in SEEDS:
            src = f"{UPSTREAM_REF}:FlowMonitor Results/{subdir}/{prefix}-seed{s}.xml"
            dst = os.path.join(rawdir, f"author_{cls}_seed{s}.xml")
            with open(dst, "wb") as fh:
                fh.write(git_show(src))
            n += 1
    print(f"extracted {n} author XMLs -> {os.path.relpath(rawdir, HERE)}/")


def write_manifest(path, rawdir):
    rows = [["file", "scenario", "intensity", "run"]]
    for cls in SOURCES:
        for s in SEEDS:
            rel = os.path.join(os.path.basename(rawdir), f"author_{cls}_seed{s}.xml")
            # intensity=0: the author data is a single fixed configuration per class,
            # with no attack-intensity knob (unlike our sweep). Kept only for schema
            # parity; it is not a feature.
            rows.append([rel, cls, 0, s])
    with open(path, "w", newline="") as fh:
        csv.writer(fh).writerows(rows)
    print(f"wrote {os.path.basename(path)} ({len(rows) - 1} runs)")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-extract", action="store_true",
                    help="skip pulling XMLs from upstream; reuse raw_author/ on disk")
    ap.add_argument("--rawdir", default=os.path.join(HERE, "raw_author"))
    ap.add_argument("--manifest", default=os.path.join(HERE, "manifest_author.csv"))
    ap.add_argument("--outdir", default=os.path.join(HERE, "out"))
    args = ap.parse_args()

    if not os.path.exists(BUILDER):
        sys.exit(f"parser not found: {BUILDER}")

    if not args.no_extract:
        extract(args.rawdir)
    write_manifest(args.manifest, args.rawdir)

    # Single source of truth for feature computation: the same builder used for
    # our own dataset. Any change to feature definitions happens there, once.
    subprocess.run(
        [sys.executable, BUILDER, "--manifest", args.manifest, "--outdir", args.outdir],
        check=True,
    )


if __name__ == "__main__":
    main()
