#include "ns3/core-module.h"
#include "ns3/network-module.h"
#include "ns3/wifi-module.h"
#include "ns3/internet-module.h"
#include "ns3/applications-module.h"
#include "ns3/mobility-module.h"
#include "ns3/point-to-point-module.h"
#include "ns3/flow-monitor-module.h"
#include "ns3/netanim-module.h"

#include <memory>

#include "iomt-noise.h"

using namespace ns3;

NS_LOG_COMPONENT_DEFINE("IoMTDetailedNetworkWithAP");

int main(int argc, char *argv[]) {
    // Enable logging
    LogComponentEnable("UdpEchoClientApplication", LOG_LEVEL_INFO);
    LogComponentEnable("UdpEchoServerApplication", LOG_LEVEL_INFO);
    LogComponentEnable("FlowMonitor", LOG_LEVEL_INFO);  // Log flow monitor info

    // Set simulation parameters
    double simulationTime = 30.0; // seconds

    // --- CLI parameters: RNG run (seed) + output filename ---------------------
    // NS-3 is deterministic by default, so without varying --run every
    // replication produces identical results. Vary --run for statistically
    // independent replicas; --output keeps their FlowMonitor XMLs separate.
    uint32_t rngRun = 1;                          // independent replication ("seed")
    std::string output = "flowmonitor-stats_wip"; // output XML prefix (no extension)
    // The ward's congestion driver; calibrated in iomt-noise.h (docs/18).
    double heavyMbps = IOMT_HEAVY_MBPS;
    double heavySpread = IOMT_HEAVY_SPREAD; // 0 = exactly heavyMbps (calibration)
    // Packet traces are a debugging aid, not an output of the sweep: FlowMonitor
    // already carries every feature we extract. Under a congested medium they cost
    // ~100 MB of pcap/NetAnim per run and the I/O dominates the runtime, so they
    // are off unless asked for.
    bool tracing = false;
    CommandLine cmd;
    cmd.AddValue("run", "RNG run number for an independent replication (seed)", rngRun);
    cmd.AddValue("output", "Output filename prefix, without .xml", output);
    cmd.AddValue("heavy", "Imaging/video gateway offered load in Mbps (0 = off)", heavyMbps);
    cmd.AddValue("heavyspread", "Per-run fractional spread of the imaging rate", heavySpread);
    cmd.AddValue("tracing", "Write pcap + NetAnim traces (debugging only)", tracing);
    cmd.Parse(argc, argv);

    RngSeedManager::SetSeed(1);     // fixed base seed
    RngSeedManager::SetRun(rngRun); // independent random stream per run

    // Before any Wi-Fi device exists: small, embedded-sized MAC queues.
    LimitMacQueue();

    // Number of nodes
    uint32_t numNodes = 9; // 9 Wi-Fi devices

    // Create Wi-Fi nodes
    NodeContainer wifiNodes;
    wifiNodes.Create(numNodes);

    // Create a wireless access point (AP) node
    NodeContainer wifiApNode;
    wifiApNode.Create(1); // Single AP

    // Create Hexoskin Shirt Node (Bluetooth emulation)
    NodeContainer hexoskinNodes;
    hexoskinNodes.Create(1);

    // Wi-Fi channel and PHY configuration
    YansWifiChannelHelper channel = YansWifiChannelHelper::Default();
    AddChannelFading(channel); // per-run Nakagami fading on top of log-distance
    YansWifiPhyHelper phy = ns3::YansWifiPhyHelper();
    phy.SetChannel(channel.Create());

    // Configure Wi-Fi for station nodes
    WifiHelper wifi;
    wifi.SetStandard(WIFI_STANDARD_80211n);
    wifi.SetRemoteStationManager("ns3::MinstrelHtWifiManager");

    WifiMacHelper mac;
    Ssid ssid = Ssid("HealthNet_24G");

    // Configure station (STA) MAC
    mac.SetType("ns3::StaWifiMac", "Ssid", SsidValue(ssid), "ActiveProbing", BooleanValue(false));
    NetDeviceContainer wifiDevices = wifi.Install(phy, mac, wifiNodes);

    // Configure AP MAC
    mac.SetType("ns3::ApWifiMac", "Ssid", SsidValue(ssid));
    NetDeviceContainer apDevice = wifi.Install(phy, mac, wifiApNode);

    // Per-run random packet loss on every Wi-Fi receiver (STAs + AP): a real
    // noise floor so baseline delivery is not deterministically 1.0.
    AddReceiveNoise(wifiDevices);
    AddReceiveNoise(apDevice);

    // Install IP stack on all nodes
    InternetStackHelper stack;
    stack.Install(wifiNodes);
    stack.Install(wifiApNode);
    stack.Install(hexoskinNodes);

    // Assign IP addresses
    Ipv4AddressHelper address;
    address.SetBase("192.168.1.0", "255.255.255.0");
    Ipv4InterfaceContainer wifiInterfaces = address.Assign(wifiDevices);
    Ipv4InterfaceContainer apInterface = address.Assign(apDevice);

    // Set up mobility for station nodes
    MobilityHelper mobility;
    mobility.SetPositionAllocator("ns3::GridPositionAllocator",
                                  "MinX", DoubleValue(0.0),
                                  "MinY", DoubleValue(0.0),
                                  "DeltaX", DoubleValue(10.0),
                                  "DeltaY", DoubleValue(10.0),
                                  "GridWidth", UintegerValue(5),
                                  "LayoutType", StringValue("RowFirst"));
    mobility.SetMobilityModel("ns3::ConstantPositionMobilityModel");
    mobility.Install(wifiNodes);
    JitterPositions(wifiNodes); // small per-run position offset

    // Set up mobility for the AP
    Ptr<ListPositionAllocator> apPosition = CreateObject<ListPositionAllocator>();
    apPosition->Add(Vector(0.0, 0.0, 0.0)); // AP fixed at (0, 0)
    mobility.SetPositionAllocator(apPosition);
    mobility.Install(wifiApNode);

    // Set up mobility for the Hexoskin Shirt
    mobility.Install(hexoskinNodes);

    // Simulate Bluetooth with Point-to-Point Link between Smartphone and Hexoskin Shirt
    PointToPointHelper p2p;
    p2p.SetDeviceAttribute("DataRate", StringValue("3Mbps")); // Bluetooth typical speed
    p2p.SetChannelAttribute("Delay", StringValue("2ms"));
    NetDeviceContainer p2pDevices = p2p.Install(wifiNodes.Get(1), hexoskinNodes.Get(0));
    Ipv4AddressHelper p2pAddress;
    p2pAddress.SetBase("10.1.1.0", "255.255.255.0");
    Ipv4InterfaceContainer p2pInterfaces = p2pAddress.Assign(p2pDevices);

    // The medical path under study (STA2 -> STA0, port 8080): a patient-monitor
    // ECG waveform, and the flow the grey-hole attacks in the sibling scenario.
    // 128 kbps / 128 B is the real clinical profile: a low bit rate carried by
    // MANY SMALL packets. Packet COUNT, not bit rate, sets how finely delivery
    // can be measured, so this stays as packet-rich as the old generic 1 Mbps /
    // 512 B stream while using ~8x less of the band -- which is what leaves room
    // for the imaging gateway to congest the medium.
    uint16_t baxterPort = 8080;
    Address baxterAddress(InetSocketAddress(wifiInterfaces.GetAddress(0), baxterPort));
    PacketSinkHelper baxterSink("ns3::UdpSocketFactory", baxterAddress);
    ApplicationContainer baxterApp = baxterSink.Install(wifiNodes.Get(0)); // Baxter node
    baxterApp.Start(Seconds(1.0));
    baxterApp.Stop(Seconds(20.0));

    OnOffHelper baxterTraffic("ns3::UdpSocketFactory", baxterAddress);
    SetNoisyOnOff(baxterTraffic, 128e3, 128); // per-run randomized rate/size/burst
    ApplicationContainer baxterTrafficApp = baxterTraffic.Install(wifiNodes.Get(2)); // A secondary control device
    baxterTrafficApp.Start(Seconds(2.0));
    baxterTrafficApp.Stop(Seconds(20.0));

    // Smartphone Traffic (Lower Priority)
    uint16_t smartphonePort = 9090;
    Address smartphoneAddress(InetSocketAddress(wifiInterfaces.GetAddress(1), smartphonePort));
    PacketSinkHelper smartphoneSink("ns3::UdpSocketFactory", smartphoneAddress);
    ApplicationContainer smartphoneApp = smartphoneSink.Install(wifiNodes.Get(1)); // Smartphone node
    smartphoneApp.Start(Seconds(2.0));
    smartphoneApp.Stop(Seconds(20.0));

    OnOffHelper smartphoneTraffic("ns3::UdpSocketFactory", smartphoneAddress);
    SetNoisyOnOff(smartphoneTraffic, 64e3, 128); // per-run randomized rate/size/burst
    ApplicationContainer smartphoneTrafficApp = smartphoneTraffic.Install(hexoskinNodes.Get(0)); // Hexoskin Shirt
    smartphoneTrafficApp.Start(Seconds(3.0));
    smartphoneTrafficApp.Stop(Seconds(20.0));

    // The rest of the ward: a random subset of the light medical devices plus the
    // always-on imaging gateway (see iomt-noise.h for why that split matters).
    uint32_t crossFlows =
        InstallMedicalCrossTraffic(wifiNodes, wifiInterfaces, 2.0, 20.0, heavyMbps, heavySpread);
    std::cout << "Cross-traffic flows installed: " << crossFlows
              << " (imaging " << heavyMbps << " Mbps, spread " << heavySpread << ")" << std::endl;

    // Enable routing on the relay node so it can forward packets
    Ipv4GlobalRoutingHelper::PopulateRoutingTables();
    wifiNodes.Get(0)->GetObject<Ipv4>()->SetForwarding(1, true);  // Enable forwarding on interface 1 of relay

    // Packet traces + NetAnim: debugging aids, off by default (see --tracing).
    // Held by pointer because AnimationInterface starts writing as soon as it is
    // constructed, so it must not exist at all unless it was asked for.
    std::unique_ptr<AnimationInterface> anim;
    if (tracing)
    {
        phy.EnablePcap("wifi_ap_wip", wifiApNode);  // Capture Wi-Fi traffic
        phy.EnablePcap("baxter_pump_wip", wifiDevices.Get(0));  // Capture Baxter traffic (Node 0)
        phy.EnablePcap("hexoskin_phone_wip", wifiDevices.Get(1));  // Capture Baxter traffic (Node 0)
        p2p.EnablePcap("hexoskin_wip", p2pDevices);  // Capture Hexoskin traffic (P2P link)
        anim = std::make_unique<AnimationInterface>("network-anim_wip.xml");
    }

    // FlowMonitor setup
    FlowMonitorHelper flowmon;
    Ptr<FlowMonitor> monitor = flowmon.InstallAll();
    
    // Run the simulation
    Simulator::Stop(Seconds(simulationTime)); // Extended time
    Simulator::Run();
    
    // Check for lost packets and log stats
    monitor->CheckForLostPackets();

    // Save FlowMonitor stats to XML (for graphing)
    monitor->SerializeToXmlFile(output + ".xml", true, true);

    // Display flow statistics
    std::map<FlowId, FlowMonitor::FlowStats> stats = monitor->GetFlowStats();
    for (auto iter = stats.begin(); iter != stats.end(); ++iter)
    {
        std::cout << "Flow ID: " << iter->first << std::endl;
        std::cout << "  Tx Packets: " << iter->second.txPackets << std::endl;
        std::cout << "  Rx Packets: " << iter->second.rxPackets << std::endl;
        std::cout << "  Lost Packets: " << iter->second.lostPackets << std::endl;
        std::cout << "  Throughput: " << iter->second.rxBytes * 8.0 / simulationTime / 1000 << " kbps" << std::endl;
    }
    
    // Clean up and exit
    Simulator::Destroy();

    return 0;
}

