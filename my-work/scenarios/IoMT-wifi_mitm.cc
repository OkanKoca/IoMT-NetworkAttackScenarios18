/*
 * IoMT-wifi_mitm.cc
 * ---------------------------------------------------------------------------
 * Timing MITM (delaying on-path relay) attack on the IoMT Wi-Fi network.
 *
 * An on-path relay node receives the patient monitor's ECG waveform traffic and
 * forwards EVERY packet to the real monitor -- but only after holding it for a
 * randomized interval. Nothing is dropped and nothing is altered: delivery stays
 * ~1.0 and the byte counts match, so a loss- or volume-based check sees a healthy
 * flow. The damage is purely temporal: the waveform reaches the monitor late and
 * unevenly, which for a patient monitor is a clinical-safety problem (a delayed
 * alarm is a missed alarm), not merely a network-quality one.
 *
 *   delay = 0    -> forwards immediately == the benign relay (see below)
 *   delay > 0    -> holds each packet ~U[0.5d, 1.5d] ms before forwarding
 *
 * Why this attack exists in this project (the unclaimed axis):
 *   The flow features span three modalities -- volume (dos/ddos), delivery
 *   (greyhole/blackhole) and timing. Nothing attacked the timing axis: the only
 *   timing signal present was a SIDE EFFECT of the relay's extra hop, not a
 *   controlled knob. --delay turns that side effect into an intensity axis.
 *
 * The relay lattice (one relay, one shared zero, three behaviours):
 *   forwards, no delay      -> baseline: grey p=0 == mitm delay=0
 *   forwards with prob 1-p  -> greyhole   (delivery axis)
 *   drops everything        -> blackhole  (delivery axis, endpoint)
 *   forwards after ~d ms    -> mitm       (TIMING axis)
 * Because mitm delay=0 is behaviourally identical to grey p=0, the zero point of
 * this attack's curve is already measured and doubles as a correctness check --
 * the same way blackhole == grey p=1 does.
 *
 * Why the hold is RANDOMIZED, not constant: a constant hold shifts every packet
 * equally, so one-way delay moves but packet-delay-variation does not -- only one
 * of the two timing features would respond. A randomized hold moves both, and is
 * the more faithful model of a compromised gateway (processing/queueing delay is
 * not constant). It lets packets reorder, which is realistic for this threat and
 * shows up honestly as inflated jitter.
 *
 * Calibration note: the relay already costs ~+12.6 ms of one-way delay just by
 * existing (an extra hop). Holds below that are inside the relay's own footprint;
 * the sweep grid is chosen to straddle it.
 *
 * Parameters:
 *   --delay   mean added hold in ms (attack intensity knob); 0 = benign relay
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
NS_LOG_COMPONENT_DEFINE("IoMTTimingMitm");

// ---------------------------------------------------------------------------
// Timing-MITM relay application: forwards EVERY received packet to a fixed
// destination, but only after a randomized hold of ~U[0.5d, 1.5d] ms. Models a
// compromised on-path gateway that tampers with timing rather than content.
//
// Contrast with GreyholeRelay (IoMT-wifi_grey.cc): same interception, same
// sockets, same node. The only difference is what happens to a received packet --
// dropped with probability p there, held for a while here.
// ---------------------------------------------------------------------------
class TimingMitmRelay : public Application
{
  public:
    // listenPort : UDP port this relay receives redirected victim traffic on
    // forwardTo  : real destination (monitor address:port) packets are sent to
    // delayMs    : d, MEAN added hold in ms; actual hold ~U[0.5d, 1.5d]
    void Setup(uint16_t listenPort, Address forwardTo, double delayMs);
    // Public getters: counters are read from main() AFTER Simulator::Run(),
    // because StopApplication() may not fire when scheduled at the stop time.
    uint64_t GetForwarded() const { return m_forwarded; }
    uint64_t GetHeld() const { return m_held; }
    uint64_t GetStranded() const { return m_stranded; }
    double GetMeanHoldMs() const { return m_held ? m_holdSumMs / m_held : 0.0; }

  private:
    // "override": NS-3 calls these two automatically at start/stop time.
    void StartApplication() override;
    void StopApplication() override;
    // Receive callback: NS-3 invokes this every time a packet arrives.
    void HandleRead(Ptr<Socket> socket);
    // Deferred send: Simulator::Schedule() calls this once the hold has elapsed.
    void Forward(uint32_t size);

    // Ptr<T> = NS-3 reference-counted smart pointer (auto-frees the object
    // when the last Ptr to it goes away; no manual delete needed).
    Ptr<Socket> m_rxSocket;                 // receives the victim's traffic
    Ptr<Socket> m_txSocket;                 // forwards packets to the monitor
    uint16_t m_listenPort = 0;
    Address m_forwardTo;                    // generic address wrapper (holds IP:port)
    double m_delayMs = 0.0;                 // d: mean hold (attack intensity knob)
    Ptr<UniformRandomVariable> m_rng;       // hold draw (uses the RNG stream)
    bool m_running = false;                 // guards sends after StopApplication()
    uint64_t m_held = 0;                    // packets accepted and scheduled
    uint64_t m_forwarded = 0;               // packets actually sent on
    uint64_t m_stranded = 0;                // still held when the app stopped
    double m_holdSumMs = 0.0;               // to report the realized mean hold
};

void
TimingMitmRelay::Setup(uint16_t listenPort, Address forwardTo, double delayMs)
{
    // Just stash the parameters; no sockets exist yet (app not started).
    m_listenPort = listenPort;
    m_forwardTo = forwardTo;
    m_delayMs = delayMs;
}

void
TimingMitmRelay::StartApplication()
{
    m_running = true;
    // CreateObject<T>() constructs an NS-3 object and returns a Ptr<T> to it
    // (the NS-3 replacement for `new`, wired into the ref-counting system).
    m_rng = CreateObject<UniformRandomVariable>();

    // Receive the control traffic redirected to this (attacker) node.
    m_rxSocket = Socket::CreateSocket(GetNode(), UdpSocketFactory::GetTypeId());
    m_rxSocket->Bind(InetSocketAddress(Ipv4Address::GetAny(), m_listenPort));
    m_rxSocket->SetRecvCallback(MakeCallback(&TimingMitmRelay::HandleRead, this));

    // Socket used to forward packets to the real monitor.
    m_txSocket = Socket::CreateSocket(GetNode(), UdpSocketFactory::GetTypeId());
    // Connect(peer): fix the remote endpoint so later Send() goes to the monitor.
    m_txSocket->Connect(m_forwardTo);
}

void
TimingMitmRelay::StopApplication()
{
    // Any Forward() events still queued must not touch a closed socket; the flag
    // makes them no-ops that get counted instead (see Forward()).
    m_running = false;
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
TimingMitmRelay::HandleRead(Ptr<Socket> socket)
{
    Ptr<Packet> packet;
    Address from;
    // RecvFrom(from) -> Ptr<Packet> for the next queued packet, or a null Ptr
    // (evaluates false) when the queue is empty. 'from' is filled with sender.
    while ((packet = socket->RecvFrom(from)))
    {
        // Hold time for THIS packet, drawn fresh: ~U[0.5d, 1.5d] ms.
        // Drawing per packet (not per run) is what makes the delay a jitter
        // source and not just a constant offset -- see the header note.
        double holdMs = 0.0;
        if (m_delayMs > 0.0)
        {
            // GetValue(min,max) -> double uniform in [min,max) off this stream.
            holdMs = m_rng->GetValue(0.5 * m_delayMs, 1.5 * m_delayMs);
        }
        m_holdSumMs += holdMs;

        // Seconds(double), NOT MilliSeconds(int): the grid reaches down to d=1 ms
        // and the jittered draw is fractional (e.g. 0.73 ms). MilliSeconds() takes
        // an integer and would truncate the whole low end of the sweep to 0.
        Time hold = Seconds(holdMs / 1000.0);

        // Schedule(delay, &Method, this, args...) queues a future call. At
        // holdMs = 0 this still fires at the SAME simulated time, so delay=0 adds
        // no simulated delay and stays equivalent to the benign relay.
        // Only the size is captured: forwarding a fresh packet (rather than the
        // received object) avoids carrying its FlowMonitor tag into the next hop.
        Simulator::Schedule(hold, &TimingMitmRelay::Forward, this, packet->GetSize());
        m_held++;
    }
}

void
TimingMitmRelay::Forward(uint32_t size)
{
    // The app may have stopped while this packet was being held. Sending on a
    // closed socket would be an error; count it as stranded instead. With the
    // sweep's timings (victim stops at 20 s, relay at 30 s) this should stay 0 --
    // it is reported so a non-zero value is impossible to miss.
    if (!m_running || !m_txSocket)
    {
        m_stranded++;
        return;
    }
    // Create<Packet>(size) -> Ptr<Packet> of `size` zero-filled bytes.
    // NOTE: zero-fill is intentional and fine for network-metric features
    // (throughput, OWD, PDV, loss all depend on size/timing, not content).
    // It also means this scenario CANNOT be extended into content tampering
    // without first giving the victim traffic a real payload to corrupt.
    Ptr<Packet> fresh = Create<Packet>(size);
    m_txSocket->Send(fresh);
    m_forwarded++;
}

int
main(int argc, char* argv[])
{
    double simulationTime = 30.0; // seconds (match the NORMAL baseline)

    // --- CLI parameters: intensity (delay), RNG run (seed), output filename ---
    double delayMs = 0.0;                           // d: attack intensity knob
    uint32_t rngRun = 1;                            // independent replication (seed)
    std::string output = "flowmonitor-stats_mitm";  // output XML prefix (no ext.)
    // The ward's congestion driver; calibrated in iomt-noise.h (docs/18).
    double heavyMbps = IOMT_HEAVY_MBPS;
    double heavySpread = IOMT_HEAVY_SPREAD; // 0 = exactly heavyMbps (calibration)
    // Which STA hosts the relay -- same knob, same meaning, same default as IoMT-wifi_grey.cc.
    // It has to stay symmetric with grey because `mitm delay=0` and `grey p=0` are the same
    // physical thing (an on-path relay doing nothing), and that identity is what anchors the
    // zero point of the timing curve. A different default here would silently break it.
    uint32_t relayIndex = 8;
    // CommandLine parses --key=value pairs; AddValue binds a flag to a variable.
    CommandLine cmd;
    cmd.AddValue("delay", "Mean added hold in ms (0 = benign relay); actual ~U[0.5d,1.5d]", delayMs);
    cmd.AddValue("relay", "STA index hosting the relay (distance knob; 3-8, default 8)", relayIndex);
    cmd.AddValue("run", "RNG run number for an independent replication (seed)", rngRun);
    cmd.AddValue("output", "Output filename prefix, without .xml", output);
    cmd.AddValue("heavy", "Imaging/video gateway offered load in Mbps (0 = off)", heavyMbps);
    cmd.AddValue("heavyspread", "Per-run fractional spread of the imaging rate", heavySpread);
    cmd.Parse(argc, argv); // overwrites the defaults above from argv

    NS_ABORT_MSG_IF(delayMs < 0.0, "--delay must be >= 0");

    // Same rejection as IoMT-wifi_grey.cc: STA0/1/2 already hold the monitor sink, the
    // telemetry sink and the ECG source, and only 9 STAs exist.
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
    uint32_t numNodes = 9; // 9 Wi-Fi STAs
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
    phy.SetChannel(channel.Create()); // Create() -> Ptr<YansWifiChannel>

    WifiHelper wifi;
    wifi.SetStandard(WIFI_STANDARD_80211n);
    wifi.SetRemoteStationManager("ns3::MinstrelHtWifiManager"); // rate-control algo

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
    address.SetBase("192.168.1.0", "255.255.255.0"); // network + mask to hand out from
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
    p2pAddress.SetBase("10.1.1.0", "255.255.255.0"); // separate subnet for the P2P link
    Ipv4InterfaceContainer p2pInterfaces = p2pAddress.Assign(p2pDevices);

    // --- Node roles ----------------------------------------------------------
    uint16_t monitorPort = 8080;  // real patient-monitor sink port
    uint16_t relayPort = 7070;    // port the MITM relay listens on
    Address monitorAddress(InetSocketAddress(wifiInterfaces.GetAddress(0), monitorPort));   // STA 0
    Address relayAddress(InetSocketAddress(wifiInterfaces.GetAddress(relayIndex), relayPort));

    // Real patient-monitor sink on STA 0.
    PacketSinkHelper monitorSink("ns3::UdpSocketFactory", monitorAddress);
    ApplicationContainer monitorApp = monitorSink.Install(wifiNodes.Get(0));
    monitorApp.Start(Seconds(1.0));
    monitorApp.Stop(Seconds(simulationTime));

    // High-priority control traffic (STA 2) — aimed at the ATTACKER relay.
    OnOffHelper ecgTraffic("ns3::UdpSocketFactory", relayAddress);
    // Patient-monitor ECG waveform: the real clinical profile is a low bit rate
    // carried by many small packets (see IoMT-wifi_wip.cc for the full rationale).
    // Packet COUNT is what sets how finely the timing distribution can be
    // resolved, so this victim path stays deliberately packet-rich.
    SetNoisyOnOff(ecgTraffic, 128e3, 128); // per-run randomized rate/size/burst
    ApplicationContainer ecgApp = ecgTraffic.Install(wifiNodes.Get(2));
    ecgApp.Start(Seconds(2.0)); // starts AFTER the relay is listening (1.0s)
    ecgApp.Stop(Seconds(20.0));

    // Timing-MITM relay on STA 8: forwards everything, but ~d ms late.
    Ptr<TimingMitmRelay> relay = CreateObject<TimingMitmRelay>();
    relay->Setup(relayPort, monitorAddress, delayMs);
    wifiNodes.Get(relayIndex)->AddApplication(relay);
    relay->SetStartTime(Seconds(1.0)); // listening before control traffic begins
    // The 10 s gap between the victim stopping (20 s) and the relay stopping
    // leaves room for the longest held packet to still be delivered.
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
    Ptr<FlowMonitor> monitor = flowmon.InstallAll();

    Simulator::Stop(Seconds(simulationTime));
    Simulator::Run();                       // processes the event queue
    monitor->CheckForLostPackets();         // finalizes lost-packet accounting
    monitor->SerializeToXmlFile(output + ".xml", true, true);

    // Relay counters: proof the hold worked (read here, post-Run, via getters).
    // held == forwarded and stranded == 0 is the invariant: a timing MITM must
    // not lose packets, otherwise it has quietly become a grey-hole.
    std::cout << "Timing-MITM relay: held=" << relay->GetHeld()
              << " forwarded=" << relay->GetForwarded()
              << " stranded=" << relay->GetStranded()
              << " (delay=" << delayMs << "ms, realized mean hold="
              << relay->GetMeanHoldMs() << "ms)" << std::endl;

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
