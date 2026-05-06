# Assessing IoMT Network Resilience: A Comparative Performance Analysis of Simulated Attacks using NS-3
This study simulates four attack scenarios—DoS, DDoS (UDP Flooding), MITM, Blackhole and MQTT DoS (Command Injection)—on an IoMT network using NS-3.
In a controlled sandbox environment, it evaluates the network Throughput, One-Way Delay
(OWD), Packet Delay Variation (PDV), and Packet loss for a Baxter WIP and a Hexoskin SHS. Graphical results illustrate network degradation under
attacks. The findings identify network vulnerabilities and propose controls to both enhance IoMT
security and resilience and ensure safety in patient care.

Supplementary Appendix is available. See: Zenodo: https://doi.org/10.5281/zenodo.16747386 

# Research Experiment Design
This study design simulates a wireless IoMT network using the WLAN 802.11 protocol, comprising a Wireless Access Point, Baxter Wireless Infusion Pump (WIP), and Hexoskin Smart Health Shirt (SHS). The setup replicates a real-world patient-centric environment for integrated healthcare devices. The aim is to establish security controls for healthcare institutions, leveraging insights from the OpenICE interoperability platform supporting real-time cardiac and cognitive monitoring, as shown in the Figure below.

<img width="1375" height="712" alt="image" src="https://github.com/user-attachments/assets/cceaea07-9835-4517-b8b9-64f5854a93e9" />

## Network Attack Model Scenarios
### DoS UDP Flooding Attack:
The attack was simulated on each network node, with one node as the attacker. Configured with the
UDPEchoClientHelper class (as per pseudo-code in Listing 1.4), the attacker transmitted excessive 1024-
byte packets at 0.01-second intervals, with a maximum limit of 1,000,000 packets, as implemented in
NS-3,. The attack aims to exhaust the resources of the target node (e.g. bandwidth) and interfere with
legitimate traffic by producing excessive UDP traffic[16].
#### Expected Impact: 
A UDP flood attack can degrade the target node performance, leading to network
disconnection, memory exhaustion, and device malfunction. In a WIP real-world setting, this could result
in incorrect or delayed medication dosages, threatening patient safety. On the Hexoskin device, it may
cause delayed or inaccurate health readings, compromising reliability.
### DDoS UDP Flooding Attack:
The attack was simulated on all nodes, targeting each device individually. Unlike the previous DoS attack,
multiple attacker nodes flood the target node with excessive UDP traffic. The attack loop iterates over all
nodes in the attacker container, with each node configured using the UDPEchoClientHelper class in
NS-3 to generate UDP traffic and install the attack application (as per pseudo-code in Listing 1.5).
Expected Impact: Similar to the single-node DoS UDP flood, this attack can deplete network performance,
saturating bandwidth, deny node resources, and overload memory, affecting device functionality
[16]. On the WIP, it could delay medical infusion delivery, while the Hexoskin SHS may produce inaccurate
health readings. Excessive traffic may crash both devices, complicating mitigation. Table 2 compares the
impact of the UDP flooding attack between single-node DoS and multiple-node DDoS scenarios.
Table 2. Comparative Impact of DoS and DDoS UDP Flooding Attacks
Impact Factor DoS UDP
Flood
DDoS UDP
Flood
Traffic Volume Single attack source Multiple attacking
nodes
Detection Easier to identify Harder; requires
network-wide analysis
Impact Scope Localized to one
node
Affects entire network
Mitigation Simple rate-limiting Needs load balancing,
clustering
### MITM Attack:
This MITM attack intercepts, modifies, and forwards packets from target nodes using the MITMCallBack
function, linked to the attacker node for packet handling, as shown in Listing 1.6.
The attacker node modifies the first byte of packets and drops any exceeding 512 bytes; smaller
packets are then forwarded. The MITMNode CallBack function, linked to the attacker node, handles
packet reception (see Listing 1.7 ).
#### Expected Impact: 
This attack compromises packet integrity, causing packet loss, data corruption, and
misinterpretation of device applications. In real-world scenarios, the Baxter WIP could issue incorrect
drug commands, while the Hexoskin SHS may transmit inaccurate health metrics.
### Blackhole (BH) Attack:
The BH attack was simulated with a MITM attacker node intercepting and manipulating traffic to assess
network vulnerabilities. The attacker exploits IP routing tables, inspecting and analyzing packets, and
selectively dropping or forwarding them using the MitmInterceptAndDrop function (shown in Listing
1.8 ), disrupting legitimate communication.
#### Expected Impact: 
Packet drops cause communication failure and denial of service on the target node,
while other traffic remains unaffected. This results in delays in critical medical data transmission, minimal
packet loss, and reduced network throughput, with no notable impact on non-targeted nodes [16].
The simulated attacks on the IoMT network are implemented in C++ and NS-3, with Python scripts
that generate the results for the performance analysis. The code is available on GitHub [17].
### MQTT DoS Broker Flood (Command Injection) Attack:
This attack simulates a command injection that floods the MQTT broker with excessive messages, causing
a Denial-of-Service (DoS) by overloading and crashing the system. It disrupts communication for IoMT
devices like Baxter WIP and Hexoskin SHS, leading to traffic delays or signal inconsistencies that may
delay commands or produce inaccurate diagnostics, risking patient misdiagnosis. Considering that NS-3
lacks native MQTT support [18], UDP traffic models the MQTT message flow and broker overload. The
attack is implemented using a malicious UDP client that sends high rate, oversized PUBLISH messages
that are larger the default 256 MB MQTT payload to the broker (UDP server), simulating malformed
MQTT packets, as shown in Listing 1.9. and see Listing 1.10.
#### Expected Impact: 
The MQTT flood attack degrades IoMT network performance by overwhelming the
broker with high-rate, oversized messages, causing around 10% packet loss, increased latency, reduced
throughput, and potential DoS conditions for devices like the WIP and SHS. Beyond disrupting critical
medical communications, it also floods blockchain logs and triggers intrusion alerts, simulating a realistic
and severe cyberthreats to medical IoMT environments.

