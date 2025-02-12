import xml.etree.ElementTree as ET
import pandas as pd
import matplotlib.pyplot as plt

# File names
files = {
    "NORMAL": "flowmonitor-stats_blocksec.xml",
    "DOS": "flowmonitor-stats_blocksec_dos.xml",
    "DDOS": "flowmonitor-stats_blocksec_ddos.xml",
    "MITM": "flowmonitor-stats_blocksec_mitm.xml",
    "BLACKHOLE": "flowmonitor-stats_blocksec_black.xml",
}

# Parse XML and extract metrics
def parse_xml(file, scenario_label):
    tree = ET.parse(file)
    root = tree.getroot()
    flows = root.find("FlowStats").findall("Flow")
    
    data = []
    for flow in flows:
        flow_id = flow.attrib.get("flowId")
        txBytes = int(flow.attrib.get("txBytes", 0))
        rxBytes = int(flow.attrib.get("rxBytes", 0))
        txPackets = int(flow.attrib.get("txPackets", 0))
        rxPackets = int(flow.attrib.get("rxPackets", 0))
        lostPackets = int(flow.attrib.get("lostPackets", 0))
        delaySum = float(flow.attrib.get("delaySum", 0).replace("ns", ""))
        jitterSum = float(flow.attrib.get("jitterSum", 0).replace("ns", ""))
        
        throughput = rxBytes / (10 ** 6)  # Convert to MB
        end_to_end_delay = delaySum / (10 ** 9)  # Convert to seconds
        jitter = jitterSum / (10 ** 9)  # Convert to seconds
        packet_loss = lostPackets / (lostPackets + rxPackets) if rxPackets + lostPackets > 0 else 0
        
        data.append({
            "FlowID": flow_id,
            "Throughput (MB)": throughput,
            "End-to-End Delay (s)": end_to_end_delay,
            "Jitter (s)": jitter,
            "Packet Loss (%)": packet_loss * 100,
            "Scenario": scenario_label,
        })
    return data

# Aggregate data for all files
results = []
for label, file in files.items():
    results.extend(parse_xml(file, label))

# Convert to DataFrame
final_df = pd.DataFrame(results)

# Convert columns to numeric types
numeric_columns = ["Throughput (MB)", "End-to-End Delay (s)", "Jitter (s)", "Packet Loss (%)"]
final_df[numeric_columns] = final_df[numeric_columns].apply(pd.to_numeric, errors='coerce')

# Check if there are still non-numeric values in numeric columns
print("Columns with non-numeric values:")
for col in numeric_columns:
    non_numeric_data = final_df[final_df[col].isna()]
    if not non_numeric_data.empty:
        print(f"{col}: {non_numeric_data}")

# Drop rows with invalid numeric data (optional)
final_df = final_df.dropna(subset=numeric_columns)

# Save the detailed flow-level data to CSV
final_df.to_csv("flow_level_blocksec_results.csv", index=False)
print("Flow-level results saved to flow_level_blocksec_results.csv")

# Create a summary table by averaging metrics for each scenario
summary_df = final_df.groupby("Scenario")[numeric_columns].mean().reset_index()

# Save summary results
summary_df.to_csv("summary_blocksec_results.csv", index=False)
print("Summary results saved to summary_blocksec_results.csv")

# Visualization
metrics = ["Throughput (MB)", "End-to-End Delay (s)", "Jitter (s)", "Packet Loss (%)"]
for metric in metrics:
    plt.figure(figsize=(10, 6))
    for scenario in files.keys():
        scenario_data = final_df[final_df["Scenario"] == scenario]
        plt.plot(
            scenario_data["FlowID"],
            scenario_data[metric],
            marker="o",
            label=scenario
        )
    plt.title(f"Comparison of {metric}")
    plt.xlabel("Flow ID")
    plt.ylabel(metric)
    plt.legend()
    plt.grid(True)
    plt.savefig(f"{metric.replace(' ', '_').lower()}_comparison.png")
    plt.show()

