# Experiment: end-to-end delay that survives an application-layer relay

Status: experimental. Nothing here feeds the frozen `v1.1` release, the dataset, the
model, or the report. It lives on its own branch for that reason.

## The gap this addresses

The timing-MITM relay holds each packet for `U[0.5d, 1.5d]` ms and the features cannot
see it. The reason is structural rather than a bug:

* FlowMonitor measures **per-flow transit** -- the time between a flow's own tx and rx
  stamps. The relay terminates the incoming flow and originates a new one, so the hold
  happens *between* two flows. The second flow's tx stamp is taken after the hold, and
  its transit is therefore unchanged.
* Jitter is blind for the same reason. With `D(i,j) = (Rj-Ri) - (Sj-Si)`, a hold that
  shifts send and receive times together contributes exactly zero.

The stand-in currently in the schema, `victim_startup_lag_ms`, infers the hold from when
the first packet arrives. It works, and it is one observation per run while every other
feature averages thousands. Measured across the MITM sweep, its within-configuration
spread is larger than the effect it exists to measure:

| `d` (ms) | mean lag | std | expected rise (`0.5d`) |
|---|---|---|---|
| 1 | 29.4 | 21.2 | 0.5 |
| 2 | 29.7 | 19.9 | 1.0 |
| 5 | 33.2 | 18.6 | 2.5 |
| 10 | 36.7 | 19.2 | 5.0 |
| 20 | 42.1 | 18.3 | 10.0 |
| 200 | 272.9 | 328.2 | 100.0 |

Below `d = 50` the axis is not readable, and at `d = 200` a single collapsing run sets
the spread.

## Approach

NS-3 already carries a send timestamp end to end; the work is to stop destroying it.

* `OnOffApplication` has an `EnableSeqTsSizeHeader` attribute that prepends a
  `SeqTsSizeHeader` (sequence number, send timestamp, size -- 20 bytes serialized).
* `PacketSink` has the matching attribute and a `RxWithSeqTsSize` trace that reports the
  header and the size per packet.
* The relay forwards `Create<Packet>(size)`, a fresh zero-filled packet, which drops the
  header. It has to remove the header on receipt and re-attach it when forwarding.

The measured quantity is then `Simulator::Now() - header.GetTs()` at the monitor: true
end-to-end delay for every delivered packet, the relay's hold included.

Two things to keep honest:

* **Packet size must stay constant.** The header adds 20 bytes on the wire. The OnOff
  payload is reduced by the same 20 so the baseline's throughput and saturation point do
  not move; otherwise this instrumentation would perturb the very calibration it is
  measured against.
* **This deliberately leaves the flow abstraction.** It is not a repair of the
  flow-level features -- their blindness is a property of the abstraction and stands as
  a finding. It is a second, lower-level measurement placed alongside them.

## The low-delay excess, isolated

A first look at three seeds showed the median at `d = 1` sitting 6-8 ms above the same
seed's `d = 0`, where the injected hold is 1 ms. Three candidates were tested and two
were eliminated outright:

* **Rng stream divergence — no.** The offered load is bit-identical across the sweep:
  the victim source sends 1573 packets and the heavy background flow 21554 at every
  value of `d`. Only what is *delivered* changes.
* **A code path discontinuity between immediate and deferred sending — no.** `d = 0`
  already goes through `Simulator::Schedule`, and `d = 0.001` reproduces `d = 0` to the
  last digit. There is no immediate-send branch to be discontinuous with.
* **Chaotic sensitivity of a saturated medium — no, and this was the wrong reading.**
  It came from three seeds. At ten, paired against each seed's own `d = 0`:

| `d` | paired delta | std | injected | t | seeds to resolve at 2 SE |
|---|---|---|---|---|---|
| 1 | +3.20 | 2.40 | 1 | 4.22 | 24 |
| 5 | +9.05 | 4.59 | 5 | 6.23 | 4 |
| 20 | +25.25 | 3.19 | 20 | 25.03 | 1 |

The effect is systematic, not chaotic. The earlier estimate that ~300 seeds would be
needed at `d = 1` was wrong by more than an order of magnitude, and wrong for a specific
reason worth recording: it divided by the *unpaired* spread across seeds (6.0 ms) rather
than the paired spread (2.4 ms). Most of the across-seed variance is each seed's own
baseline, and pairing removes it. Three seeds were also simply too few to see that.

What remains after the elimination is a real overshoot: the delta exceeds the injected
hold by roughly 2-3 ms at every `d`. It is not an artefact of summarising with a median
-- the mean overshoots by the same amount (+2.27, +1.78, +2.84) -- so it is physical.
The reading is that holding does two things: it adds its own duration, and it de-bunches
the relay's transmissions, which changes how they contend with the heavy background
flow. The second cost is roughly constant and does not scale with `d`, which is why it
dominates at the low end and disappears into the signal by `d = 20`.

## What this cannot fix

Binary detection will not gain a curve. The MITM uses the same relay whose mere presence
already drives detection to 0.975, so the decision is saturated before the hold does
anything. The gain, if any, is in **type separation**: grey-hole moves delivery and
leaves timing alone, MITM does the reverse. Ablation on the frozen model already shows
naming a relay run `greyhole` leans on the timing features (0.90 with them, 0.50
without) while detection does not -- so a cleaner timing axis is the part with room to
move.
