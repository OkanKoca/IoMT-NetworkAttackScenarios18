#!/usr/bin/env python3
"""
build_dataset.py
--------------------------------------------------------------------------
FlowMonitor XML -> labeled flow dataset for the attack detector.

Two-layer output (see docs/07):
  * flows.csv   : lossless intermediate, one row per flow per run (transparency)
  * dataset.csv : one row per RUN, a run-level feature vector (what the model sees)

Each input XML is described by a manifest row (file, scenario, intensity, run),
so scenario/intensity/run metadata never has to be parsed out of filenames.

Usage:
  python3 build_dataset.py --manifest manifest.csv --outdir out
--------------------------------------------------------------------------
"""

import argparse
import os
import xml.etree.ElementTree as ET

import pandas as pd

# Destination-port -> semantic role. Mapping by *destination* port is
# scenario-agnostic: the source IP changes (STA2 vs relay), but the role a flow
# plays is fixed by where it is headed. (docs/07)
PORT_ROLE = {
    8080: "monitor",    # ECG waveform delivered to the patient monitor (the victim path)
    7070: "relay_in",   # victim traffic arriving at the grey-hole relay (grey-hole only)
    9090: "telemetry",  # untouched low-priority telemetry (contrast flow)
    9: "flood",         # DoS/DDoS flood target port
}


def ns_to_s(text):
    """Parse a FlowMonitor time/duration string like '+1.61368e+09ns' to seconds.

    Kept as one function because this unit parse recurs for every time field;
    getting it right in a single place avoids silent per-field mistakes.
    """
    return float(text.replace("ns", "").replace("+", "")) / 1e9


def parse_xml(path):
    """Return a list of per-flow dicts, joining FlowStats with the classifier.

    Metrics live in <FlowStats>, the 5-tuple (and destination port) lives in
    <Ipv4FlowClassifier>; they share flowId, so we join on it.
    """
    root = ET.parse(path).getroot()

    # 5-tuple table: flowId -> classifier attributes
    clsf = {}
    for f in root.find("Ipv4FlowClassifier").findall("Flow"):
        clsf[int(f.get("flowId"))] = {
            "src": f.get("sourceAddress"),
            "dst": f.get("destinationAddress"),
            "dst_port": int(f.get("destinationPort")),
        }

    flows = []
    for f in root.find("FlowStats").findall("Flow"):
        fid = int(f.get("flowId"))
        c = clsf.get(fid, {})
        tx = int(f.get("txPackets"))
        rx = int(f.get("rxPackets"))
        lost = int(f.get("lostPackets"))
        rx_bytes = int(f.get("rxBytes"))
        # Per-flow ACTIVE window: the span the flow was actually delivering.
        # Chosen over a fixed sim duration so idle tails don't dilute the rate
        # (legit traffic stops at 20s while the sim runs to 30s). (decision: per-flow window)
        t_first_tx = ns_to_s(f.get("timeFirstTxPacket"))
        t_last_rx = ns_to_s(f.get("timeLastRxPacket"))
        t_first_rx = ns_to_s(f.get("timeFirstRxPacket"))
        window = t_last_rx - t_first_rx
        delay_sum = ns_to_s(f.get("delaySum"))
        jitter_sum = ns_to_s(f.get("jitterSum"))

        dst_port = c.get("dst_port")
        flows.append(
            {
                "flowId": fid,
                "role": PORT_ROLE.get(dst_port, "other"),
                "src": c.get("src"),
                "dst": c.get("dst"),
                "dst_port": dst_port,
                "tx": tx,
                "rx": rx,
                "lost": lost,
                "rx_bytes": rx_bytes,
                "t_first_tx": t_first_tx,
                "t_last_rx": t_last_rx,
                # bit/s -> Mbit/s over the flow's own active window; guard empty window.
                "throughput_mbps": (rx_bytes * 8.0 / window / 1e6) if window > 0 else 0.0,
                # mean one-way delay and mean packet-delay-variation, in ms.
                "owd_ms": (delay_sum / rx * 1000.0) if rx > 0 else 0.0,
                "pdv_ms": (jitter_sum / rx * 1000.0) if rx > 0 else 0.0,
            }
        )
    return flows


