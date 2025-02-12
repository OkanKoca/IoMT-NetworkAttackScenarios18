import matplotlib.pyplot as plt

# FlowMonitor stats
flow_ids = [1, 2]  # Flow IDs to analyze
tx_packets = [500, 450]  # Transmitted packets for each flow
rx_packets = [480, 440]  # Received packets for each flow

# Compute packet loss percentage
packet_loss = [(tx - rx) / tx * 100 for tx, rx in zip(tx_packets, rx_packets)]

# Plot the graph
plt.figure(figsize=(10, 6))

# Throughput
plt.subplot(2, 2, 1)
plt.plot(flow_ids, [0.5, 0.3], 'b-o')
plt.title("Network Throughput (Mbps)")
plt.xlabel("Flow ID")
plt.ylabel("Throughput (Mbps)")

# End-to-End Delay
plt.subplot(2, 2, 2)
plt.plot(flow_ids, [0.001, 0.0025], 'r-o')
plt.title("End-to-End Delay (Seconds)")
plt.xlabel("Flow ID")
plt.ylabel("Delay (s)")

# Jitter
plt.subplot(2, 2, 3)
plt.plot(flow_ids, [1e-5, 3e-6], 'g-o')
plt.title("Network Jitter (Seconds)")
plt.xlabel("Flow ID")
plt.ylabel("Jitter (s)")

# Packet Loss
plt.subplot(2, 2, 4)
plt.plot(flow_ids, packet_loss, 'm-o')
plt.title("Packet Loss (%)")
plt.xlabel("Flow ID")
plt.ylabel("Packet Loss (%)")

plt.tight_layout()
plt.show()

