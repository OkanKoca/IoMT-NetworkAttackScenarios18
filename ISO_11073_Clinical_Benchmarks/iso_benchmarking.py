import pandas as pd
import ast

# --- Load ANOVA data ---
wip_df = pd.read_csv("anova_results.csv")
shs_df = pd.read_csv("anova_results2.csv")

# --- Load Tukey HSD result files ---
try:
    tukey_df1 = pd.read_csv("tukey_hsd_results.csv")
except Exception:
    tukey_df1 = pd.DataFrame()

try:
    tukey_df2 = pd.read_csv("tukey_hsd_results2.csv")
except Exception:
    tukey_df2 = pd.DataFrame()

# --- Metric mapping ---
def map_metric(metric_name):
    if "Throughput" in metric_name:
        return "Throughput"
    elif "Delay" in metric_name:
        return "Delay"
    elif "Jitter" in metric_name:
        return "Jitter"
    elif "Packet_Loss" in metric_name or "PacketLoss" in metric_name:
        return "PacketLoss"
    return metric_name

# --- Flatten 'Mean' stringified dicts into rows ---
def flatten_confidence_df(df):
    rows = []
    for _, row in df.iterrows():
        metric = map_metric(row["Metric"])
        scenario = row["Scenario"].upper()
        value = row["Mean"]
        rows.append({
            "Scenario": scenario,
            "Metric": metric,
            "Value": value
        })
    return pd.DataFrame(rows)

# --- Compute thresholds from NORMAL baseline ---
def compute_thresholds_from_baseline(df):
    normal_means = {}
    for _, row in df.iterrows():
        metric = map_metric(row["Metric"])
        scenario = row["Scenario"].upper()
        if scenario == "NORMAL":
            normal_means[metric] = row["Mean"]

    thresholds = {
        "Throughput": 0.9 * normal_means.get("Throughput", 0),
        "Delay": 1.1 * normal_means.get("Delay", 0),
        "Jitter": 1.1 * normal_means.get("Jitter", 0),
        "PacketLoss": 1.1 * normal_means.get("PacketLoss", 0),
    }
    return thresholds

# --- Check violation status ---
def check_violation(metric, value, thresholds):
    if pd.isnull(value):
        return "N/A"
    if metric == "Throughput":
        return "❌" if value < thresholds[metric] else "✅"
    else:
        return "❌" if value > thresholds[metric] else "✅"

# --- Benchmarking function ---
def benchmark(df, label, thresholds):
    results = []
    for _, row in df.iterrows():
        rec = {
            "Scenario": row["Scenario"],
            "Device": label
        }
        for metric in ["Throughput", "Delay", "Jitter", "PacketLoss"]:
            val = row.get(metric, None)
            rec[f"{metric}_Value"] = val
            rec[f"{metric}_Status"] = check_violation(metric, val, thresholds)
        results.append(rec)
    return pd.DataFrame(results)

# --- Process and pivot ANOVA data ---
flat_wip = flatten_confidence_df(wip_df)
flat_shs = flatten_confidence_df(shs_df)

pivot_wip = flat_wip.pivot(index="Scenario", columns="Metric", values="Value").reset_index()
pivot_shs = flat_shs.pivot(index="Scenario", columns="Metric", values="Value").reset_index()

# --- Calculate thresholds from WIP NORMAL baseline ---
acceptable_thresholds = compute_thresholds_from_baseline(wip_df)

print("✅ Derived Thresholds from WIP (NORMAL scenario):")
for k, v in acceptable_thresholds.items():
    print(f"  {k}: {v:.4f}")

# --- Run benchmarking ---
wip_benchmark = benchmark(pivot_wip, "WIP", acceptable_thresholds)
shs_benchmark = benchmark(pivot_shs, "SHS", acceptable_thresholds)

combined = pd.concat([wip_benchmark, shs_benchmark], ignore_index=True)

print("\n📊 Benchmark Summary:")
print(combined.to_string(index=False))

combined.to_csv("benchmark_summary.csv", index=False)

# --- Function to print/save significant Tukey results ---
def print_significant_tukey(tukey_df, label):
    if tukey_df.empty:
        print(f"\nℹ️ No Tukey HSD results found in {label}.")
        return
    # Normalize column name for rejection flag
    reject_col = None
    for col in tukey_df.columns:
        if col.lower() == 'reject':
            reject_col = col
            break
    if reject_col is None:
        print(f"\n⚠️ 'Reject' column not found in {label} Tukey data.")
        return
    significant = tukey_df[tukey_df[reject_col] == True]
    print(f"\n🔍 Significant Differences (Tukey HSD) - {label}:")
    if significant.empty:
        print("No significant differences found.")
    else:
        print(significant.to_string(index=False))
        significant.to_csv(f"significant_tukey_{label}.csv", index=False)

# --- Analyze Tukey HSD files ---
print_significant_tukey(tukey_df1, "File 1")
print_significant_tukey(tukey_df2, "File 2")