def _delivery_ratio(flows):
    """End-to-end delivery ratio of the victim (medical) path.

    Grey-hole splits the path in two (sensor->relay on 7070, relay->monitor on 8080),
    so the honest end-to-end ratio joins them: delivered_by_monitor / sent_to_relay.
    When there is no relay hop (normal/DoS) it is the monitor flow's own rx/tx.
    A fully-denied path (blackhole, p=1) has traffic into the relay but no monitor
    flow -> ratio 0, which is exactly right. (docs/05)
    """
    relay_in = [f for f in flows if f["role"] == "relay_in"]
    monitor = [f for f in flows if f["role"] == "monitor"]
    rx_monitor = sum(f["rx"] for f in monitor)
    if relay_in:
        tx_in = sum(f["tx"] for f in relay_in)
        return rx_monitor / tx_in if tx_in > 0 else float("nan")
    if monitor:
        tx_monitor = sum(f["tx"] for f in monitor)
        return rx_monitor / tx_monitor if tx_monitor > 0 else float("nan")
    return float("nan")


def _victim_timing(flows):
    """End-to-end delay and jitter of the victim (medical) path, in ms.

    Follows the same rule as _delivery_ratio, and for the same reason. The grey-hole
    and blackhole scenarios split the victim path into TWO IP flows (sensor->relay on
    7070, relay->monitor on 8080), because a station cannot reach another station
    directly in infrastructure mode. Timing only the 8080 flow would therefore measure
    the LAST LEG in those scenarios and the WHOLE path in the others -- one column
    silently holding two different physical quantities. Measured, it reports the
    relayed path as FASTER than the direct one (14.5 ms vs 16.2 ms) when the relayed
    path is really 1.76x slower (28.4 ms end-to-end), i.e. it hands the model a
    spurious separator pointing the wrong way. Delays add along a path, so sum the legs.

    Jitter: summing each leg's mean |delay variation| is an APPROXIMATION -- two
    independent legs would combine as sqrt(a^2 + b^2), so this is an upper bound. It is
    used anyway because it is at least consistent across classes, which is the property
    a feature must have; timing a single leg is not approximate but wrong.

    Returns (nan, nan) when nothing reaches the monitor (blackhole, grey p=1): a fully
    denied path has no delivered packets to time. That missingness is itself signal and
    is imputed + flagged with an indicator at the ML stage.
    """
    monitor = [f for f in flows if f["role"] == "monitor"]
    if not monitor:
        return float("nan"), float("nan")
    last = max(monitor, key=lambda f: f["rx"])  # busiest, mirroring the rule below
    relay_in = [f for f in flows if f["role"] == "relay_in"]
    if not relay_in:
        return last["owd_ms"], last["pdv_ms"]  # no relay: the 8080 flow IS the path
    first = max(relay_in, key=lambda f: f["rx"])
    return first["owd_ms"] + last["owd_ms"], first["pdv_ms"] + last["pdv_ms"]


