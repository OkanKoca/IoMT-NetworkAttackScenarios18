/*
 * IoMT-wifi_ddos.cc
 * ---------------------------------------------------------------------------
 * Distributed Denial-of-Service (DDoS) on the IoMT Wi-Fi network.
 *
 * Several attacker stations flood the infusion pump simultaneously, exhausting
 * the shared Wi-Fi medium so the legitimate control/telemetry flows degrade.
 * It differs from single-source DoS by the NUMBER of concurrent flooders
 * (--nattackers), which is its intensity knob and its structural signature
 * (many high-volume flows instead of one).
 *
 * Fixes vs the study's version (verified broken in docs/07): the attacker
 * nodes there received an IP stack but NO Wi-Fi device and no address, so they
 * were interfaceless and sent nothing. Here they are real associated stations.
 *
 * Parameters:
 *   --nattackers  number of concurrent flooders (intensity knob)
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

using namespace ns3;

NS_LOG_COMPONENT_DEFINE("IoMTDDoS");

int
main(int argc, char* argv[])
{
    double simulationTime = 30.0; // seconds (matches the NORMAL/DoS/grey baseline)

    // --- CLI parameters ------------------------------------------------------
    uint32_t nAttackers = 5;                         // intensity knob
    uint32_t rngRun = 1;                             // independent replication (seed)
    std::string output = "flowmonitor-stats_ddos";   // output XML prefix (no ext.)
    CommandLine cmd;
    cmd.AddValue("nattackers", "Number of concurrent DDoS flooders (intensity)", nAttackers);
    cmd.AddValue("run", "RNG run number for an independent replication (seed)", rngRun);
    cmd.AddValue("output", "Output filename prefix, without .xml", output);
    cmd.Parse(argc, argv);

    RngSeedManager::SetSeed(1);
    RngSeedManager::SetRun(rngRun);

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
    uint16_t pumpPort = 8080;
    Address pumpAddress(InetSocketAddress(wifiInterfaces.GetAddress(0), pumpPort)); // STA 0
    PacketSinkHelper pumpSink("ns3::UdpSocketFactory", pumpAddress);
    ApplicationContainer pumpApp = pumpSink.Install(wifiNodes.Get(0));
    pumpApp.Start(Seconds(1.0));
    pumpApp.Stop(Seconds(20.0));

    OnOffHelper controlTraffic("ns3::UdpSocketFactory", pumpAddress);
    controlTraffic.SetAttribute("DataRate", StringValue("1Mbps"));
    controlTraffic.SetAttribute("PacketSize", UintegerValue(512));
    ApplicationContainer controlApp = controlTraffic.Install(wifiNodes.Get(2));
    controlApp.Start(Seconds(2.0));
    controlApp.Stop(Seconds(20.0));

    uint16_t smartphonePort = 9090;
    Address smartphoneAddress(InetSocketAddress(wifiInterfaces.GetAddress(1), smartphonePort));
    PacketSinkHelper smartphoneSink("ns3::UdpSocketFactory", smartphoneAddress);
    ApplicationContainer smartphoneApp = smartphoneSink.Install(wifiNodes.Get(1));
    smartphoneApp.Start(Seconds(2.0));
    smartphoneApp.Stop(Seconds(20.0));
    OnOffHelper smartphoneTraffic("ns3::UdpSocketFactory", smartphoneAddress);
    smartphoneTraffic.SetAttribute("DataRate", StringValue("512Kbps"));
    smartphoneTraffic.SetAttribute("PacketSize", UintegerValue(256));
    ApplicationContainer smartphoneTrafficApp = smartphoneTraffic.Install(hexoskinNodes.Get(0));
    smartphoneTrafficApp.Start(Seconds(3.0));
    smartphoneTrafficApp.Stop(Seconds(20.0));

    // --- DDoS: each attacker floods the pump's host, saturating the medium ---
    Ipv4Address targetAddress = wifiInterfaces.GetAddress(0); // pump host (STA 0)
    for (uint32_t i = 0; i < nAttackers; ++i)
    {
        UdpEchoClientHelper attackClient(targetAddress, 9); // flood target port 9
        attackClient.SetAttribute("MaxPackets", UintegerValue(1000000));
        attackClient.SetAttribute("Interval", TimeValue(Seconds(0.01))); // 100 pkt/s each
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
