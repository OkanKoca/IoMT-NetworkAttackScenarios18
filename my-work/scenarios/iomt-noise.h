#ifndef IOMT_NOISE_H
#define IOMT_NOISE_H

// Shared per-run stochasticity for the IoMT scenarios.
//
// The scenarios were deterministic: fixed traffic parameters, a clean Yans
// channel and fixed node positions gave a zero-variance baseline (normal
// delivery = 1.0 exactly), which makes every attack trivially separable and
// flattens the detection-vs-intensity curve. These helpers add reproducible,
// seed-driven variance to the legitimate side of the network so the baseline
// has a real noise floor. All randomness draws from ns-3's RNG streams, which
// RngSeedManager::SetRun(--run) makes independent-but-reproducible per run.
//
// Include this header after the ns-3 modules and call the helpers at the
// marked sites in each scenario (channel, mobility, device install, traffic).

#include <algorithm>
#include <string>
#include <vector>

#include "ns3/core-module.h"
#include "ns3/network-module.h"
#include "ns3/wifi-module.h"
#include "ns3/mobility-module.h"
#include "ns3/applications-module.h"
#include "ns3/internet-module.h"

namespace ns3 {

// Layer Nakagami fast-fading on top of the channel's existing (log-distance)
// path loss. Call AFTER YansWifiChannelHelper::Default() and BEFORE Create().
// Note: all nodes sit within a ~56 m span (< Distance1 = 80 m default), so only
// the m0 tier is exercised here; m1/m2 are set for completeness. Smaller m =
// heavier fading.
//
// Measured: on these short, high-SNR links fading surfaces as rate adaptation
// (throughput/delay variance), NOT as loss -- Minstrel answers a weaker signal
// with a slower, more robust modulation instead of dropping the frame. Neither
// this nor AddReceiveNoise moves end-to-end delivery (see that helper's note on
// MAC ARQ); a real delivery noise floor is a congestion effect and comes from
// the dense-topology stage. This helper is the physical-realism layer.
inline void AddChannelFading(YansWifiChannelHelper& channel)
{
    channel.AddPropagationLoss("ns3::NakagamiPropagationLossModel",
                               "m0", DoubleValue(2.0),
                               "m1", DoubleValue(1.5),
                               "m2", DoubleValue(1.0));
}

// Perturb each node's fixed position by a small per-run random offset. Call
// AFTER mobility.Install(...). Different distances -> different SNR each run,
// which both varies the channel and makes distinct --run values genuinely
// independent replicas instead of near-duplicates.
inline void JitterPositions(NodeContainer nodes, double maxJitter = 2.0)
{
    Ptr<UniformRandomVariable> u = CreateObject<UniformRandomVariable>();
    for (uint32_t i = 0; i < nodes.GetN(); ++i)
    {
        Ptr<MobilityModel> mm = nodes.Get(i)->GetObject<MobilityModel>();
        if (!mm)
        {
            continue;
        }
        Vector p = mm->GetPosition();
        p.x += u->GetValue(-maxJitter, maxJitter);
        p.y += u->GetValue(-maxJitter, maxJitter);
        mm->SetPosition(p);
    }
}

// Attach a small per-run random packet-loss model to each Wi-Fi device's
// receiver. Call AFTER wifi.Install(...). Note: 802.11 MAC ARQ retransmits a
// corrupted frame (up to ~7 times), so a small per-attempt error like this does
// NOT lower end-to-end delivery -- it surfaces as a little extra delay/jitter
// variance. A stable delivery noise floor is a congestion effect, produced by
// the dense-topology stage, not by link-error injection here. Each device gets
// its own per-attempt error rate from [minPer, maxPer].
inline void AddReceiveNoise(NetDeviceContainer devices,
                            double minPer = 0.005, double maxPer = 0.02)
{
    Ptr<UniformRandomVariable> u = CreateObject<UniformRandomVariable>();
    for (uint32_t i = 0; i < devices.GetN(); ++i)
    {
        Ptr<WifiNetDevice> wnd = DynamicCast<WifiNetDevice>(devices.Get(i));
        if (!wnd)
        {
            continue;
        }
        Ptr<RateErrorModel> em = CreateObject<RateErrorModel>();
        em->SetAttribute("ErrorUnit", EnumValue(RateErrorModel::ERROR_UNIT_PACKET));
        em->SetAttribute("ErrorRate", DoubleValue(u->GetValue(minPer, maxPer)));
        wnd->GetPhy()->SetPostReceptionErrorModel(em);
    }
}

// Randomize an OnOff application's send parameters around a base, so the
// legitimate flows are not byte-identical every run. Sets DataRate and
// PacketSize to +/-`spread` of the base and replaces the default constant 1s/1s
// on/off with random burst durations. baseRate is in bits/s, basePkt in bytes.
//
// The random on/off also swings the duty cycle run to run (~0.33 to ~0.88,
// mean ~0.63), so the OFFERED LOAD already varies even at spread = 0; pass
// spread = 0 when a caller needs an exactly known rate (calibration).
//
// PacketSize is clamped to 1472 B: that is the largest UDP payload that still
// fits a 1500 B MTU once the IP+UDP headers are added, so a randomized size can
// never silently start fragmenting (which would split one packet into two and
// corrupt the per-flow packet accounting FlowMonitor reports).
inline void SetNoisyOnOff(OnOffHelper& app, double baseRateBps, uint32_t basePkt,
                          double spread = 0.2)
{
    Ptr<UniformRandomVariable> u = CreateObject<UniformRandomVariable>();
    const double lo = 1.0 - spread;
    const double width = 2.0 * spread;
    double rate = baseRateBps * (lo + width * u->GetValue());
    app.SetAttribute("DataRate", DataRateValue(DataRate((uint64_t)rate)));
    uint32_t pkt = (uint32_t)std::clamp(basePkt * (lo + width * u->GetValue()), 64.0, 1472.0);
    app.SetAttribute("PacketSize", UintegerValue(pkt));
    app.SetAttribute("OnTime", StringValue("ns3::UniformRandomVariable[Min=0.5|Max=1.5]"));
    app.SetAttribute("OffTime", StringValue("ns3::UniformRandomVariable[Min=0.2|Max=1.0]"));
}

// Shrink every Wi-Fi MAC transmit queue. Call BEFORE any Wi-Fi device is built:
// Config::SetDefault only reaches objects constructed after it runs.
//
// ns-3 defaults to 500 packets, a router-sized buffer; embedded medical devices
// and small APs hold far less. The short queue is what turns medium contention
// into actual packet loss rather than unbounded delay, and congestion loss is
// the ONE delivery-axis lever 802.11 cannot hide: ARQ retransmits a corrupted
// frame away (see AddReceiveNoise), but it cannot retransmit a packet that was
// dropped before it ever reached the air. (A queued packet is also dropped once
// it exceeds WifiMacQueue::MaxDelay, 500 ms by default -- a second, latency-based
// path to the same congestion loss.)
inline void LimitMacQueue(uint32_t maxPackets = 50)
{
    Config::SetDefault("ns3::WifiMacQueue::MaxSize",
                       QueueSizeValue(QueueSize(std::to_string(maxPackets) + "p")));
}

// One background medical device: who sends, who collects it, on which port, and
// the profile it sends at while ON.
//
// Ports stay clear of the pipeline's role ports (8080 pump / 7070 relay_in /
// 9090 telemetry / 9 flood) so build_dataset reads this cross-traffic as "other":
// it feeds the structural + volume features (flow count, throughput, loss) while
// delivery_ratio keeps measuring the victim path alone.
struct MedicalFlow
{
    uint32_t src;    // STA index of the device
    uint32_t dst;    // STA index of the collector it reports to
    uint16_t port;   // its own destination port
    double rateBps;  // bits/s while ON
    uint32_t pkt;    // bytes
};

// The ward's background devices. Rates/sizes are the real clinical profiles:
// low bit-rate, many small packets. Note these are LIGHT on purpose -- their job
// is to vary the flow count and add contention, not to carry features of their
// own. The imaging gateway (below) is the one that drives congestion.
static const MedicalFlow IOMT_LIGHT_DEVICES[] = {
    {3, 0, 8110, 64e3, 128}, // ventilator     -> bedside monitor
    {4, 0, 8120, 8e3, 64},   // pulse oximeter -> bedside monitor
    {5, 1, 8130, 2e3, 64},   // NIBP cuff      -> ward gateway
    {6, 1, 8140, 16e3, 64},  // infusion pump  -> ward gateway
};

// Imaging/video gateway: the congestion driver. A real hospital Wi-Fi does not
// only carry telemetry -- imaging transfers, video consults and staff traffic
// share the band, and that mix is what actually congests an IoMT network.
// 1200 B is bulk-transfer sized and stays under the fragmentation limit.
static const MedicalFlow IOMT_HEAVY_DEVICE = {7, 1, 8150, 0.0 /* set by caller */, 1200};

// Calibrated load of the congestion driver, shared by every scenario: the whole
// point is that the baseline noise floor is IDENTICAL across classes, so this
// number lives in exactly one place.
//
// It is measured, not chosen (docs/18). probe_heavy.py found this medium
// saturates at ~12.9 Mbps of STA->STA throughput -- every byte crosses the air
// twice, STA -> AP -> STA -- and swept the response: 15 Mbps offered still
// delivers 99.9%, 20 Mbps gives 97.3%, 25 Mbps collapses to 86%. 19 Mbps +/-20%
// straddles that knee, so runs land on both sides of it and the baseline's
// delivery comes out spread (mean 0.968, std 0.034) instead of pinned at 1.0.
//
// Congestion is the ONLY lever that works here: it is what the ARQ finding
// (see AddReceiveNoise) left as the sole physical route to delivery variance.
// Re-run calibrate_normal.py after ANY change to the traffic profile, node
// count or queue size -- all of them move the knee.
static const double IOMT_HEAVY_MBPS = 19.0;
static const double IOMT_HEAVY_SPREAD = 0.2;

// Populate the ward around the victim path: a random subset of the light medical
// devices plus the always-on imaging gateway. Call AFTER addressing, with the
// window the legitimate traffic runs in. Returns the number of flows installed.
//
// Two separate jobs, deliberately split:
//
//  * FLOW COUNT (the structural artefact): a random SUBSET of the light devices
//    is active each run, so a normal run's flow count spreads instead of being
//    the constant 2 that made "flow count > 2" a free, intensity-independent
//    attack flag. Installing a FIXED number of background flows would not fix
//    this -- it would only move the flag's threshold, not remove it.
//
//  * DELIVERY FLOOR (the congestion): the imaging gateway is ALWAYS on. If it
//    were part of the random subset, congestion would be a per-run coin flip and
//    delivery would come out bimodal (clean runs vs congested runs) rather than
//    as a noise floor. Its RATE varies per run instead -- how busy the ward is
//    this run -- which is what spreads delivery smoothly.
inline uint32_t InstallMedicalCrossTraffic(NodeContainer wifiNodes,
                                           Ipv4InterfaceContainer wifiIfs,
                                           double startTime, double stopTime,
                                           double heavyMbps, double heavySpread = 0.2)
{
    Ptr<UniformRandomVariable> u = CreateObject<UniformRandomVariable>();
    uint32_t installed = 0;

    auto install = [&](const MedicalFlow& d, double rateBps, double spread) {
        Address dst(InetSocketAddress(wifiIfs.GetAddress(d.dst), d.port));
        // The sink must sit on the node that OWNS this address. A sink installed
        // on any other node still binds, but then nothing is listening where the
        // packets actually land -- and FlowMonitor, being an IP-layer probe,
        // reports the flow delivered regardless, so the mistake is invisible in
        // the data. (This is exactly the defect found in the upstream study.)
        PacketSinkHelper sink("ns3::UdpSocketFactory", dst);
        ApplicationContainer sinkApp = sink.Install(wifiNodes.Get(d.dst));
        sinkApp.Start(Seconds(std::max(0.0, startTime - 1.0)));
        sinkApp.Stop(Seconds(stopTime));

        OnOffHelper src("ns3::UdpSocketFactory", dst);
        SetNoisyOnOff(src, rateBps, d.pkt, spread);
        ApplicationContainer srcApp = src.Install(wifiNodes.Get(d.src));
        // Staggered start: a synchronized burst from every device is an artefact.
        srcApp.Start(Seconds(startTime + u->GetValue(0.0, 1.0)));
        srcApp.Stop(Seconds(stopTime));
        ++installed;
    };

    // Random subset of the light devices: k ~ U{0..n}, and WHICH ones is random
    // too (partial Fisher-Yates over the index list).
    const uint32_t nLight = sizeof(IOMT_LIGHT_DEVICES) / sizeof(IOMT_LIGHT_DEVICES[0]);
    std::vector<uint32_t> idx(nLight);
    for (uint32_t i = 0; i < nLight; ++i)
    {
        idx[i] = i;
    }
    for (uint32_t i = nLight; i > 1; --i)
    {
        std::swap(idx[i - 1], idx[u->GetInteger(0, i - 1)]);
    }
    uint32_t k = u->GetInteger(0, nLight);
    for (uint32_t i = 0; i < k; ++i)
    {
        install(IOMT_LIGHT_DEVICES[idx[i]], IOMT_LIGHT_DEVICES[idx[i]].rateBps, 0.2);
    }

    if (heavyMbps > 0.0)
    {
        install(IOMT_HEAVY_DEVICE, heavyMbps * 1e6, heavySpread);
    }
    return installed;
}

} // namespace ns3

#endif // IOMT_NOISE_H
