# Day 3 — Reproduce NORMAL + DoS baseline

Reproduction of the two clean scenarios from `Simulated Networks/` to confirm the
NS-3 toolchain works and the study's setup is buildable. Builds on the upstream study
`ramamr33/IoMT-NetworkAttackScenarios18` (Zenodo DOI: `10.5281/zenodo.16747386`).

## Environment
- NS-3 **3.48** (`~/ns-3-dev`, built via `./ns3`)
- Default single-seed run (no `RngRun` set yet — seeds come in Day 5)

## How it was run
```bash
# from ~/ns-3-dev
cp "<repo>/Simulated Networks/IoMT-wifi_wip.cc"     scratch/
cp "<repo>/Simulated Networks/IoMT-wifi_wip_dos.cc" scratch/
./ns3 build IoMT-wifi_wip IoMT-wifi_wip_dos
./ns3 run IoMT-wifi_wip       # -> flowmonitor-stats_wip.xml
./ns3 run IoMT-wifi_wip_dos   # -> flowmonitor-stats_dos.xml
```
(runs were executed in isolated working dirs so the XMLs don't collide)

## Scenarios
| Scenario | Source | Attacker | Sim time | Output |
|---|---|---|---|---|
| NORMAL | `IoMT-wifi_wip.cc` | none | 30 s | `flowmonitor-stats_wip.xml` |
| DoS | `IoMT-wifi_wip_dos.cc` | STA idx 8, UDP flood (1024 B @ 0.01 s) | 40 s | `flowmonitor-stats_dos.xml` |

## Results (single seed)
**NORMAL** — 2 flows, 0 lost packets:
- Flow 1: Tx/Rx 2197, 316.4 kbps
- Flow 2: Tx/Rx 1999, 151.4 kbps

**DoS** — 3 flows (extra flow = attacker), 0 lost packets on the legit flows:
- Flow 1: Tx/Rx 3900, 820.6 kbps
- Flow 2: Tx/Rx 2197, 237.3 kbps
- Flow 3: Tx/Rx 1999, 113.5 kbps

DoS shows no packet loss on the WIP flow — consistent with the study's finding that
the WIP is resilient to UDP-flood packet loss (impact shows up in delay/throughput, not loss).

## Known caveat (carry into Day 4)
Sim durations differ: NORMAL = 30 s, DoS = 40 s. Throughput here is normalized by each
scenario's own `simulationTime`, so cross-scenario throughput is **not** directly comparable
yet. Normalize to a common duration (and a common seed set) before building the labeled dataset.
