# Assessing IoMT Network Resilience: A Comparative Performance Analysis of Simulated Attacks using NS-3
This study simulates four attack scenarios—DoS, DDoS (UDP Flooding), MITM, Blackhole and MQTT DoS (Command Injection)—on an IoMT network using NS-3.
In a controlled sandbox environment, it evaluates the network Throughput, One-Way Delay
(OWD), Packet Delay Variation (PDV), and Packet loss for a Baxter WIP and a Hexoskin SHS. Graphical results illustrate network degradation under
attacks. The findings identify network vulnerabilities and propose controls to both enhance IoMT
security and resilience and ensure safety in patient care.

# Research Experiment Design
This study design simulates a wireless IoMT network using the WLAN 802.11 protocol, comprising a Wireless Access Point, Baxter Wireless Infusion Pump (WIP), and Hexoskin Smart Health Shirt (SHS). The setup replicates a real-world patient-centric environment for integrated healthcare devices. The aim is to establish security controls for healthcare institutions, leveraging insights from the OpenICE interoperability platform supporting real-time cardiac and cognitive monitoring, as shown in the Figure below.

![image](https://github.com/user-attachments/assets/e6eecd62-8dcf-4f85-83b6-496c2500cb5f)

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


## Overall Patterns
The analysis identifies critical vulnerabilities in Baxter WIP and Hexoskin SHS to MITM attacks, leading to packet loss, performance degradation, and network disruption. WIP experiences high PDV under MITM and DoS, while SHS suffers disruptions from DoS/DDoS. Unlike other attacks, MITM poses the highest risk, potentially compromising patient safety by altering drug dosages and device readings.

Robust security is essential to prevent data manipulation. While blockchain authentication enhances security, its complexity and energy demands make it unsuitable for resource-limited IoMT devices. Alternative preventative solutions -Deep Packet Inspection (DPI), Network Behavioral Analysis (NBA), Network Anomaly Detection (NAD), Network Detection and Respeonse (NDR), - and improved packet cleansing, encapsulation, and encryption for mitigation, should be explored for resilient IoMT security in healthcare.
