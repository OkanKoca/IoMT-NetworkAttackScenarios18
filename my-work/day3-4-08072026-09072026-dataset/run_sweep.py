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
MANIFEST_PROBES = os.path.join(HERE, "manifest_probes.csv")
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
# DoS intensity: flood rate (pkt/s). The 1/2/5 points exist for the same reason as
# grey's 0.02/0.05: the curve has to reach its floor to show a collapse. At rate10 the
# flood is ~82 kbps against a ~12 Mbps congested medium and detection is already down to
# 0.50 -- but 0.50 is where the grid STOPS, not where the attack becomes invisible, so
# the arm cannot be said to bottom out. These runs are also the cheap ones (~20 s): the
# interesting region and the affordable region are the same place.
DOS_RATES = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000]
DDOS_NATTACKERS_GRID = [1, 2, 3, 5, 8]           # DDoS intensity: number of flooders
DDOS_SEEDS = 5                                   # fewer seeds — DDoS runs are expensive
BLACKHOLE_INTENSITY = 1.0                        # single point (= grey-hole p=1 endpoint)

# --- Probe configurations (evaluated, NOT trained on) ---------------------
# A probe answers "what does the detector, as trained, say about THIS?" Probes are
# swept here so the whole regeneration is paid once, but they are written to a
# SEPARATE manifest so they cannot leak into training.
#
# Three reasons a configuration belongs here rather than in the training set:
#   1. Its feature vector is indistinguishable from an existing class, so training on
#      it would put one vector under two labels (label noise). This already cost us
#      once: training the sub-10 stealth DoS points raised the false-alarm rate from
#      12.5% to 35% and dropped macro-F1 0.809 -> 0.741.
#   2. The question is about generalization ("what does it do with an attack modality
#      it never saw?"), which training on the answer would destroy.
#   3. Keeping the training set fixed keeps the headline numbers comparable across
#      this change -- a probe cannot move them.
#
# TIMING-MITM. Deliberately a probe FIRST. The scientific question is not "can a model
# separate six classes" (ordinary) but "what does a detector trained on volume and
# delivery attacks say about a TIMING attack it has never seen?" -- and the expected
# answer, that it reports greyhole, is direct evidence for this project's thesis that
# flow-based detection reads mechanism rather than intent. Promoting mitm to a training
# class stays open, but it is a decision to make with the probe result in hand: mitm at
# low delay is byte-identical to grey p=0, so training it risks turning greyhole (F1
# 0.944) into a confusable pair -- the same failure that dos<->ddos already has.
# delay=0 is absent on purpose: it IS grey p=0, measured below as the relay baseline.
MITM_DELAYS_MS = [1, 2, 5, 10, 20, 50, 100, 200]
MITM_SEEDS = 10
# RELAY BASELINE. grey p=0 = an on-path relay that drops nothing. Not a training class
# (its behaviour is indistinguishable from doing nothing, so it cannot carry an attack
# label), but it is the zero point BOTH the grey delivery curve and the mitm timing
# curve must be read against: an intensity curve only shows the variable being swept,
# and the relay is present at every point. Extended 10 -> 40 seeds to match the normal
# baseline's seed count, so the two can be compared without an n mismatch. (docs/19)
RELAY_BASELINE_SEEDS = 40
# RELAY POSITION. The relay has always been STA8, the node FARTHEST from the AP
# (31.6 m), so its measured cost mixes "an extra hop" with "a distant node". Sweeping
# the position with the attack switched off (p=0) separates them. Indices are distances
# on the grid: STA5 10.0 m, STA6 14.1 m, STA7 22.4 m, STA8 31.6 m, STA4 40.0 m. Until
# this is measured, the relay's -2.09 sigma delivery cost must be reported as specific
# to this topology. (docs/19 section 7)
RELAY_POSITIONS = [5, 6, 7, 4]                   # 8 is covered by the baseline above
RELAY_POSITION_SEEDS = 10
# One position gets the full seed count instead of 10. Measuring grey-hole against the
# BENIGN RELAY (rather than against normal) is what gives the delivery axis a real
# collapse curve, and in that comparison the benign relay is the negative class -- so its
# spread sets the false-alarm floor directly. At STA8 that floor is 0.35, because the
# benign relay there is bimodal: ~28% of its runs lose the first burst entirely and land
# a whole OnOff period out. STA5 sits 10 m from the AP with delivery 0.987 +/- little, so
# it should be a far cleaner negative class. 40 seeds matches the STA8 baseline's count,
# so the two floors can be compared without an n mismatch.
RELAY_CLEAN_POSITION = 5
RELAY_CLEAN_SEEDS = 40
# The grey-hole grid repeated at the clean position. This is NOT optional decoration: the
# benign-relay comparison is only valid when both sides sit at the SAME position, because
# position is separable on its own. Measured: a classifier tells two BENIGN relays (both
# p=0, both harmless) apart by position alone at 0.762 accuracy, chance being 0.50. So
# pairing an STA5 negative class with an STA8 positive class would credit the detector for
# recognizing distance and report it as recognizing malice.
GREY_CLEAN_POSITION_GRID = P_GRID
GREY_CLEAN_SEEDS = 10
# VOLUME-MATCHED DoS/DDoS. The detector's weakest pair (dos F1 0.672, ddos 0.577)
# confuses them in both directions, and the standing explanation is that one strong
# flood and several weak ones carry the same volume signature. That is a hypothesis
# about WHICH feature is doing the work, and it is testable: hold total offered load
# fixed at 200 pkt/s and vary only how it is distributed across attackers. If flow
# COUNT still separates them, the confusion is a grid artifact and more configs fix
# it; if it does not, "indistinguishable at equal volume" becomes a defensible finding.
# Either outcome is a result. A probe rather than training data because the existing
# ddos intensity axis is the attacker count, and these configs share attacker counts
# with the trained ones while meaning something different -- as training rows they
# would silently merge into the wrong config groups under the grouped CV.
VOLUME_MATCHED_TOTAL = 200                       # pkt/s, matches the trained dos rate200
VOLUME_MATCHED_SPLITS = [(2, 100), (4, 50), (8, 25)]  # (attackers, per-attacker rate)
VOLUME_MATCHED_SEEDS = 10
# Seeds start past the training grid's range on purpose. The single-flooder reference
# arm is dos at rate 200, which is also a trained configuration -- run at seeds 1..10 it
# reproduces the trained rows byte for byte, so "probe" would have been a label on copies
# of training data. Shifting the seeds makes the arm genuinely unseen. The whole block
# shifts together, not just that arm, because the comparison's premise is that the four
# configurations differ ONLY in how the load is split; a per-arm seed set would break it.
VOLUME_MATCHED_SEED_START = 11

