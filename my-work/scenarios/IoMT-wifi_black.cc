/*
 * IoMT-wifi_black.cc
 * ---------------------------------------------------------------------------
 * Blackhole attack on the IoMT Wi-Fi network.
 *
 * An on-path relay node attracts the patient monitor's ECG waveform and drops
 * EVERY packet, forwarding nothing to the real monitor (total denial of the
 * control path). It is the "loud" sibling of the stealthy grey-hole: behaviour
 * is identical to grey-hole at p = 1 (delivery_ratio -> 0), reproduced here as
 * a standalone scenario for faithfulness to the study's attack roster.
 *
 * Fix vs the study's version (verified broken in docs/07): there the attacker
 * had no Wi-Fi device (its callback sat on the loopback) and the drop filter
 * compared an L2 address to an InetSocketAddress, so it never matched and
 * dropped nothing. Here the drop happens at a genuine on-path relay app.
 *
 * Parameters:
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

#include "iomt-timing.h"      // end-to-end delay below the flow layer
#include "iomt-noise.h"

using namespace ns3;

NS_LOG_COMPONENT_DEFINE("IoMTBlackhole");

// On-path relay that receives the victim's traffic and drops all of it.
class BlackholeRelay : public Application
{
  public:
    void Setup(uint16_t listenPort) { m_listenPort = listenPort; }
    uint64_t GetDropped() const { return m_dropped; }

  private:
    void StartApplication() override
    {
        m_rxSocket = Socket::CreateSocket(GetNode(), UdpSocketFactory::GetTypeId());
        m_rxSocket->Bind(InetSocketAddress(Ipv4Address::GetAny(), m_listenPort));
        m_rxSocket->SetRecvCallback(MakeCallback(&BlackholeRelay::HandleRead, this));
    }
    void StopApplication() override
    {
        if (m_rxSocket)
        {
            m_rxSocket->Close();
        }
    }
    void HandleRead(Ptr<Socket> socket)
    {
        Ptr<Packet> packet;
        Address from;
        while ((packet = socket->RecvFrom(from)))
        {
            m_dropped++; // received, then silently discarded (never forwarded)
        }
    }

    Ptr<Socket> m_rxSocket;
    uint16_t m_listenPort = 0;
    uint64_t m_dropped = 0;
};

int
main(int argc, char* argv[])
{
    double simulationTime = 30.0; // seconds (matches the NORMAL/DoS/grey baseline)

    uint32_t rngRun = 1;
    std::string output = "flowmonitor-stats_black";
    // The ward's congestion driver; calibrated in iomt-noise.h (docs/18).
    double heavyMbps = IOMT_HEAVY_MBPS;
    double heavySpread = IOMT_HEAVY_SPREAD; // 0 = exactly heavyMbps (calibration)
    CommandLine cmd;
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
    uint32_t numNodes = 9;
    NodeContainer wifiNodes;
    wifiNodes.Create(numNodes);
    NodeContainer wifiApNode;
    wifiApNode.Create(1);
    NodeContainer hexoskinNodes;
    hexoskinNodes.Create(1);

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
    JitterPositions(wifiNodes); // small per-run position offset
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
    uint16_t monitorPort = 8080;
    uint16_t relayPort = 7070;
    Address monitorAddress(InetSocketAddress(wifiInterfaces.GetAddress(0), monitorPort));   // STA 0
    Address relayAddress(InetSocketAddress(wifiInterfaces.GetAddress(8), relayPort)); // STA 8 attacker

    // Real patient-monitor sink on STA 0.(receives nothing under attack).
    PacketSinkHelper monitorSink("ns3::UdpSocketFactory", monitorAddress);
    EnableVictimTiming(monitorSink);
    ApplicationContainer monitorApp = monitorSink.Install(wifiNodes.Get(0));
    E2eDelay e2e;
    AttachTiming(monitorApp, e2e);
    monitorApp.Start(Seconds(1.0));
    monitorApp.Stop(Seconds(simulationTime));

    // Control traffic (STA 2) aimed at the attacker relay.
    OnOffHelper ecgTraffic("ns3::UdpSocketFactory", relayAddress);
    // Patient-monitor ECG waveform: the real clinical profile is a low bit rate
    // carried by many small packets (see IoMT-wifi_wip.cc for the full rationale).
    SetNoisyOnOff(ecgTraffic, 128e3, 128, 0.2, TimingHeaderBytes()); // per-run randomized
    EnableVictimTiming(ecgTraffic);
    ApplicationContainer ecgApp = ecgTraffic.Install(wifiNodes.Get(2));
    ecgApp.Start(Seconds(2.0));
    ecgApp.Stop(Seconds(20.0));

    // Blackhole relay on STA 8: drops everything.
    Ptr<BlackholeRelay> relay = CreateObject<BlackholeRelay>();
    relay->Setup(relayPort);
    wifiNodes.Get(8)->AddApplication(relay);
    relay->SetStartTime(Seconds(1.0));
    relay->SetStopTime(Seconds(simulationTime));

    // Untouched telemetry (Hexoskin -> smartphone STA 1).
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

    Ipv4GlobalRoutingHelper::PopulateRoutingTables();

    // --- Measurement ---------------------------------------------------------
    FlowMonitorHelper flowmon;
    Ptr<FlowMonitor> monitor = flowmon.InstallAll();

    Simulator::Stop(Seconds(simulationTime));
    Simulator::Run();
    ReportTiming(e2e);
    monitor->CheckForLostPackets();
    monitor->SerializeToXmlFile(output + ".xml", true, true);

    std::cout << "Blackhole relay: dropped=" << relay->GetDropped() << " run=" << rngRun << std::endl;
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
