import pandas as pd

# Load the combined ANOVA results
anova_df = pd.read_csv("anova_results.csv")

# Pivot the data so each metric becomes a column
pivot_df = anova_df.pivot_table(index=["Scenario", "Device"], columns="Metric", values="Mean").reset_index()

# Compute baseline thresholds (based on NORMAL scenario)
def compute_thresholds(df):
    normal_df = df[df["Scenario"] == "NORMAL"]
    thresholds = {}
    for metric in ["Throughput", "Delay", "Jitter", "PacketLoss"]:
        if metric in normal_df.columns:
            normal_val = normal_df[metric].mean()
            if metric == "Throughput":
                thresholds[metric] = 0.9 * normal_val  # Lower bound
            else:
                thresholds[metric] = 1.1 * normal_val  # Upper bound
    return thresholds

# Check if value violates the threshold
def check_violation(metric, value, thresholds):
    if metric not in thresholds or pd.isnull(value):
        return "N/A"
    if metric == "Throughput":
        return "❌" if value < thresholds[metric] else "✅"
    else:
        return "❌" if value > thresholds[metric] else "✅"

# Run benchmarking
def benchmark(df, thresholds):
    results = []
    for _, row in df.iterrows():
        record = {
            "Scenario": row["Scenario"],
            "Device": row["Device"]
        }
        for metric in ["Throughput", "Delay", "Jitter", "PacketLoss"]:
            val = row.get(metric, None)
            record[f"{metric}_Value"] = val
            record[f"{metric}_Status"] = check_violation(metric, val, thresholds)
        results.append(record)
    return pd.DataFrame(results)

# Run the analysis
thresholds = compute_thresholds(pivot_df)
summary_df = benchmark(pivot_df, thresholds)

# Output
print("✅ Derived Thresholds:")
print(thresholds)
print("\n📊 Benchmark Summary:")
print(summary_df.to_string(index=False))

# Save to CSV
summary_df.to_csv("benchmark_summary.csv", index=False)