### Energy Monitoring of IoMT Devices
To assess the energy efficiency of wearable IoMT devices under normal and attack conditions, a custom
BluetoothEnergyModel was developed in NS-3 [19] [20], and applied to the Hexoskin Smart Health Shirt
(SHS), which uses Bluetooth Low Energy (BLE) as shown in see Listing 1.11. The model simulates battery
consumption by defining three states—IDLE (0.01 A), TRANSMITTING (0.15 A), and RECEIVING
(0.12 A)—at a constant operating voltage of 3.0 V, capturing realistic BLE behavior in both benign and
adversarial scenarios.

The BluetoothEnergyModel was linked to the energy source and set to alternate between TRANSMITTING
(0.2s) and IDLE (4.8s) every 5 seconds, simulating periodic data transmission typical of
real-world Bluetooth sensors as shown in Listing 1.12. This scheduling in NS-3 ensures consistent, repeatable
energy usage throughout the simulation.
To monitor battery, drain or consumption, the simulation also includes a RemainingEnergyCallback
function (shown in Listing 1.13 ) that logs the remaining energy of each node, including the SHS node
(HexoskinNode.Get(0)) at every interval.

## Network Performance Analysis
This section presents a comparative performance analysis of the four simulated IoMT network attack scenarios targeting both the Baxter WIP, and the Hexoskin SHS devices. Key metrics -Network Throughput, OWD, PDV, and Packet Loss - are analyzed from line graphs, with a NORMAL network scenario as a benchmark for comparison. The graphs are generated using a Python script with matplotlib and pandas, extracting flow monitor statistics from XML files, and producing a CSV file of key metric values against Flow IDs. The analysis of these results are discussed below.

### Network Throughput
The consolidated network throughput from all five scenarios on both targeted device nodes are summarized on projected graphs shown in Fig. 3 and Fig. 4 respectively.

<img width="305" height="205" alt="image" src="https://github.com/user-attachments/assets/e862078e-4f1c-488c-9a2b-18e75745b25e" />


Throughput analysis of the Baxter WIP shows significant degradation under all attacks, with BH and DDoS UDP floods reducing throughput to near zero by Flow ID 3, while NORMAL conditions maintain high performance.  

For Hexoskin SHS, throughput starts at 2 Mbps under NORMAL conditions and stabilizes at 1 Mbps by Flow ID 3. Attacks affect throughput differently: DoS peaks at 4 Mbps, dropping to 0 Mbps at Flow ID 3; DDoS decreases from 3 Mbps to 0.5 Mbps; MITM drops from 2 Mbps to 0 Mbps; and BH consistently results in 0 Mbps by Flow ID 3 \cite{c20}.

