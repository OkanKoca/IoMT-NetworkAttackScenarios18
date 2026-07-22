// iomt-timing.h -- end-to-end delay for the victim path, measured below the flow layer.
//
// WHY THIS EXISTS
//
// FlowMonitor reports per-FLOW transit: the gap between a flow's own tx and rx stamps.
// Where an on-path relay sits, it ends one flow and begins another, so any time the
// relay spends holding a packet falls BETWEEN two flows and neither flow's transit
// records it. Jitter is blind for the same reason -- with D(i,j) = (Rj-Ri) - (Sj-Si),
// a hold that shifts sends and receives together is exactly zero.
//
// The fix is not available inside the flow abstraction, so this steps outside it. The
// source stamps each packet, the stamp survives the relay, and the sink subtracts. That
// is a true end-to-end delay including whatever the relay did, and it is one sample per
// delivered packet rather than the one sample per RUN that a first-arrival estimate
// gives.
//
// It lives in a shared header rather than in each scenario because the feature list once
// lived in each notebook, the copies drifted, and a published table ended up assembled
// from two of them. A measurement definition that differs between scenarios would put
// the same column under two meanings, which is worse: nothing would fail, the numbers
// would just stop being comparable.
//
// USING IT (four lines per scenario)
//
//   #include "iomt-timing.h"
//   ...
//   PacketSinkHelper monitorSink(...);
//   EnableVictimTiming(monitorSink);                     // sink parses the header
//   ApplicationContainer monitorApp = monitorSink.Install(...);
//   E2eDelay e2e;  AttachTiming(monitorApp, e2e);        // collect per packet
//   ...
//   OnOffHelper ecgTraffic(...);
//   SetNoisyOnOff(ecgTraffic, 128e3, 128, 0.2, TimingHeaderBytes());
//   EnableVictimTiming(ecgTraffic);                      // source writes the header
//   ...
//   ReportTiming(e2e);                                   // after Simulator::Run()
//
// A RELAY MUST CARRY THE HEADER. Forwarding Create<Packet>(size) discards it and
// restores exactly the blindness this file exists to remove. Remove the header on
// receipt, keep it, and re-add the SAME one when forwarding -- re-stamping at the relay
// would erase the hold as effectively as dropping the header did.
//
// ONLY ENABLE IT WHERE THE PORT IS CLEAN. A sink told to expect the header will read
// the first bytes of any untagged packet as one. The victim's monitor port carries only
// the victim path; the background devices use their own ports and their own sinks.

#ifndef IOMT_TIMING_H
#define IOMT_TIMING_H

#include "ns3/application-container.h"
#include "ns3/nstime.h"
#include "ns3/on-off-helper.h"
#include "ns3/packet-sink-helper.h"
#include "ns3/packet.h"
#include "ns3/seq-ts-size-header.h"
#include "ns3/simulator.h"

#include <algorithm>
#include <iostream>
#include <numeric>
#include <vector>

namespace ns3
{

// Bytes the stamp costs on the wire. Pass to SetNoisyOnOff so the PAYLOAD shrinks by
// this much and the packet stays the size the baseline was calibrated at: instrumentation
// that grew the packets would move the saturation point it is measured against.
inline uint32_t
TimingHeaderBytes()
{
    return SeqTsSizeHeader().GetSerializedSize();
}

// Per-packet end-to-end delay, source stamp to sink.
class E2eDelay
{
  public:
    // Signature of PacketSink's RxWithSeqTsSize trace.
    void Rx(Ptr<const Packet>, const Address&, const Address&, const SeqTsSizeHeader& h)
    {
        m_ms.push_back((Simulator::Now() - h.GetTs()).GetSeconds() * 1000.0);
    }

    size_t Count() const { return m_ms.size(); }

    double Mean() const
    {
        return m_ms.empty() ? 0.0
                            : std::accumulate(m_ms.begin(), m_ms.end(), 0.0) / m_ms.size();
    }

    // Nearest-rank quantile on a sorted copy. The sample is small enough that sorting
    // per call is free, and mutating the record in order to read it would be a poor trade.
    double Quantile(double q) const
    {
        if (m_ms.empty()) return 0.0;
        std::vector<double> s(m_ms);
        std::sort(s.begin(), s.end());
        return s[(size_t)(q * (s.size() - 1))];
    }

  private:
    std::vector<double> m_ms;
};

inline void
EnableVictimTiming(OnOffHelper& source)
{
    source.SetAttribute("EnableSeqTsSizeHeader", BooleanValue(true));
}

inline void
EnableVictimTiming(PacketSinkHelper& sink)
{
    sink.SetAttribute("EnableSeqTsSizeHeader", BooleanValue(true));
}

inline void
AttachTiming(ApplicationContainer& sinkApp, E2eDelay& sink)
{
    sinkApp.Get(0)->TraceConnectWithoutContext("RxWithSeqTsSize",
                                              MakeCallback(&E2eDelay::Rx, &sink));
}

// One line, same shape in every scenario, so the sweep can parse it without knowing
// which scenario produced it. n=0 is a real answer, not a failure: it is what a fully
// denied victim path looks like, and reporting 0 ms for it would say "instant" -- the
// sentinel mistake that corrupted the timing features here once already.
inline void
ReportTiming(const E2eDelay& e2e)
{
    std::cout << "End-to-end delay (source stamp -> monitor): n=" << e2e.Count()
              << " mean=" << e2e.Mean() << "ms"
              << " median=" << e2e.Quantile(0.50) << "ms"
              << " p95=" << e2e.Quantile(0.95) << "ms" << std::endl;
}

} // namespace ns3

#endif // IOMT_TIMING_H
