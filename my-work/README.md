# my-work/ — internship working area

All original/experimental work for the IoMT attack-detection internship lives here, so the
upstream files (`Simulated Networks/`, `IoMT-Network-Attack-Scenarios/`, ...) stay clean for
attribution. See the root `CLAUDE.md` for the full plan. Upstream study:
`ramamr33/IoMT-NetworkAttackScenarios18` — Zenodo DOI `10.5281/zenodo.16747386`.

## Layout
| Folder | Purpose |
|---|---|
| `day3-baseline/` | Reproduced NORMAL + DoS FlowMonitor outputs (proves the toolchain works) |
| `day4-pipeline/` | FlowMonitor XML → labeled CSV pipeline (WIP) |
| `day5-newattack/` | The new stealthy attack (low-rate pulsing / Shrew DoS) + its runs |
| `scenarios/` | Curated copies of scenario `.cc` files actually used (edited/parameterized) |
| `data/` | Assembled datasets fed to the ML detector |

## Convention
Scenario `.cc` files are edited under `~/ns-3-dev/scratch/`, then the *source* + *result files*
are copied back here — never the whole ns-3 tree. Raw run artifacts (`*.pcap`, `network-anim*.xml`)
are git-ignored; curated result XML/CSV are committed on purpose.