### One-Way Delay (OWD)
The graphs in Fig. 5 and Fig. 6 illustrate the comparative performance analysis of OWD for all five network scenarios.


OWD analysis of WIP and SHS in IoMT networks reveals distinct delay patterns under various attack scenarios. For WIP, NORMAL conditions exhibit stable delays, BH causes no delay, MITM disrupts packets without affecting delay beyond Flow ID 1, DoS introduces moderate delays peaking at Flow ID 3, and DDoS maintains a consistent OWD. Similarly, SHS under NORMAL conditions shows a stable 2s delay, while DoS leads to significant (20s) delays, DDoS induces moderate (10s) delays at Flow ID 2, MITM has no impact, and BH introduces an initial 5s delay with no further effects.

<img width="359" height="250" alt="image" src="https://github.com/user-attachments/assets/53dd3462-d8e2-4c1f-8b82-3e6244cba98f" />

 
### Packet Delay Variation (PDV)
Consolidating the PDV from all five scenarios, the 
graphs are shown on Fig. 7 and Fig. 8.

<img width="297" height="191" alt="image" src="https://github.com/user-attachments/assets/429f5b15-7bbf-41e7-a197-f92d5ce8c940" />


PDV analysis of the WIP shows that DoS and MITM attacks cause significant PDV at Flow ID 1, unlike NORMAL and DDoS scenarios. The BH attack results in minimal PDV, which stabilizes across flow IDs, while DDoS has no significant effect. For the SHS, the NORMAL network shows minimal PDV, indicating optimal performance. DoS causes the highest PDV (0.6 seconds) at Flow ID 1, disrupting the network, while DDoS and MITM induce moderate PDV (0.3 seconds), with MITM recovering quickly. BH exhibits minimal PDV, similar to NORMAL conditions.

<img width="311" height="197" alt="image" src="https://github.com/user-attachments/assets/d37655f2-d958-49ed-8fe3-728899fdfc09" />


### Packet Loss
A detailed packet loss analysis was performed in all scenarios, as shown on the projected graph in Fig. 9.

<img width="367" height="223" alt="image" src="https://github.com/user-attachments/assets/a7668af1-9a00-452c-a6a9-65cdb020358f" />

On the WIP, analysis shows that the MITM attack causes total packet loss and network failure, while DoS and BH attacks result in no packet loss, demonstrating resilience to these threats. Similarly, the SHS does not show packet loss under DoS, DDoS, and BH attacks, indicating robust performance. However, the MITM attack leads to packet loss 100\% in Flow ID 1, revealing a critical vulnerability and highlighting the need for enhanced security against MITM attacks. 

