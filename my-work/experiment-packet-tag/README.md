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

## Results (full sweep + retrain, 2026-07-23)

The instrumented scenarios were swept in full (625 runs, `sweep/`, isolated from the
frozen `raw/` and dataset) and rebuilt with the true e2e delay added as three columns
(`e2e_delay_{median,mean,p95}_ms`). Reproduced by `isolate_tag.py`.

**The instrumentation is neutral to the baseline.** The 285-row tagged training set lands
the honest grouped-CV macro-F1 at **0.786**, byte-for-byte the frozen `v1.1` figure
(0.786-0.787) -- so the header + the DataRate compensation in `iomt-noise.h` did not move
the calibration.

**The stamp makes the hold a real axis.** Class medians of the new e2e delay vs the old
one-sample estimate (ms):

| class | e2e_median | old `startup_lag` |
|---|---|---|
| normal | 2.07 | 9.15 |
| benign relay (p=0) | 6.20 | 29.48 |
| grey-hole (all p) | 4.47 | 29.48 |
| mitm d<20 | 12.87 | 30.28 |
| mitm d>=20 | **99.54** | 83.98 |

The old estimate put the benign relay, the grey-hole and the low MITM at an identical
~30 ms; the stamp ranks them and pushes the real timing attack (99.5 ms) clear.

**But the tag fixes the timing confusion only, not the headline.** Two retrains:

*B. MITM trained as a class, benign relay held out as the control:*

| | macro-F1 | benign relay called 'mitm' | called 'greyhole' | any attack |
|---|---|---|---|---|
| tag-free | 0.786 | 0.47 | 0.42 | 1.00 |
| tag | 0.782 | **0.03** | 0.88 | 0.97 |

The tag all but eliminates the benign-relay-as-MITM error (0.47 -> 0.03), and lifts MITM
F1 (0.810 -> 0.827) and grey-hole F1 (0.918 -> 0.943). It does **not** lower how often the
benign relay is flagged at all (1.00 -> 0.97): the alarm simply moves from `mitm` to
`greyhole`. Macro-F1 is unchanged.

*Position control.* The far benign relay (STA8) genuinely loses packets -- delivery median
0.878, min 0.000 (bimodal, some seeds lose the first burst) -- so its any-attack rate is
0.97. A near benign relay (STA5, delivery 0.954) is flagged 0.72. Part of the residual is
therefore distance-induced loss reading as a mild grey-hole; part is not (even the clean
relay is flagged more often than not).

*C. Option 1 literal -- a detector whose negative class IS the benign relay, positive the
malicious relay, position fixed at STA8:*

| | benign false alarm | grey-hole recall | mitm recall |
|---|---|---|---|
| tag-free | 0.45 | 0.96 | 0.93 |
| tag | 0.38 | 0.88 | 0.95 |

Even given a benign-relay category to sort into and the tag, ~40% of benign relays are
still called malicious, because a benign on-path relay's involuntary loss is
mechanistically identical to a mild grey-hole. The tag helps the mechanism it was built
for (mitm recall 0.93 -> 0.95) and slightly hurts the one it is irrelevant to (grey-hole
0.96 -> 0.88).

### Verdict

The tag delivers a real, bounded contribution and **refines the project's central finding
rather than overturning it**:

> Flow-based detection reads the *mechanism* a relay imposes on the victim path -- added
> delay, lost packets -- not its *intent*. Instrumenting the true end-to-end delay turns
> the timing mechanism into a genuine intensity axis and stops a benign relay from being
> mistaken for a timing-MITM. It cannot separate a benign relay from a delivery attack,
> because an honest on-path relay produces real packet loss (extra hop, distance) that is
> indistinguishable from a mild grey-hole. The false alarm is relocated from the timing
> class to the delivery class, not removed.

This is the honest, partly-unfavourable result: a defensible methods contribution (the
timing axis) with an explicitly characterised limit (the delivery axis stays confounded).

## Six-class detector, MITM promoted to a trained class (Q1a, `mitm_sixclass.py`)

No new sweep: the MITM probes already exist, so promoting MITM to a sixth trained class (d>=20,
the probe rule) is an analysis step on the existing tagged data.

| class | P | R | F1 (tag) | F1 (tag-free) | n |
|---|---|---|---|---|---|
| normal | 0.705 | 0.775 | 0.738 | 0.692 | 40 |
| dos | 0.706 | 0.686 | 0.696 | 0.721 | 70 |
| ddos | 0.600 | 0.480 | 0.533 | 0.622 | 25 |
| greyhole | 0.915 | 0.973 | 0.943 | 0.918 | 110 |
| blackhole | 0.909 | 1.000 | 0.952 | 0.952 | 10 |
| mitm | 0.886 | 0.775 | **0.827** | 0.810 | 40 |

macro-F1 0.782 (tag) vs 0.786 (tag-free): promoting MITM does not move the headline, and MITM
lands at a healthy 0.827 without cannibalising grey-hole (0.943). The confusion matrix
(`figs/fig_confusion.png`) shows the two expected leaks: ddos->dos (10, the equal-volume overlap)
and **mitm->greyhole (9, the sub-threshold hold read as a delivery attack)**.

**The MITM curve reads clean, and it flags option (b).** Detection is saturated at 1.00 for every
`d` (relay presence, as expected); correct *typing* as MITM steps up sharply at `d≈50`
(`figs/fig_mitm_curve.png`): 0.10 at d<=20, 1.00 at d>=50. Below the knee the hold is too small
to separate from a benign/grey relay, so it is typed greyhole -- the thesis, on the timing axis.

But the per-fold MITM F1 is fragile: **[1.0, 0.952, 1.0, 0.182]** across the four folds that
carry MITM. With only 4 config-groups (d=20,50,100,200), one fold holds d=20 alone -- the weak
config -- and collapses. So the 0.827 is real but under-sampled. **This is what triggers option
(b):** a light top-up of a few `d` values in [20,200] (esp. near the 20-50 knee) to give more
config-groups and firm up the estimate -- ~40 runs, not a heavy sweep.

## Figures (`figs/`)

* `fig_topology.png` -- schematic of the AP-centred infrastructure Wi-Fi: node roles, the victim
  ECG path (STA2->AP->STA0), the relay interception (STA8), and the imaging congestion source.
* `fig_confusion.png` -- the 6-class confusion matrix above.
* `fig_mitm_curve.png` -- MITM detection (saturated) vs correct typing (knee at d~50).

A NetAnim animation of a DoS run (`netanim/network-anim_dos.xml`, regenerable, gitignored) can be
opened in the NetAnim viewer for a packet-level view of the flood; PyViz is unavailable (the
build has Python bindings off).
