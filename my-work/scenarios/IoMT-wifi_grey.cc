/*
 * IoMT-wifi_grey.cc
 * ---------------------------------------------------------------------------
 * Grey-hole (selective forwarding) attack on the IoMT Wi-Fi network.
 *
 * An on-path relay node receives the high-priority infusion-pump control
 * traffic and forwards each packet to the real pump only with probability
 * (1 - p), silently dropping it with probability p. Unlike a blackhole
 * (p = 1, drops everything and is obvious), a grey-hole with 0 < p < 1 leaks
 * only partial loss that resembles ordinary wireless degradation -> stealthy.
 *
 *   p = 0.0  -> behaves like the normal baseline (no loss)
 *   p = 1.0  -> a working blackhole (target flow fully denied)
 *
 * Note on measurement: the drop happens at the relay application, so the
 * survivors' hop (relay -> pump) shows no L3 "lostPackets"; the attack instead
 * shows up as a THROUGHPUT / rxPackets deficit on the pump-delivery flow.
 * End-to-end loss = 1 - (pump rxPackets / control txPackets).
 *
 * Parameters:
 *   --p       drop probability (attack intensity knob), 0.0 .. 1.0
 *   --run     RNG run number for an independent replication (seed)
 *   --output  output FlowMonitor XML prefix (without .xml)
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

NS_LOG_COMPONENT_DEFINE("IoMTGreyHole");

// ---------------------------------------------------------------------------
// Grey-hole relay application: forwards each received packet to a fixed
// destination with probability (1 - dropProb); drops it otherwise. Models a
// compromised on-path gateway performing selective forwarding.
// ---------------------------------------------------------------------------
class GreyholeRelay : public Application
{
  public:
    // listenPort : UDP port this relay receives redirected victim traffic on
    // forwardTo   : real destination (pump address:port) survivors are sent to
    // dropProb    : p, probability each packet is dropped
    void Setup(uint16_t listenPort, Address forwardTo, double dropProb);
    uint64_t GetForwarded() const { return m_forwarded; }
    uint64_t GetDropped() const { return m_dropped; }

  private:
    void StartApplication() override;
    void StopApplication() override;
    void HandleRead(Ptr<Socket> socket);

    Ptr<Socket> m_rxSocket;                 // receives the victim's traffic
    Ptr<Socket> m_txSocket;                 // forwards survivors to the pump
    uint16_t m_listenPort = 0;
    Address m_forwardTo;
    double m_dropProb = 0.0;
    Ptr<UniformRandomVariable> m_rng;       // drop decision (uses the RNG stream)
    uint64_t m_forwarded = 0;
    uint64_t m_dropped = 0;
};

void
GreyholeRelay::Setup(uint16_t listenPort, Address forwardTo, double dropProb)
{
    m_listenPort = listenPort;
    m_forwardTo = forwardTo;
    m_dropProb = dropProb;
}

void
GreyholeRelay::StartApplication()
{
    m_rng = CreateObject<UniformRandomVariable>();

    // Receive the control traffic redirected to this (attacker) node.
    m_rxSocket = Socket::CreateSocket(GetNode(), UdpSocketFactory::GetTypeId());
    m_rxSocket->Bind(InetSocketAddress(Ipv4Address::GetAny(), m_listenPort));
    m_rxSocket->SetRecvCallback(MakeCallback(&GreyholeRelay::HandleRead, this));

    // Socket used to forward survivors to the real pump.
    m_txSocket = Socket::CreateSocket(GetNode(), UdpSocketFactory::GetTypeId());
    m_txSocket->Connect(m_forwardTo);
}

void
GreyholeRelay::StopApplication()
{
    if (m_rxSocket)
    {
        m_rxSocket->Close();
    }
    if (m_txSocket)
    {
        m_txSocket->Close();
    }
}

void
GreyholeRelay::HandleRead(Ptr<Socket> socket)
{
    Ptr<Packet> packet;
    Address from;
    while ((packet = socket->RecvFrom(from)))
    {
        // Selective forwarding: drop with probability p, otherwise forward.
        if (m_rng->GetValue() < m_dropProb)
        {
            m_dropped++;
            continue;
        }
        // Forward a fresh packet of the same size. Re-sending the received
        // object would carry its FlowMonitor tag and mis-classify the hop.
        Ptr<Packet> fresh = Create<Packet>(packet->GetSize());
        m_txSocket->Send(fresh);
        m_forwarded++;
    }
}

int
main(int argc, char* argv[])
{
    double simulationTime = 30.0; // seconds (match the NORMAL baseline)

    // --- CLI parameters: intensity (p), RNG run (seed), output filename ------
    double dropProb = 0.0;                          // p: attack intensity knob
    uint32_t rngRun = 1;                            // independent replication (seed)
    std::string output = "flowmonitor-stats_grey";  // output XML prefix (no ext.)
    CommandLine cmd;
    cmd.AddValue("p", "Grey-hole drop probability (0.0 = none, 1.0 = blackhole)", dropProb);
    cmd.AddValue("run", "RNG run number for an independent replication (seed)", rngRun);
    cmd.AddValue("output", "Output filename prefix, without .xml", output);
    cmd.Parse(argc, argv);

    RngSeedManager::SetSeed(1);     // fixed base seed
    RngSeedManager::SetRun(rngRun); // independent random stream per run

    // --- Nodes ---------------------------------------------------------------
    uint32_t numNodes = 9; // 9 Wi-Fi STAs
    NodeContainer wifiNodes;
    wifiNodes.Create(numNodes);
    NodeContainer wifiApNode;
    wifiApNode.Create(1);
    NodeContainer hexoskinNodes;
    hexoskinNodes.Create(1);

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
    mac.SetType("ns3::ApWifiMac", "Ssid", SsidValue(ssid));
    NetDeviceContainer apDevice = wifi.Install(phy, mac, wifiApNode);

    // --- Internet stack + addressing -----------------------------------------
    InternetStackHelper stack;
    stack.Install(wifiNodes);
    stack.Install(wifiApNode);
    stack.Install(hexoskinNodes);

    Ipv4AddressHelper address;
    address.SetBase("192.168.1.0", "255.255.255.0");
    Ipv4InterfaceContainer wifiInterfaces = address.Assign(wifiDevices);
    Ipv4InterfaceContainer apInterface = address.Assign(apDevice);

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

    // --- Hexoskin Bluetooth emulation (P2P) — untouched victim contrast ------
    PointToPointHelper p2p;
    p2p.SetDeviceAttribute("DataRate", StringValue("3Mbps"));
    p2p.SetChannelAttribute("Delay", StringValue("2ms"));
    NetDeviceContainer p2pDevices = p2p.Install(wifiNodes.Get(1), hexoskinNodes.Get(0));
    Ipv4AddressHelper p2pAddress;
    p2pAddress.SetBase("10.1.1.0", "255.255.255.0");
    Ipv4InterfaceContainer p2pInterfaces = p2pAddress.Assign(p2pDevices);

    // --- Node roles ----------------------------------------------------------
    uint16_t pumpPort = 8080;  // real infusion-pump sink port
    uint16_t relayPort = 7070; // port the grey-hole relay listens on
    Address pumpAddress(InetSocketAddress(wifiInterfaces.GetAddress(0), pumpPort));   // STA 0
    Address relayAddress(InetSocketAddress(wifiInterfaces.GetAddress(8), relayPort)); // STA 8 attacker

    // Real pump sink on STA 0.
    PacketSinkHelper pumpSink("ns3::UdpSocketFactory", pumpAddress);
    ApplicationContainer pumpApp = pumpSink.Install(wifiNodes.Get(0));
    pumpApp.Start(Seconds(1.0));
    pumpApp.Stop(Seconds(simulationTime));

    // High-priority control traffic (STA 2) — now aimed at the ATTACKER relay.
    OnOffHelper controlTraffic("ns3::UdpSocketFactory", relayAddress);
    controlTraffic.SetAttribute("DataRate", StringValue("1Mbps"));
    controlTraffic.SetAttribute("PacketSize", UintegerValue(512));
    ApplicationContainer controlApp = controlTraffic.Install(wifiNodes.Get(2));
    controlApp.Start(Seconds(2.0));
    controlApp.Stop(Seconds(20.0));

    // Grey-hole relay on STA 8: forward survivors to the real pump with prob (1-p).
    Ptr<GreyholeRelay> relay = CreateObject<GreyholeRelay>();
    relay->Setup(relayPort, pumpAddress, dropProb);
    wifiNodes.Get(8)->AddApplication(relay);
    relay->SetStartTime(Seconds(1.0));
    relay->SetStopTime(Seconds(simulationTime));

    // Untouched low-priority telemetry (Hexoskin -> smartphone STA 1).
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

    Ipv4GlobalRoutingHelper::PopulateRoutingTables();

    // --- Measurement ---------------------------------------------------------
    FlowMonitorHelper flowmon;
    Ptr<FlowMonitor> monitor = flowmon.InstallAll();

    Simulator::Stop(Seconds(simulationTime));
    Simulator::Run();
    monitor->CheckForLostPackets();
    monitor->SerializeToXmlFile(output + ".xml", true, true);

    std::cout << "Grey-hole relay: forwarded=" << relay->GetForwarded()
              << " dropped=" << relay->GetDropped() << " (p=" << dropProb << ")" << std::endl;

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
