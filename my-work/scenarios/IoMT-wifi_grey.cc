/*
 * IoMT-wifi_grey.cc
 * ---------------------------------------------------------------------------
 * Grey-hole (selective forwarding) attack on the IoMT Wi-Fi network.
 *
 * An on-path relay node receives the patient monitor's ECG waveform
 * traffic and forwards each packet to the real monitor only with probability
 * (1 - p), silently dropping it with probability p. Unlike a blackhole
 * (p = 1, drops everything and is obvious), a grey-hole with 0 < p < 1 leaks
 * only partial loss that resembles ordinary wireless degradation -> stealthy.
 *
 *   p = 0.0  -> behaves like the normal baseline (no loss)
 *   p = 1.0  -> a working blackhole (target flow fully denied)
 *
 * Note on measurement: the drop happens at the relay application, so the
 * survivors' hop (relay -> monitor) shows no L3 "lostPackets"; the attack instead
 * shows up as a THROUGHPUT / rxPackets deficit on the monitor-delivery flow.
 * End-to-end loss = 1 - (monitor rxPackets / ECG txPackets).
 *
 * Parameters:
 *   --p       drop probability (attack intensity knob), 0.0 .. 1.0
 *   --relay   STA index hosting the relay, 3..8 (distance knob; default 8)
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

#include "iomt-noise.h"               // shared per-run stochasticity helpers

#include <iostream>                   // std::cerr for the co-location warning below

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
    // forwardTo   : real destination (monitor address:port) survivors are sent to
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
    Ptr<Socket> m_txSocket;                 // forwards survivors to the monitor
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

    // Socket used to forward survivors to the real monitor.
    m_txSocket = Socket::CreateSocket(GetNode(), UdpSocketFactory::GetTypeId());
    // Connect(peer): fix the remote endpoint so later Send() goes to the monitor.
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
        // NOTE: zero-fill is intentional and fine for network-metric features
        // (throughput, OWD, PDV, loss all depend on size/timing, not content).
        // Payload is NOT preserved, so any future payload-based feature would
        // silently break here and must copy the original bytes instead.
        Ptr<Packet> fresh = Create<Packet>(packet->GetSize());
        // Send(packet) -> bytes sent (>=0), or -1 on error. Goes to the peer
        // fixed by Connect() above (the monitor).
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
    // The ward's congestion driver; calibrated in iomt-noise.h (docs/18).
    double heavyMbps = IOMT_HEAVY_MBPS;
    double heavySpread = IOMT_HEAVY_SPREAD; // 0 = exactly heavyMbps (calibration)
    // Which STA hosts the relay. Default 8 keeps every earlier run reproducible.
    // The grid places STA i at ((i%5)*10, (i/5)*10) with the AP at the origin, so the
    // index IS a distance: STA5 10.0 m, STA6 14.1 m, STA7 22.4 m, STA8 31.6 m, STA4 40.0 m.
    // The measured cost of an on-path relay therefore mixes two causes -- the extra hop and
    // the relay's own distance from the AP -- and sweeping this flag is what separates them.
    // STA0/1/2 are taken (monitor sink, telemetry sink, ECG source); picking one would
    // silently collapse two roles onto one node, so they are rejected below.
    uint32_t relayIndex = 8;
    // CommandLine parses --key=value pairs; AddValue binds a flag to a variable.
    CommandLine cmd;
    cmd.AddValue("p", "Grey-hole drop probability (0.0 = none, 1.0 = blackhole)", dropProb);
    cmd.AddValue("relay", "STA index hosting the relay (distance knob; 3-8, default 8)", relayIndex);
    cmd.AddValue("run", "RNG run number for an independent replication (seed)", rngRun);
    cmd.AddValue("output", "Output filename prefix, without .xml", output);
    cmd.AddValue("heavy", "Imaging/video gateway offered load in Mbps (0 = off)", heavyMbps);
    cmd.AddValue("heavyspread", "Per-run fractional spread of the imaging rate", heavySpread);
    cmd.Parse(argc, argv); // overwrites the defaults above from argv

    // Reject a relay index that would double-book a node whose role is already fixed,
    // rather than producing a run that looks valid but measures something else.
    if (relayIndex < 3 || relayIndex > 8)
    {
        NS_FATAL_ERROR("--relay must be in [3,8]: STA0 is the monitor sink, STA1 the "
                       "telemetry sink, STA2 the ECG source, and only 9 STAs exist.");
    }
    // STA3..STA7 are legal but NOT empty: each also sources a ward device (iomt-noise.h).
    // Hosting the relay there is allowed -- a position sweep needs those nodes -- but the
    // run then measures "relay + that device on one node", which is not the same quantity
    // as STA8, the only STA with no traffic of its own. STA7 matters most: it sources the
    // heavy imaging flow that drives congestion, so a relay placed there is measured under
    // a different load than a relay anywhere else. Comparing positions without accounting
    // for this reads a co-location difference as a distance effect.
    if (relayIndex >= 3 && relayIndex <= 7)
    {
        static const char* kOccupant[] = {"ventilator (64 kbps)", "pulse oximeter (8 kbps)",
                                          "NIBP cuff (2 kbps)", "infusion pump (16 kbps)",
                                          "HEAVY imaging gateway (congestion driver)"};
        std::cerr << "WARNING: STA" << relayIndex << " also sources the "
                  << kOccupant[relayIndex - 3] << ", so this run measures the relay AND that "
                  << "device on one node. STA8 is the only STA with no traffic of its own.\n";
    }

    // SetSeed fixes the base seed; SetRun picks an independent substream, so
    // different --run values give reproducible-but-different randomness.
    RngSeedManager::SetSeed(1);     // fixed base seed
    RngSeedManager::SetRun(rngRun); // independent random stream per run

    // Before any Wi-Fi device exists: small, embedded-sized MAC queues.
    LimitMacQueue();

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
    AddChannelFading(channel); // per-run Nakagami fading on top of log-distance
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

    // Per-run random packet loss on the legitimate receivers (STAs + AP): a real
    // noise floor so baseline delivery is not deterministically 1.0.
    AddReceiveNoise(wifiDevices);
    AddReceiveNoise(apDevice);

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
    JitterPositions(wifiNodes); // small per-run position offset
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
    uint16_t monitorPort = 8080;  // real patient-monitor sink port
    uint16_t relayPort = 7070; // port the grey-hole relay listens on
    // InetSocketAddress(ip, port) wraps an IPv4 endpoint; GetAddress(i) returns
    // the IP assigned to interface i (STA index) above.
    Address monitorAddress(InetSocketAddress(wifiInterfaces.GetAddress(0), monitorPort));   // STA 0
    Address relayAddress(InetSocketAddress(wifiInterfaces.GetAddress(relayIndex), relayPort));

    // Real patient-monitor sink on STA 0.
    // PacketSinkHelper installs a server that just absorbs incoming packets.
    PacketSinkHelper monitorSink("ns3::UdpSocketFactory", monitorAddress);
    ApplicationContainer monitorApp = monitorSink.Install(wifiNodes.Get(0)); // -> ApplicationContainer
    monitorApp.Start(Seconds(1.0)); // Seconds(x) -> Time value; schedules app start
    monitorApp.Stop(Seconds(simulationTime));

    // High-priority control traffic (STA 2) — now aimed at the ATTACKER relay.
    // OnOffHelper generates a UDP stream toward the given remote address.
    OnOffHelper ecgTraffic("ns3::UdpSocketFactory", relayAddress);
    // Patient-monitor ECG waveform: the real clinical profile is a low bit rate
    // carried by many small packets (see IoMT-wifi_wip.cc for the full rationale).
    // Packet COUNT is what sets how finely the drop probability p can be resolved,
    // so this victim path stays deliberately packet-rich.
    SetNoisyOnOff(ecgTraffic, 128e3, 128); // per-run randomized rate/size/burst
    ApplicationContainer ecgApp = ecgTraffic.Install(wifiNodes.Get(2));
    ecgApp.Start(Seconds(2.0)); // starts AFTER the relay is listening (1.0s)
    ecgApp.Stop(Seconds(20.0));

    // Grey-hole relay: forward survivors to the real monitor with prob (1-p).
    Ptr<GreyholeRelay> relay = CreateObject<GreyholeRelay>();
    relay->Setup(relayPort, monitorAddress, dropProb);
    // AddApplication attaches our custom app to the attacker node.
    wifiNodes.Get(relayIndex)->AddApplication(relay);
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
    SetNoisyOnOff(smartphoneTraffic, 64e3, 128); // per-run randomized rate/size/burst
    ApplicationContainer smartphoneTrafficApp = smartphoneTraffic.Install(hexoskinNodes.Get(0));
    smartphoneTrafficApp.Start(Seconds(3.0));
    smartphoneTrafficApp.Stop(Seconds(20.0));

    // The rest of the ward: a random subset of the light medical devices plus the
    // always-on imaging gateway (see iomt-noise.h for why that split matters).
    InstallMedicalCrossTraffic(wifiNodes, wifiInterfaces, 2.0, 20.0, heavyMbps, heavySpread);

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
