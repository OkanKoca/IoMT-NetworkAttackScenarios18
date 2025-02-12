import xml.etree.ElementTree as ET
import matplotlib.pyplot as plt
import numpy as np

# Function to remove units and convert to float
def parse_value(value_str):
    # Remove any non-numeric characters (like 'ns') and convert to float
    return float(value_str.replace("ns", "").replace("+", ""))

# Parse the flowmonitor stats XML file
tree = ET.parse('flowmonitor-stats_blocksec_ddos.xml')
root = tree.getroot()

# Lists to store extracted values for each flow
throughput = []
delay = []
jitter = []
packet_loss = []
flow_ids = []

# Extracting the flow statistics
for flow in root.findall(".//Flow"):
    flow_id = int(flow.attrib["flowId"])
    
    # Safely get attributes, using a default of 0 if they don't exist
    tx_bytes = int(flow.attrib.get("txBytes", 0))
    rx_bytes = int(flow.attrib.get("rxBytes", 0))
    tx_packets = int(flow.attrib.get("txPackets", 0))
    rx_packets = int(flow.attrib.get("rxPackets", 0))
    lost_packets = int(flow.attrib.get("lostPackets", 0))
    
    # Parse delaySum and jitterSum by removing units and converting to float
    delay_sum = parse_value(flow.attrib.get("delaySum", "0"))
    jitter_sum = parse_value(flow.attrib.get("jitterSum", "0"))
    
    # Parse the time values and remove the 'ns' unit before converting to float
    time_last_tx = parse_value(flow.attrib.get("timeLastTxPacket", "0"))
    time_first_tx = parse_value(flow.attrib.get("timeFirstTxPacket", "0"))

    # Calculate simulation time (in seconds), ensuring it's not zero
    simulation_time = (time_last_tx - time_first_tx) / 1e9  # Convert from ns to seconds
    
    # Check if simulation_time is zero to avoid division by zero
    if simulation_time > 0:
        # Calculate throughput in Mbps
        throughput_value = (tx_bytes * 8) / (simulation_time * 1e6)  # Mbps

        # Calculate average delay and jitter (in seconds)
        avg_delay = delay_sum / tx_packets / 1e9  # Convert from ns to seconds
        avg_jitter = jitter_sum / tx_packets / 1e9  # Convert from ns to seconds

        # Packet loss percentage
        packet_loss_value = (lost_packets / tx_packets) * 100 if tx_packets > 0 else 0

        # Store the values
        throughput.append(throughput_value)
        delay.append(avg_delay)
        jitter.append(avg_jitter)
        packet_loss.append(packet_loss_value)
        flow_ids.append(flow_id)
    else:
        # Print a warning for zero simulation time
        print(f"Warning: Flow {flow_id} has zero simulation time. Skipping this flow.")

# Plotting the extracted metrics

# Throughput Plot
plt.figure(figsize=(10, 6))
plt.subplot(2, 2, 1)
plt.plot(flow_ids, throughput, marker='o', color='b', label="Throughput")
plt.title("Network Throughput (Mbps)")
plt.xlabel("Flow ID")
plt.ylabel("Throughput (Mbps)")
plt.grid(True)

# End-to-End Delay Plot
plt.subplot(2, 2, 2)
plt.plot(flow_ids, delay, marker='o', color='r', label="End-to-End Delay")
plt.title("End-to-End Delay (Seconds)")
plt.xlabel("Flow ID")
plt.ylabel("Delay (s)")
plt.grid(True)

# Jitter Plot
plt.subplot(2, 2, 3)
plt.plot(flow_ids, jitter, marker='o', color='g', label="Jitter")
plt.title("Network Jitter (Seconds)")
plt.xlabel("Flow ID")
plt.ylabel("Jitter (s)")
plt.grid(True)

# Packet Loss Plot
plt.subplot(2, 2, 4)
plt.plot(flow_ids, packet_loss, marker='o', color='purple', label="Packet Loss")
plt.title("Packet Loss (%)")
plt.xlabel("Flow ID")
plt.ylabel("Packet Loss (%)")
plt.grid(True)

# Show the plots
plt.tight_layout()
plt.show()

