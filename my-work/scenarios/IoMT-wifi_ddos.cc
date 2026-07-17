/*
 * IoMT-wifi_ddos.cc
 * ---------------------------------------------------------------------------
 * Distributed Denial-of-Service (DDoS) on the IoMT Wi-Fi network.
 *
 * Several attacker stations flood the patient monitor simultaneously, exhausting
 * the shared Wi-Fi medium so the legitimate control/telemetry flows degrade.
 * It differs from single-source DoS by the NUMBER of concurrent flooders
 * (--nattackers), which is its structural signature (many flood flows instead
 * of one). Per-attacker flood rate (--rate) is an independent knob: together
 * they span an (attacker-count x rate) plane, so a k-attacker DDoS can be given
 * the same TOTAL volume as a single-source DoS while differing in flow count —
 * i.e. the true DoS/DDoS separator is the number of flooding flows, not volume.
 *
 * Fixes vs the study's version (verified broken): the attacker nodes there
 * received an IP stack but NO Wi-Fi device and no address, so they were
 * interfaceless and sent nothing. Here they are real associated stations.
 *
 * Parameters:
 *   --nattackers  number of concurrent flooders (structural knob)
 *   --rate        per-attacker flood rate in pkt/s (volume knob; default 100)
 *   --run         RNG run number for an independent replication (seed)
 *   --output      output FlowMonitor XML prefix (without .xml)
 * ---------------------------------------------------------------------------
 */

#include "ns3/core-module.h"
#include "ns3/network-module.h"
#include "ns3/wifi-module.h"
#include "ns3/internet-module.h"
#include "ns3/applications-module.h"
#include "ns3/mobility-module.h"
#include "ns3/point-to-point-module.h"
#include "ns3/flow-monitor-module.h"

#include "iomt-noise.h"

using namespace ns3;

NS_LOG_COMPONENT_DEFINE("IoMTDDoS");

