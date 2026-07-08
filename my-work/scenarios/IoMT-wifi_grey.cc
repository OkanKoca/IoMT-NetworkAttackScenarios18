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

// Each *-module.h pulls in one whole NS-3 subsystem (helpers + classes).
#include "ns3/core-module.h"          // Simulator, Ptr, CommandLine, RNG, Time
#include "ns3/network-module.h"       // Node, NetDevice, Packet, Socket, Address
#include "ns3/wifi-module.h"          // WifiHelper, Yans PHY/channel, MAC types
#include "ns3/internet-module.h"      // IP/UDP stack, addressing, routing
#include "ns3/applications-module.h"  // OnOffHelper, PacketSinkHelper
#include "ns3/mobility-module.h"      // node positions / mobility models
#include "ns3/point-to-point-module.h"// wired P2P link (Hexoskin BLE emulation)
#include "ns3/flow-monitor-module.h"  // per-flow statistics collection

using namespace ns3;

// Registers a named log component so NS_LOG_* macros can target this file.
NS_LOG_COMPONENT_DEFINE("IoMTGreyHole");

// ---------------------------------------------------------------------------
// Grey-hole relay application: forwards each received packet to a fixed
// destination with probability (1 - dropProb); drops it otherwise. Models a
// compromised on-path gateway performing selective forwarding.
//
// Derives from ns3::Application: the standard way to attach custom traffic
// behaviour to a node. NS-3 calls StartApplication()/StopApplication() at the
// times set via SetStartTime()/SetStopTime().
// ---------------------------------------------------------------------------
class GreyholeRelay : public Application
{
  public:
    // listenPort : UDP port this relay receives redirected victim traffic on
    // forwardTo   : real destination (pump address:port) survivors are sent to
    // dropProb    : p, probability each packet is dropped
    void Setup(uint16_t listenPort, Address forwardTo, double dropProb);
    // Public getters: counters are read from main() AFTER Simulator::Run(),
    // because StopApplication() may not fire when scheduled at the stop time.
    uint64_t GetForwarded() const { return m_forwarded; }
    uint64_t GetDropped() const { return m_dropped; }

  private:
    // "override": NS-3 calls these two automatically at start/stop time.
    void StartApplication() override;
    void StopApplication() override;
    // Receive callback: NS-3 invokes this every time a packet arrives.
    void HandleRead(Ptr<Socket> socket);

    // Ptr<T> = NS-3 reference-counted smart pointer (auto-frees the object
    // when the last Ptr to it goes away; no manual delete needed).
    Ptr<Socket> m_rxSocket;                 // receives the victim's traffic
    Ptr<Socket> m_txSocket;                 // forwards survivors to the pump
    uint16_t m_listenPort = 0;
    Address m_forwardTo;                    // generic address wrapper (holds IP:port)
    double m_dropProb = 0.0;
    Ptr<UniformRandomVariable> m_rng;       // drop decision (uses the RNG stream)
    uint64_t m_forwarded = 0;
    uint64_t m_dropped = 0;
};

void
GreyholeRelay::Setup(uint16_t listenPort, Address forwardTo, double dropProb)
{
    // Just stash the parameters; no sockets exist yet (app not started).
    m_listenPort = listenPort;
    m_forwardTo = forwardTo;
    m_dropProb = dropProb;
}

void
GreyholeRelay::StartApplication()
{
    // CreateObject<T>() constructs an NS-3 object and returns a Ptr<T> to it
    // (the NS-3 replacement for `new`, wired into the ref-counting system).
    m_rng = CreateObject<UniformRandomVariable>();

    // Receive the control traffic redirected to this (attacker) node.
    // Socket::CreateSocket(node, typeId) -> Ptr<Socket> bound to this node,
    // UdpSocketFactory::GetTypeId() selects a UDP socket.
    m_rxSocket = Socket::CreateSocket(GetNode(), UdpSocketFactory::GetTypeId());
    // Bind(local): claim a local address/port to listen on. GetAny() = 0.0.0.0
    // (accept on any interface). Returns 0 on success.
    m_rxSocket->Bind(InetSocketAddress(Ipv4Address::GetAny(), m_listenPort));
    // Register the receive handler. MakeCallback(&Method, this) wraps a member
    // function into an NS-3 callback object; HandleRead fires on each arrival.
    m_rxSocket->SetRecvCallback(MakeCallback(&GreyholeRelay::HandleRead, this));

    // Socket used to forward survivors to the real pump.
    m_txSocket = Socket::CreateSocket(GetNode(), UdpSocketFactory::GetTypeId());
    // Connect(peer): fix the remote endpoint so later Send() goes to the pump.
    m_txSocket->Connect(m_forwardTo);
}

