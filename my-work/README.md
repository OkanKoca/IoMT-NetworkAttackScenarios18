# my-work/ — original working area

All original/experimental work for the IoMT attack-detection project lives here, so the
upstream files (`Simulated Networks/`, `IoMT-Network-Attack-Scenarios/`, ...) stay clean for
attribution. Upstream study: `ramamr33/IoMT-NetworkAttackScenarios18` — Zenodo DOI
`10.5281/zenodo.16747386`.

Folders are named by real working day + date (`dayN-ddmmyyyy-topic`) as a chronological journal.

## Layout
| Folder | Purpose |
|---|---|
| `day2-07072026-baseline/` | Reproduced NORMAL + DoS FlowMonitor outputs (proves the toolchain works) |
| `day3-4-08072026-09072026-dataset/` | FlowMonitor XML → labeled CSV pipeline (`run_sweep.py`, `build_dataset.py`) + the assembled dataset (`out/dataset.csv`) |
| `day5-10072026-detector/` | ML detector — Jupyter notebooks (binary → multiclass → intensity curve) |
| `scenarios/` | Curated copies of scenario `.cc` files actually used (edited/parameterized) |

## Convention
Scenario `.cc` files are edited under `~/ns-3-dev/scratch/`, then the *source* + *result files*
are copied back here — never the whole ns-3 tree. Raw run artifacts (`*.pcap`, `network-anim*.xml`)
are git-ignored; curated result XML/CSV are committed on purpose. ML work runs in the repo-root
`.venv/` (see memory / docs).