int
main(int argc, char* argv[])
{
    double simulationTime = 30.0; // seconds (matches the NORMAL/DoS/grey baseline)

    // --- CLI parameters ------------------------------------------------------
    uint32_t nAttackers = 5;                         // structural knob (flood-flow count)
    uint32_t floodRate = 100;                        // per-attacker flood rate (pkt/s); volume knob
    uint32_t rngRun = 1;                             // independent replication (seed)
    std::string output = "flowmonitor-stats_ddos";   // output XML prefix (no ext.)
    // The ward's congestion driver; calibrated in iomt-noise.h (docs/18).
    double heavyMbps = IOMT_HEAVY_MBPS;
    double heavySpread = IOMT_HEAVY_SPREAD; // 0 = exactly heavyMbps (calibration)
    CommandLine cmd;
    cmd.AddValue("nattackers", "Number of concurrent DDoS flooders (structural knob)", nAttackers);
    cmd.AddValue("rate", "Per-attacker flood rate in pkt/s (volume knob)", floodRate);
    cmd.AddValue("run", "RNG run number for an independent replication (seed)", rngRun);
    cmd.AddValue("output", "Output filename prefix, without .xml", output);
    cmd.AddValue("heavy", "Imaging/video gateway offered load in Mbps (0 = off)", heavyMbps);
    cmd.AddValue("heavyspread", "Per-run fractional spread of the imaging rate", heavySpread);
    cmd.Parse(argc, argv);

    RngSeedManager::SetSeed(1);
    RngSeedManager::SetRun(rngRun);

    // Before any Wi-Fi device exists: small, embedded-sized MAC queues.
    LimitMacQueue();

    // --- Nodes ---------------------------------------------------------------
    uint32_t numNodes = 9; // 9 legitimate Wi-Fi STAs
    NodeContainer wifiNodes;
    wifiNodes.Create(numNodes);
    NodeContainer wifiApNode;
    wifiApNode.Create(1);
    NodeContainer hexoskinNodes;
    hexoskinNodes.Create(1);
    NodeContainer attackerNodes;
    attackerNodes.Create(nAttackers);

    // --- Wi-Fi PHY / MAC -----------------------------------------------------
    YansWifiChannelHelper channel = YansWifiChannelHelper::Default();
    AddChannelFading(channel); // per-run Nakagami fading on top of log-distance
    YansWifiPhyHelper phy;
    phy.SetChannel(channel.Create());

    WifiHelper wifi;
    wifi.SetStandard(WIFI_STANDARD_80211n);
    wifi.SetRemoteStationManager("ns3::MinstrelHtWifiManager");

    WifiMacHelper mac;
    Ssid ssid = Ssid("HealthNet_24G");
    mac.SetType("ns3::StaWifiMac", "Ssid", SsidValue(ssid), "ActiveProbing", BooleanValue(false));
    NetDeviceContainer wifiDevices = wifi.Install(phy, mac, wifiNodes);
    // FIX: give the attackers a real Wi-Fi device as associated stations.
    NetDeviceContainer attackerDevices = wifi.Install(phy, mac, attackerNodes);
    mac.SetType("ns3::ApWifiMac", "Ssid", SsidValue(ssid));
    NetDeviceContainer apDevice = wifi.Install(phy, mac, wifiApNode);

    // Per-run random packet loss on the legitimate receivers (STAs + AP): a real
    // noise floor so baseline delivery is not deterministically 1.0.
    AddReceiveNoise(wifiDevices);
    AddReceiveNoise(apDevice);

    // --- Internet stack + addressing -----------------------------------------
    InternetStackHelper stack;
    stack.Install(wifiNodes);
    stack.Install(wifiApNode);
    stack.Install(hexoskinNodes);
    stack.Install(attackerNodes);

    Ipv4AddressHelper address;
    address.SetBase("192.168.1.0", "255.255.255.0");
    Ipv4InterfaceContainer wifiInterfaces = address.Assign(wifiDevices);
    Ipv4InterfaceContainer apInterface = address.Assign(apDevice);
    // FIX: assign the attackers IP addresses so they can actually transmit.
    Ipv4InterfaceContainer attackerInterfaces = address.Assign(attackerDevices);

    // --- Mobility (all fixed) ------------------------------------------------
    MobilityHelper mobility;
    mobility.SetPositionAllocator("ns3::GridPositionAllocator",
                                  "MinX", DoubleValue(0.0), "MinY", DoubleValue(0.0),
                                  "DeltaX", DoubleValue(10.0), "DeltaY", DoubleValue(10.0),
                                  "GridWidth", UintegerValue(5),
                                  "LayoutType", StringValue("RowFirst"));
    mobility.SetMobilityModel("ns3::ConstantPositionMobilityModel");
    mobility.Install(wifiNodes);
    JitterPositions(wifiNodes); // small per-run position offset
    Ptr<ListPositionAllocator> apPosition = CreateObject<ListPositionAllocator>();
    apPosition->Add(Vector(0.0, 0.0, 0.0));
    mobility.SetPositionAllocator(apPosition);
    mobility.Install(wifiApNode);
    mobility.Install(hexoskinNodes);
    // Attackers on their own fixed grid, offset from the legitimate stations.
    mobility.SetPositionAllocator("ns3::GridPositionAllocator",
                                  "MinX", DoubleValue(5.0), "MinY", DoubleValue(30.0),
                                  "DeltaX", DoubleValue(5.0), "DeltaY", DoubleValue(5.0),
                                  "GridWidth", UintegerValue(5),
                                  "LayoutType", StringValue("RowFirst"));
    mobility.Install(attackerNodes);

    // --- Hexoskin Bluetooth emulation (P2P) — untouched victim contrast ------
    PointToPointHelper p2p;
    p2p.SetDeviceAttribute("DataRate", StringValue("3Mbps"));
    p2p.SetChannelAttribute("Delay", StringValue("2ms"));
    NetDeviceContainer p2pDevices = p2p.Install(wifiNodes.Get(1), hexoskinNodes.Get(0));
    Ipv4AddressHelper p2pAddress;
    p2pAddress.SetBase("10.1.1.0", "255.255.255.0");
    Ipv4InterfaceContainer p2pInterfaces = p2pAddress.Assign(p2pDevices);

    // --- Legitimate traffic (same windows as the baseline) -------------------
    uint16_t monitorPort = 8080;
    Address monitorAddress(InetSocketAddress(wifiInterfaces.GetAddress(0), monitorPort)); // STA 0
    PacketSinkHelper monitorSink("ns3::UdpSocketFactory", monitorAddress);
    ApplicationContainer monitorApp = monitorSink.Install(wifiNodes.Get(0));
    monitorApp.Start(Seconds(1.0));
    monitorApp.Stop(Seconds(20.0));

    OnOffHelper ecgTraffic("ns3::UdpSocketFactory", monitorAddress);
    // Patient-monitor ECG waveform: the real clinical profile is a low bit rate
    // carried by many small packets (see IoMT-wifi_wip.cc for the full rationale).
    SetNoisyOnOff(ecgTraffic, 128e3, 128); // per-run randomized rate/size/burst
    ApplicationContainer ecgApp = ecgTraffic.Install(wifiNodes.Get(2));
    ecgApp.Start(Seconds(2.0));
    ecgApp.Stop(Seconds(20.0));

    uint16_t smartphonePort = 9090;
    Address smartphoneAddress(InetSocketAddress(wifiInterfaces.GetAddress(1), smartphonePort));
    PacketSinkHelper smartphoneSink("ns3::UdpSocketFactory", smartphoneAddress);
    ApplicationContainer smartphoneApp = smartphoneSink.Install(wifiNodes.Get(1));
    smartphoneApp.Start(Seconds(2.0));
    smartphoneApp.Stop(Seconds(20.0));
    OnOffHelper smartphoneTraffic("ns3::UdpSocketFactory", smartphoneAddress);
    SetNoisyOnOff(smartphoneTraffic, 64e3, 128); // per-run randomized rate/size/burst
    ApplicationContainer smartphoneTrafficApp = smartphoneTraffic.Install(hexoskinNodes.Get(0));
    smartphoneTrafficApp.Start(Seconds(3.0));
    smartphoneTrafficApp.Stop(Seconds(20.0));

    // The rest of the ward: a random subset of the light medical devices plus the
    // always-on imaging gateway (see iomt-noise.h for why that split matters).
    InstallMedicalCrossTraffic(wifiNodes, wifiInterfaces, 2.0, 20.0, heavyMbps, heavySpread);

    // --- DDoS: each attacker floods the monitor's host, saturating the medium ---
    Ipv4Address targetAddress = wifiInterfaces.GetAddress(0); // monitor host (STA 0)
    for (uint32_t i = 0; i < nAttackers; ++i)
    {
        UdpEchoClientHelper attackClient(targetAddress, 9); // flood target port 9
        attackClient.SetAttribute("MaxPackets", UintegerValue(1000000));
        attackClient.SetAttribute("Interval", TimeValue(Seconds(1.0 / floodRate))); // per-attacker flood rate (pkt/s)
        attackClient.SetAttribute("PacketSize", UintegerValue(1024));
        ApplicationContainer attackApp = attackClient.Install(attackerNodes.Get(i));
        attackApp.Start(Seconds(1.0));
        attackApp.Stop(Seconds(simulationTime));
    }

    Ipv4GlobalRoutingHelper::PopulateRoutingTables();

    // --- Measurement ---------------------------------------------------------
    FlowMonitorHelper flowmon;
    Ptr<FlowMonitor> monitor = flowmon.InstallAll();

    Simulator::Stop(Seconds(simulationTime));
    Simulator::Run();
    monitor->CheckForLostPackets();
    monitor->SerializeToXmlFile(output + ".xml", true, true);

    std::cout << "DDoS: nAttackers=" << nAttackers << " run=" << rngRun << std::endl;
    std::map<FlowId, FlowMonitor::FlowStats> stats = monitor->GetFlowStats();
    for (auto it = stats.begin(); it != stats.end(); ++it)
    {
        std::cout << "Flow ID: " << it->first << "  Tx: " << it->second.txPackets
                  << "  Rx: " << it->second.rxPackets << "  Lost: " << it->second.lostPackets
                  << std::endl;
    }

    Simulator::Destroy();
    return 0;
}