def run_features(flows, meta):
    """Reduce a run's flows to one labeled run-level feature vector (3 modalities)."""
    total_tx = sum(f["tx"] for f in flows)
    total_lost = sum(f["lost"] for f in flows)

    # End-to-end timing of the victim path, joining the relay legs where they exist.
    monitor_owd, monitor_pdv = _victim_timing(flows)
    tele = next((f for f in flows if f["role"] == "telemetry"), None)
    active = [f for f in flows if f["rx"] > 0]

    row = {
        # --- metadata (NOT features; must be dropped from X before training) ---
        # `intensity` in particular is a per-attack knob whose UNITS differ by class:
        # grey-hole drop-prob 0-1, DoS flood rate 10-1000 pkt/s, DDoS attacker count 1-8,
        # blackhole 1. These share no common numeric axis, so feeding intensity as a model
        # input is meaningless. It is kept ONLY to group/filter runs for the per-attack
        # detection-vs-intensity curve. (see docs/09 §3)
        "run_id": f"{meta['scenario']}_i{meta['intensity']}_r{meta['run']}",
        "scenario": meta["scenario"],
        "intensity": meta["intensity"],
        "run": meta["run"],
        # --- volume / structure ---
        "n_flows": len(flows),
        # Sum of per-flow throughputs (each on its OWN active window), not total bytes over
        # the run's union window. The union-window version dilutes: a low-rate flood extends
        # the window (to ~30s) more than it adds bytes, so total throughput would DROP below
        # normal for weak DoS -- a backwards signal. Summing per-flow rates keeps it monotonic
        # in intensity and consistent with the per-flow active-window rule. (see docs/09 §5)
        "total_throughput_mbps": sum(f["throughput_mbps"] for f in flows),
        "max_flow_throughput_mbps": max((f["throughput_mbps"] for f in flows), default=0.0),
        "max_flow_txpackets": max((f["tx"] for f in flows), default=0),
        "flow_concentration": (max((f["tx"] for f in flows), default=0) / total_tx) if total_tx > 0 else 0.0,
        # --- delivery integrity ---
        "delivery_ratio": _delivery_ratio(flows),
        "overall_loss_ratio": (total_lost / total_tx) if total_tx > 0 else 0.0,
        # --- timing ---
        "monitor_owd_ms": monitor_owd,
        "monitor_pdv_ms": monitor_pdv,
        "mean_owd_ms": (sum(f["owd_ms"] for f in active) / len(active)) if active else float("nan"),
        "mean_pdv_ms": (sum(f["pdv_ms"] for f in active) / len(active)) if active else float("nan"),
        # --- contrast ---
        "telemetry_throughput_mbps": tele["throughput_mbps"] if tele else 0.0,
        # --- labels ---
        "label_class": meta["scenario"],
        "label_binary": "normal" if meta["scenario"] == "normal" else "attack",
    }
    return row


def main():
    ap = argparse.ArgumentParser(description="FlowMonitor XML -> labeled flow dataset")
    ap.add_argument("--manifest", default="manifest.csv", help="CSV: file,scenario,intensity,run")
    ap.add_argument("--outdir", default="out", help="output directory for flows.csv/dataset.csv")
    args = ap.parse_args()

    manifest = pd.read_csv(args.manifest)
    base = os.path.dirname(os.path.abspath(args.manifest))
    os.makedirs(args.outdir, exist_ok=True)

    flow_rows, run_rows = [], []
    for _, m in manifest.iterrows():
        meta = {"scenario": m["scenario"], "intensity": m["intensity"], "run": int(m["run"])}
        xml_path = os.path.join(base, m["file"])
        flows = parse_xml(xml_path)

        run_id = f"{meta['scenario']}_i{meta['intensity']}_r{meta['run']}"
        for f in flows:
            flow_rows.append({"run_id": run_id, **meta, **f})
        row = run_features(flows, meta)
        # A NaN delivery_ratio means a broken run (no monitor tx: crashed sim, wrong port,
        # early termination), not a real 0% delivery. Surface it loudly with the offending
        # file so it can be investigated rather than silently poisoning the feature vector.
        if pd.isna(row["delivery_ratio"]):
            print(f"WARNING: delivery_ratio is NaN for {m['file']} (run_id={run_id}) "
                  "-> likely a broken run; investigate before training.")
        run_rows.append(row)

    pd.DataFrame(flow_rows).to_csv(os.path.join(args.outdir, "flows.csv"), index=False)
    dataset = pd.DataFrame(run_rows)
    dataset.to_csv(os.path.join(args.outdir, "dataset.csv"), index=False)

    # Dataset-level NaN audit before the file is used for training. Some NaNs are EXPECTED
    # (monitor_owd/pdv on fully-denied paths: blackhole, grey p=1 have no monitor flow to time)
    # and will be imputed + flagged with a missingness indicator at the ML stage. Any NaN in
    # delivery_ratio here would instead signal a broken run.
    nan_cols = dataset.columns[dataset.isna().any()].tolist()
    if nan_cols:
        print("NaN audit -> columns still containing NaN (with count):")
        for c in nan_cols:
            print(f"  {c}: {int(dataset[c].isna().sum())} run(s)")
    else:
        print("NaN audit -> no NaN in any column.")

    print(f"\nParsed {len(manifest)} runs -> {len(flow_rows)} flow rows.")
    print(f"Wrote {args.outdir}/flows.csv and {args.outdir}/dataset.csv\n")
    with pd.option_context("display.width", 200, "display.max_columns", 40):
        print(dataset.to_string(index=False))


if __name__ == "__main__":
    main()