TABLE III and TABLE IV (https://zenodo.org/records/16810649) both summarize the collection of all the key metric values that have been extracted from the CSV files, of all simulated scenarios on both targeted devices as nodes in the IoMT network respectively.

## Bluetooth Energy Consumption for Hexoskin SHS
The Bluetooth energy consumption logs for the Hexoskin SHS remained constant at 2.580 joules across
NORMAL, MITM, and MQTT scenarios (as highlighted in Tables 6). Despite observed performance
degradations, these attacks did not increase energy usage on the device’s wireless module. This highlights
that energy alone is insufficient to detect attacks in resource-constrained IoMT devices, underscoring the
need for multi-metric anomaly detection combining traffic, timing, and integrity measures.

## Statistical Validation
To ensure a rigorous and reproducible evaluation of IoMT network scenarios, statistical validation was
performed using data from 540 network flows (60 seeds, 10 simulations each producing 9 flows per
scenario). The aim was to assess how key metrics—throughput, OWD, PDV, and packet loss—respond
to various attack conditions. One-way ANOVA identified overall metric variance, and Tukey’s HSD
pinpointed which scenario pairs had significant differences, ensuring that observed degradations were not
random variations but were attributed to specific network attack behaviours based on statistical confidence.
ANOVA results showed no significant variation in throughput (F = 0.55, p = 0.739), but significant differences for OWD (p = 0.015), PDV (p < 2.17×10), and packet loss (p < 6.33×10). Tukey’s HSD results revealed five significant pairwise differences each for PDV and packet loss, and one for OWD. For instance, MITM attacks caused 11.50% packet loss versus 1.86% under BH (p = 0.000), and a significant drop in PDV compared to NORMAL. These results, backed by consistent simulation sets, standardized data collection, and strong statistical indicators, highlight MITM as the most severe attack that severely impacts packet integrity and timing consistency. Packet loss and PDV emerge as reliable indicators for detecting real-time threats, supporting flow-level monitoring for IoMT network security frameworks.

## Performance Integrity Benchmarking against Clinical Thresholds
A benchmarking process was employed to evaluate the statistical performance results by comparing them
against thresholds derived from the NORMAL scenario, which represents clinically validated, acceptable
network behavior. These thresholds were based on the mean values from simulated baseline datasets, with
throughput set to a ± 10% tolerance and OWD, PDV, and packet loss capped at 110% of their baseline
values—reflecting ISO/IEEE 11073 standards for clinical safety.
This framework ensures compliance with ISO 11073 interoperable medical communication protocols, particularly for time-sensitive applications. A Python-based ISO benchmarking script (shown
in Listing 1.14 ) applied these thresholds to assess each metric under different attack scenarios for both
the Baxter WIP and Hexoskin SHS, using ✓(’compliant’) and ✗(’non-comformant’) indicators to denote
compliance or violation. This approach systematically identifies threats that compromise clinical safety and
interoperability in IoMT networks. Figure below and Table in Appendix summarizes these clinical threshold applications
against the metrics results of all the simulated IoMT network scenarios.

<img width="1000" height="600" alt="image" src="https://github.com/user-attachments/assets/305219e6-021e-4710-8455-bdcb930e6493" />


## Overall Patterns
Among all attack scenarios evaluated, the MITM attack posed the most critical threat to both the Baxter
WIP and the Hexoskin SHS. Statistically significant results (mean packet loss = 11.50%, p < 0.0001)
highlight its severe impact, with marked increases in packet delay variation (PDV) and one-way delay
Fig. 8. Heatmap of defined ISO 11073-compliant IoMT Benchmarks with Clinical Thresholds
(OWD). These impairments undermine the reliability of real-time data exchange in IoMT systems, risking
misinterpretation of patient vitals and incorrect actuation, such as improper drug dosages or altered
sensor readings.
However, despite achieving these results, there are notable limitations that prevented these NS-3
simulations from replicating fully realistic IoMT scenarios, such as lack of native support of Bluetooth
Low Energy (BLE) and MQTT traffic that led to abstract network designs of these features (outlined in
Table 3).
Given the sensitivity of PDV and packet loss to such disruptions, mitigation should focus on preserving
timing precision and data integrity. Techniques like Deep Packet Inspection (DPI) enhance payload-level
threat detection but may increase OWD due to processing delays. Network Behavior Analysis (NBA)
and Anomaly Detection (NAD) offer adaptive protection with minimal throughput impact, albeit
with slight packet variations. Network Detection and Response (NDR) improves packet loss resilience via
rapid threat containment. Encryption and encapsulation reduce tampering risks but may marginally affect
PDV. Federated Learning (FL) enables decentralized anomaly detection with low resource overhead and
preserves both latency and throughput. Integrated deployment of these methods can enhance
IoMT security while maintaining system performance and safety.

## Conclusion
This study evaluates the impact of various attacks on the performance of the IoMT network and devices
using NS-3, highlighting the severe vulnerabilities of MITM attacks. However, some features lacking
native support from NS-3 highlights notable limitations in simulating absolutely realistic IoMT scenarios.
The MITM attack results in complete packet loss and network failure, while DoS, DDoS, and BH attacks
lead to delays and reduced throughput. Although blockchain-based authentication enhances security, its
complexity, high energy consumption, and limited scalability challenge resource-constrained IoMT devices.
Despite these disruptions, Bluetooth energy consumption remained unchanged across NORMAL, MITM,
and MQTT scenarios (2.580 J), suggesting that such attacks do not impose additional energy burdens
on the SHS device communication module. This reinforces the importance of using timing and integrity
metrics—rather than energy usage alone—for detecting stealthy threats in IoMT environments. Future
work should explore integrating energy-aware anomaly detection with traffic behavior analysis to enhance
anomaly detection accuracy without compromising device efficiency. This comprises focusing on testing
alternate preventive solutions like DPI, NBA, NAD and mitigation techniques such as NDR, improved
packet cleaning, encapsulation, improved encryption and FL to strengthen cybersecurity and resilience in
healthcare networks.