void
GreyholeRelay::StopApplication()
{
    // Close() releases the socket. Null-guards handle "stopped but never started".
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
    // RecvFrom(from) -> Ptr<Packet> for the next queued packet, or a null Ptr
    // (evaluates false) when the queue is empty. 'from' is filled with sender.
    while ((packet = socket->RecvFrom(from)))
    {
        // Selective forwarding: drop with probability p, otherwise forward.
        // GetValue() -> double uniformly in [0,1); < p happens ~p of the time.
        if (m_rng->GetValue() < m_dropProb)
        {
            m_dropped++;
            continue;
        }
        // Forward a fresh packet of the same size. Re-sending the received
        // object would carry its FlowMonitor tag and mis-classify the hop.
        // Create<Packet>(size) -> Ptr<Packet> of `size` zero-filled bytes.
        Ptr<Packet> fresh = Create<Packet>(packet->GetSize());
        // Send(packet) -> bytes sent (>=0), or -1 on error. Goes to the peer
        // fixed by Connect() above (the pump).
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
    // CommandLine parses --key=value pairs; AddValue binds a flag to a variable.
    CommandLine cmd;
    cmd.AddValue("p", "Grey-hole drop probability (0.0 = none, 1.0 = blackhole)", dropProb);
    cmd.AddValue("run", "RNG run number for an independent replication (seed)", rngRun);
    cmd.AddValue("output", "Output filename prefix, without .xml", output);
    cmd.Parse(argc, argv); // overwrites the defaults above from argv

    // SetSeed fixes the base seed; SetRun picks an independent substream, so
    // different --run values give reproducible-but-different randomness.
    RngSeedManager::SetSeed(1);     // fixed base seed
    RngSeedManager::SetRun(rngRun); // independent random stream per run

    // --- Nodes ---------------------------------------------------------------
    // NodeContainer holds a set of nodes; Create(n) allocates n empty nodes.
    uint32_t numNodes = 9; // 9 Wi-Fi STAs
    NodeContainer wifiNodes;
    wifiNodes.Create(numNodes);
    NodeContainer wifiApNode;
    wifiApNode.Create(1);
    NodeContainer hexoskinNodes;
    hexoskinNodes.Create(1);

    // --- Wi-Fi PHY / MAC -----------------------------------------------------
    // Helper pattern: *Helper classes are shortcut factories that wire the
    // low-level objects together and return device/interface containers.
    YansWifiChannelHelper channel = YansWifiChannelHelper::Default();
    YansWifiPhyHelper phy;
    phy.SetChannel(channel.Create()); // Create() -> Ptr<YansWifiChannel>

    WifiHelper wifi;
    wifi.SetStandard(WIFI_STANDARD_80211n);
    wifi.SetRemoteStationManager("ns3::MinstrelHtWifiManager"); // rate-control algo

    WifiMacHelper mac;
    Ssid ssid = Ssid("HealthNet_24G");
    // Configure MAC as a station (STA), then install on the STA nodes.
    mac.SetType("ns3::StaWifiMac", "Ssid", SsidValue(ssid), "ActiveProbing", BooleanValue(false));
    // Install(phy, mac, nodes) -> NetDeviceContainer (one NIC per node).
    NetDeviceContainer wifiDevices = wifi.Install(phy, mac, wifiNodes);
    // Reconfigure the same MAC helper as an access point, install on the AP.
    mac.SetType("ns3::ApWifiMac", "Ssid", SsidValue(ssid));
    NetDeviceContainer apDevice = wifi.Install(phy, mac, wifiApNode);

    // --- Internet stack + addressing -----------------------------------------
    // InternetStackHelper adds IP/ARP/UDP/TCP to each node.
    InternetStackHelper stack;
    stack.Install(wifiNodes);
    stack.Install(wifiApNode);
    stack.Install(hexoskinNodes);

    Ipv4AddressHelper address;
    address.SetBase("192.168.1.0", "255.255.255.0"); // network + mask to hand out from
    // Assign(devices) -> Ipv4InterfaceContainer; gives each device an IP.
    Ipv4InterfaceContainer wifiInterfaces = address.Assign(wifiDevices);
    Ipv4InterfaceContainer apInterface = address.Assign(apDevice);

    // --- Mobility (all fixed) ------------------------------------------------
    // Places nodes on a grid and pins them (constant position = no movement).
    MobilityHelper mobility;
    mobility.SetPositionAllocator("ns3::GridPositionAllocator",
                                  "MinX", DoubleValue(0.0), "MinY", DoubleValue(0.0),
                                  "DeltaX", DoubleValue(10.0), "DeltaY", DoubleValue(10.0),
                                  "GridWidth", UintegerValue(5),
                                  "LayoutType", StringValue("RowFirst"));
    mobility.SetMobilityModel("ns3::ConstantPositionMobilityModel");
    mobility.Install(wifiNodes);
    // AP + Hexoskin get an explicit single position at the origin.
    Ptr<ListPositionAllocator> apPosition = CreateObject<ListPositionAllocator>();
    apPosition->Add(Vector(0.0, 0.0, 0.0));
    mobility.SetPositionAllocator(apPosition);
    mobility.Install(wifiApNode);
    mobility.Install(hexoskinNodes);

    // --- Hexoskin Bluetooth emulation (P2P) — untouched victim contrast ------
    // NS-3 has no native BLE, so a wired point-to-point link stands in for it.
    PointToPointHelper p2p;
    p2p.SetDeviceAttribute("DataRate", StringValue("3Mbps"));
    p2p.SetChannelAttribute("Delay", StringValue("2ms"));
    // Install on exactly two nodes -> the two ends of the link.
    NetDeviceContainer p2pDevices = p2p.Install(wifiNodes.Get(1), hexoskinNodes.Get(0));
    Ipv4AddressHelper p2pAddress;
    p2pAddress.SetBase("10.1.1.0", "255.255.255.0"); // separate subnet for the P2P link
    Ipv4InterfaceContainer p2pInterfaces = p2pAddress.Assign(p2pDevices);

    // --- Node roles ----------------------------------------------------------
    uint16_t pumpPort = 8080;  // real infusion-pump sink port
    uint16_t relayPort = 7070; // port the grey-hole relay listens on
    // InetSocketAddress(ip, port) wraps an IPv4 endpoint; GetAddress(i) returns
    // the IP assigned to interface i (STA index) above.
    Address pumpAddress(InetSocketAddress(wifiInterfaces.GetAddress(0), pumpPort));   // STA 0
    Address relayAddress(InetSocketAddress(wifiInterfaces.GetAddress(8), relayPort)); // STA 8 attacker

    // Real pump sink on STA 0.
    // PacketSinkHelper installs a server that just absorbs incoming packets.
    PacketSinkHelper pumpSink("ns3::UdpSocketFactory", pumpAddress);
    ApplicationContainer pumpApp = pumpSink.Install(wifiNodes.Get(0)); // -> ApplicationContainer
    pumpApp.Start(Seconds(1.0)); // Seconds(x) -> Time value; schedules app start
    pumpApp.Stop(Seconds(simulationTime));

    // High-priority control traffic (STA 2) — now aimed at the ATTACKER relay.
    // OnOffHelper generates a UDP stream toward the given remote address.
    OnOffHelper controlTraffic("ns3::UdpSocketFactory", relayAddress);
    controlTraffic.SetAttribute("DataRate", StringValue("1Mbps"));   // send rate while "on"
    controlTraffic.SetAttribute("PacketSize", UintegerValue(512));   // bytes per packet
    ApplicationContainer controlApp = controlTraffic.Install(wifiNodes.Get(2));
    controlApp.Start(Seconds(2.0)); // starts AFTER the relay is listening (1.0s)
    controlApp.Stop(Seconds(20.0));

    // Grey-hole relay on STA 8: forward survivors to the real pump with prob (1-p).
    Ptr<GreyholeRelay> relay = CreateObject<GreyholeRelay>();
    relay->Setup(relayPort, pumpAddress, dropProb);
    // AddApplication attaches our custom app to the attacker node (STA 8).
    wifiNodes.Get(8)->AddApplication(relay);
    relay->SetStartTime(Seconds(1.0)); // listening before control traffic begins
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

    // Computes global routing tables so STA2 -> STA8 -> STA0 paths resolve.
    Ipv4GlobalRoutingHelper::PopulateRoutingTables();

    // --- Measurement ---------------------------------------------------------
    FlowMonitorHelper flowmon;
    // InstallAll() attaches monitoring to every node -> Ptr<FlowMonitor>.
    Ptr<FlowMonitor> monitor = flowmon.InstallAll();

    // Event-loop control: stop time, run until then, then tear down.
    Simulator::Stop(Seconds(simulationTime));
    Simulator::Run();                       // processes the event queue
    monitor->CheckForLostPackets();         // finalizes lost-packet accounting
    // Serialize all flow stats to XML (path relative to the working dir).
    monitor->SerializeToXmlFile(output + ".xml", true, true);

    // Relay counters: proof p worked (read here, post-Run, via the getters).
    std::cout << "Grey-hole relay: forwarded=" << relay->GetForwarded()
              << " dropped=" << relay->GetDropped() << " (p=" << dropProb << ")" << std::endl;

    // GetFlowStats() -> map<FlowId, FlowStats>; iterate for a quick per-flow view.
    std::map<FlowId, FlowMonitor::FlowStats> stats = monitor->GetFlowStats();
    for (auto it = stats.begin(); it != stats.end(); ++it)
    {
        std::cout << "Flow ID: " << it->first << "  Tx: " << it->second.txPackets
                  << "  Rx: " << it->second.rxPackets << "  Lost: " << it->second.lostPackets
                  << std::endl;
    }

    Simulator::Destroy(); // frees all simulation objects
    return 0;
}
