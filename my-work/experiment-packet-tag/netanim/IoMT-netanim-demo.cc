// Lightweight NetAnim demo of the IoMT topology.
//
// The full scenarios are unwatchable in NetAnim: a realistic ward run emits ~90k wireless
// events (every ECG/imaging/flood frame becomes an expanding circle) and it leaves the AP and
// Hexoskin stacked at the origin. This strips that back to what a viewer can actually read:
//   * explicit, spread-out node positions (nothing overlaps),
//   * named + colour-coded nodes (victim path blue, attacker orange),
//   * a handful of flows at MODEST rates so individual packets are visible,
//   * a short 9 s run.
// It is a visualisation aid, not part of the dataset pipeline -- no FlowMonitor, no noise.
//
// Build:  cp into ns-3 scratch/ and `./ns3 build IoMT-netanim-demo`
// Run:    the compiled binary writes netanim-demo.xml in the cwd; open it in NetAnim.

#include "ns3/core-module.h"
#include "ns3/network-module.h"
#include "ns3/wifi-module.h"
#include "ns3/internet-module.h"
#include "ns3/applications-module.h"
#include "ns3/mobility-module.h"
#include "ns3/netanim-module.h"

using namespace ns3;

int
main(int argc, char* argv[])
{
    double simTime = 9.0;
    CommandLine cmd;
    cmd.AddValue("time", "simulation seconds", simTime);
    cmd.Parse(argc, argv);

    NodeContainer sta;
    sta.Create(9);
    NodeContainer ap;
    ap.Create(1);
    NodeContainer hex;
    hex.Create(1);

    YansWifiChannelHelper ch = YansWifiChannelHelper::Default();
    YansWifiPhyHelper phy;
    phy.SetChannel(ch.Create());
    WifiHelper wifi;
    wifi.SetStandard(WIFI_STANDARD_80211n);
    WifiMacHelper mac;
    Ssid ssid("HealthNet_24G");
    mac.SetType("ns3::StaWifiMac", "Ssid", SsidValue(ssid), "ActiveProbing", BooleanValue(false));
    NetDeviceContainer staDev = wifi.Install(phy, mac, sta);
    mac.SetType("ns3::ApWifiMac", "Ssid", SsidValue(ssid));
    NetDeviceContainer apDev = wifi.Install(phy, mac, ap);

    InternetStackHelper stack;
    stack.Install(sta);
    stack.Install(ap);
    stack.Install(hex);
    Ipv4AddressHelper addr;
    addr.SetBase("192.168.1.0", "255.255.255.0");
    Ipv4InterfaceContainer staIf = addr.Assign(staDev);
    addr.Assign(apDev);

    // Explicit, spread positions (metres) so NetAnim lays the ward out cleanly and nothing
    // stacks. Mirrors the report's topology figure: monitor + EKG on the left, attacker far
    // right, imaging top-right, AP in the middle.
    auto place = [](NodeContainer& c, std::vector<Vector> v) {
        MobilityHelper m;
        Ptr<ListPositionAllocator> a = CreateObject<ListPositionAllocator>();
        for (auto& p : v)
            a->Add(p);
        m.SetPositionAllocator(a);
        m.SetMobilityModel("ns3::ConstantPositionMobilityModel");
        m.Install(c);
    };
    place(sta, {Vector(12, 42, 0),   // STA0 monitor
                Vector(34, 58, 0),   // STA1 phone/gateway
                Vector(12, 12, 0),   // STA2 EKG source (victim)
                Vector(64, 12, 0),   // STA3 ventilator
                Vector(52, 4, 0),    // STA4 oximeter
                Vector(4, 30, 0),    // STA5 NIBP
                Vector(24, 58, 0),   // STA6 pump
                Vector(62, 52, 0),   // STA7 imaging
                Vector(74, 32, 0)}); // STA8 ATTACKER
    place(ap, {Vector(38, 32, 0)});  // AP centre
    place(hex, {Vector(46, 58, 0)}); // Hexoskin

    // Modest constant-rate flows -> individual packets are visible (not a swarm).
    auto onoff = [](Address dst, std::string rate, uint32_t pkt) {
        OnOffHelper o("ns3::UdpSocketFactory", dst);
        o.SetAttribute("DataRate", StringValue(rate));
        o.SetAttribute("PacketSize", UintegerValue(pkt));
        o.SetAttribute("OnTime", StringValue("ns3::ConstantRandomVariable[Constant=1]"));
        o.SetAttribute("OffTime", StringValue("ns3::ConstantRandomVariable[Constant=0]"));
        return o;
    };
    auto sinkOn = [&](uint32_t node, uint16_t port) {
        PacketSinkHelper s("ns3::UdpSocketFactory",
                           InetSocketAddress(Ipv4Address::GetAny(), port));
        ApplicationContainer a = s.Install(sta.Get(node));
        a.Start(Seconds(0.5));
        a.Stop(Seconds(simTime));
    };

    sinkOn(0, 8080);  // monitor receives the ECG
    sinkOn(0, 9);     // monitor is also the flood target
    // Victim ECG STA2 -> STA0 (blue path), ~3 packets/s so each is individually visible.
    ApplicationContainer ecg =
        onoff(InetSocketAddress(staIf.GetAddress(0), 8080), "12kbps", 500).Install(sta.Get(2));
    ecg.Start(Seconds(1.0));
    ecg.Stop(Seconds(simTime));
    // Attacker STA8 -> STA0 flood, starts at t=3 s so the "before/after" is visible.
    ApplicationContainer flood =
        onoff(InetSocketAddress(staIf.GetAddress(0), 9), "60kbps", 500).Install(sta.Get(8));
    flood.Start(Seconds(3.0));
    flood.Stop(Seconds(simTime));
    // One background device (imaging, light here) so the ward is not empty: STA7 -> STA1.
    sinkOn(1, 8150);
    ApplicationContainer img =
        onoff(InetSocketAddress(staIf.GetAddress(1), 8150), "8kbps", 500).Install(sta.Get(7));
    img.Start(Seconds(1.5));
    img.Stop(Seconds(simTime));

    Ipv4GlobalRoutingHelper::PopulateRoutingTables();

    AnimationInterface anim("netanim-demo.xml");
    anim.EnablePacketMetadata(true);
    const char* desc[] = {"STA0 monitor", "STA1 phone/gw", "STA2 EKG (victim)", "STA3 ventilator",
                          "STA4 oximeter", "STA5 NIBP", "STA6 pump", "STA7 imaging",
                          "STA8 ATTACKER"};
    for (uint32_t i = 0; i < 9; ++i)
        anim.UpdateNodeDescription(sta.Get(i), desc[i]);
    anim.UpdateNodeDescription(ap.Get(0), "AP HealthNet_24G");
    anim.UpdateNodeDescription(hex.Get(0), "Hexoskin");
    // Colour the roles: victim path blue, attacker orange, AP grey, rest pale.
    anim.UpdateNodeColor(sta.Get(0), 27, 108, 168);   // monitor blue
    anim.UpdateNodeColor(sta.Get(2), 27, 108, 168);   // EKG blue
    anim.UpdateNodeColor(sta.Get(8), 230, 126, 34);   // attacker orange
    anim.UpdateNodeColor(ap.Get(0), 120, 130, 140);   // AP grey
    for (uint32_t i : {1u, 3u, 4u, 5u, 6u, 7u})
        anim.UpdateNodeColor(sta.Get(i), 200, 210, 216);
    anim.UpdateNodeColor(hex.Get(0), 200, 210, 216);

    Simulator::Stop(Seconds(simTime));
    Simulator::Run();
    Simulator::Destroy();
    return 0;
}