# Scenario -> (source file, ns-3 target name). The functional attacks (docs/07).
SCENARIOS = {
    "normal": ("IoMT-wifi_wip.cc", "IoMT-wifi_wip"),
    "dos": ("IoMT-wifi_wip_dos.cc", "IoMT-wifi_wip_dos"),
    "greyhole": ("IoMT-wifi_grey.cc", "IoMT-wifi_grey"),
    "ddos": ("IoMT-wifi_ddos.cc", "IoMT-wifi_ddos"),
    "blackhole": ("IoMT-wifi_black.cc", "IoMT-wifi_black"),
    "mitm": ("IoMT-wifi_mitm.cc", "IoMT-wifi_mitm"),
}

# Shared headers the scenarios #include. Copied into scratch/ alongside the .cc
# files (a scratch source finds a header in its own directory), so per-run noise
# AND the victim-path timing stamp each live in one place instead of being
# duplicated across the scenarios. iomt-timing.h must be listed here: a scenario
# that #includes it would otherwise build against whatever stale copy happened to
# be left in scratch/, silently decoupling the sweep from the authored header.
SHARED_HEADERS = ["iomt-noise.h", "iomt-timing.h"]

# One planned run: what build_dataset.py needs (scenario/intensity/run) plus how to
# launch it (target binary + CLI args). The manifest and the job list both derive from these.
#
# `split` routes the run to one of two manifests: "train" -> manifest.csv (the dataset the
# detector is fitted on), "probe" -> manifest_probes.csv (configurations the detector is only
# ASKED about). Both are swept in the same parallel pool -- the split is about which file the
# metadata lands in, not about how the run executes. Keeping them in separate files rather
# than one file with a column means a probe cannot reach training by someone forgetting to
# filter: build_dataset.py reads one manifest and knows nothing about splits.
Spec = namedtuple("Spec", "target name extra_args scenario intensity run split",
                  defaults=("train",))


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

    rawdir is passed in the job tuple rather than read from the module global RAW: under
    the forkserver start method (Python 3.14's default on Linux) workers re-import this
    module fresh, so a RAW reassigned in main() for --outroot would NOT reach them and they
    would resolve outputs against the default sweep dir. Threading it through the job makes
    the output location explicit and start-method-independent.
    """
    target, name, extra_args, force, rawdir = job
    out_prefix = os.path.join(rawdir, name)
    if not force and os.path.exists(out_prefix + ".xml"):
        return (name, "skip")
    env = dict(os.environ, LD_LIBRARY_PATH=BUILD_LIB)
    cmd = [binary_path(target), *extra_args, f"--output={out_prefix}"]
    with tempfile.TemporaryDirectory(prefix="ns3run_") as cwd:
        proc = subprocess.run(cmd, cwd=cwd, env=env,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        return (name, "FAIL", proc.stderr.decode(errors="replace"))
    # Persist the victim-path end-to-end delay (iomt-timing.h's ReportTiming line) into a
    # sidecar next to the XML. FlowMonitor's XML cannot carry it -- the stamp is measured
    # BELOW the flow layer -- so the sweep captures stdout and keeps the one line
    # build_dataset parses. n=0 (a fully denied path, e.g. blackhole) is a real value and is
    # written verbatim; absence of the line (an un-instrumented binary) leaves no sidecar,
    # which build_dataset reads as "no timing", not as zero delay.
    for line in proc.stdout.decode(errors="replace").splitlines():
        if line.startswith("End-to-end delay"):
            with open(out_prefix + ".timing", "w") as fh:
                fh.write(line + "\n")
            break
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

    # --- Probes: swept here, but written to a separate manifest (see Spec) --------
    # Timing-MITM — sweep the added hold. Intensity is the delay in ms.
    for d in MITM_DELAYS_MS:
        for run in range(1, MITM_SEEDS + 1):
            specs.append(Spec("IoMT-wifi_mitm", f"mitm_d{d}_r{run}",
                              [f"--delay={d}", f"--run={run}"], "mitm", d, run, "probe"))
    # Relay baseline — grey p=0, the on-path relay with the attack switched off.
    for run in range(1, RELAY_BASELINE_SEEDS + 1):
        specs.append(Spec("IoMT-wifi_grey", f"relay_p0_r{run}",
                          ["--p=0.0", f"--run={run}"], "relay", 0.0, run, "probe"))
    # Relay position — same zero-attack relay, moved around the grid. Intensity is the
    # STA index, which is a stand-in for distance (see RELAY_POSITIONS).
    for idx in RELAY_POSITIONS:
        n_seeds = RELAY_CLEAN_SEEDS if idx == RELAY_CLEAN_POSITION else RELAY_POSITION_SEEDS
        for run in range(1, n_seeds + 1):
            specs.append(Spec("IoMT-wifi_grey", f"relaypos_sta{idx}_r{run}",
                              ["--p=0.0", f"--relay={idx}", f"--run={run}"],
                              "relaypos", idx, run, "probe"))
    # Grey-hole at the clean position — position-matched partner for the STA5 relay
    # baseline, so the benign-vs-malicious comparison is not confounded by distance.
    for p in GREY_CLEAN_POSITION_GRID:
        for run in range(1, GREY_CLEAN_SEEDS + 1):
            specs.append(Spec("IoMT-wifi_grey", f"greypos_sta{RELAY_CLEAN_POSITION}_p{p}_r{run}",
                              [f"--p={p}", f"--relay={RELAY_CLEAN_POSITION}", f"--run={run}"],
                              "greypos", p, run, "probe"))
    # Volume-matched DDoS — same total offered load, split across different attacker
    # counts. Intensity is the attacker count; the per-attacker rate is in the name.
    vm_seeds = range(VOLUME_MATCHED_SEED_START,
                     VOLUME_MATCHED_SEED_START + VOLUME_MATCHED_SEEDS)
    for na, rate in VOLUME_MATCHED_SPLITS:
        for run in vm_seeds:
            specs.append(Spec("IoMT-wifi_ddos", f"volmatch_na{na}_r{rate}_run{run}",
                              [f"--nattackers={na}", f"--rate={rate}", f"--run={run}"],
                              "volmatch_ddos", na, run, "probe"))
    # The single-flooder reference point at the same total load, run through the DoS
    # scenario. dos rate200 is also a trained configuration, so this arm is only a probe
    # by virtue of its seeds (VOLUME_MATCHED_SEED_START) -- at the training seeds it would
    # BE the training rows. Keeping it in this manifest and on this block's seed set is
    # what makes the four configurations differ ONLY in how the load is split.
    for run in vm_seeds:
        specs.append(Spec("IoMT-wifi_wip_dos", f"volmatch_na1_r{VOLUME_MATCHED_TOTAL}_run{run}",
                          [f"--rate={VOLUME_MATCHED_TOTAL}", f"--run={run}"],
                          "volmatch_dos", 1, run, "probe"))
    return specs


def write_manifest(specs):
    """Write one manifest per split; both are what build_dataset.py consumes.

    Written from the planned-run list, so the manifests describe what was ASKED for
    independently of what any individual run did -- a failed run leaves a missing XML that
    build_dataset.py will complain about by name, which is louder than a silently short file.
    """
    for split, path in (("train", MANIFEST), ("probe", MANIFEST_PROBES)):
        rows = [s for s in specs if s.split == split]
        with open(path, "w") as fh:
            fh.write("file,scenario,intensity,run\n")
            for s in rows:
                fh.write(f"raw/{s.name}.xml,{s.scenario},{s.intensity},{s.run}\n")
        print(f"Wrote {os.path.basename(path)} with {len(rows)} runs.")


def main():
    global RAW, MANIFEST, MANIFEST_PROBES
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="print the planned runs, no side effects")
    ap.add_argument("--force", action="store_true", help="re-run even if the XML exists")
    ap.add_argument("--jobs", type=int, default=4,
                    help="parallel workers (default 4; use 1 for serial/debug, fewer to cap RAM)")
    ap.add_argument("--outroot", default=None,
                    help="relocate raw/ + both manifests under this dir, leaving a frozen "
                         "sweep's outputs untouched (the experiment branch writes here)")
    args = ap.parse_args()

    # Redirect all outputs under --outroot so a regeneration cannot overwrite a frozen sweep's
    # raw XMLs or manifests. The scenario BUILD (scratch copy + compile) is shared regardless,
    # which is intended: the experiment wants the newly instrumented binaries.
    if args.outroot:
        RAW = os.path.abspath(os.path.join(args.outroot, "raw"))
        MANIFEST = os.path.abspath(os.path.join(args.outroot, "manifest.csv"))
        MANIFEST_PROBES = os.path.abspath(os.path.join(args.outroot, "manifest_probes.csv"))

    specs = build_specs()
    n_train = sum(1 for s in specs if s.split == "train")
    print(f"Planned {len(specs)} runs ({n_train} train, {len(specs) - n_train} probe).")

    if args.dry_run:
        for s in specs:
            print(f"[dry:{s.split:5s}] {s.target} {' '.join(s.extra_args)} --output=raw/{s.name}")
        return

    os.makedirs(RAW, exist_ok=True)
    build_all()                 # serial, once, before any parallel run
    for s in specs:             # fail fast if a binary is missing, before spinning up the pool
        binary_path(s.target)
    write_manifest(specs)

    jobs = [(s.target, s.name, s.extra_args, args.force, RAW) for s in specs]
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
    if fails:
        print("Failures (last stderr line):")
        for name, detail in fails:
            last = detail.strip().splitlines()[-1] if detail.strip() else "(no stderr)"
            print(f"  {name}: {last}")
        sys.exit(1)


if __name__ == "__main__":
    main()
