#!/usr/bin/env python3
"""Report figures for the tagged 6-class experiment + the topology/attack-path schematic.

Palette reuses the project's validated pair (amber #c2691d relay, blue #1b6ca8 attack; the
dataviz validator passed it 6/6, docs/19) so these sit beside the existing figs. Confusion
uses a single-hue sequential ramp (magnitude). Writes PNGs to figs/.
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, Circle
import numpy as np

HERE = Path(__file__).resolve().parent
FIGS = HERE / "figs"
FIGS.mkdir(exist_ok=True)
BLUE, AMBER, INK, MUTED = "#1b6ca8", "#c2691d", "#22303a", "#6b7a85"
plt.rcParams.update({"font.size": 11, "axes.edgecolor": "#c9d2d8",
                     "axes.linewidth": 0.8, "figure.dpi": 150})


def fig_confusion(res):
    cm = np.array(res["confusion"])
    labels = res["classes"]
    cmn = cm / cm.sum(axis=1, keepdims=True)
    fig, ax = plt.subplots(figsize=(6.2, 5.4))
    im = ax.imshow(cmn, cmap="Blues", vmin=0, vmax=1)
    ax.set_xticks(range(len(labels)), labels, rotation=35, ha="right")
    ax.set_yticks(range(len(labels)), labels)
    ax.set_xlabel("tahmin edilen sınıf"), ax.set_ylabel("gerçek sınıf")
    for i in range(len(labels)):
        for j in range(len(labels)):
            if cm[i, j]:
                ax.text(j, i, f"{cm[i, j]}", ha="center", va="center",
                        color="white" if cmn[i, j] > 0.5 else INK, fontsize=10)
    ax.set_title(f"6-sınıf karışıklık matrisi (tag'li, dürüst grouped-CV)\n"
                 f"macro-F1 {res['macro_tag']:.3f}", fontsize=11, color=INK)
    cb = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cb.set_label("satır-normalize oran", color=MUTED)
    fig.tight_layout()
    fig.savefig(FIGS / "fig_confusion.png", bbox_inches="tight")
    plt.close(fig)


def fig_mitm_curve(res):
    c = res["curve"]
    d = [r["d"] for r in c]
    detect = [r["detect"] for r in c]
    typed = [r["typed_mitm"] for r in c]
    trained = [r["trained"] for r in c]
    fig, ax = plt.subplots(figsize=(7.2, 4.4))
    ax.axhline(1.0, color="#c9d2d8", lw=0.8, zorder=1)
    ax.plot(d, detect, "-o", color=BLUE, lw=2, ms=7, label="tespit (saldırı denir)", zorder=3)
    ax.plot(d, typed, "-o", color=AMBER, lw=2, ms=7, label="doğru tipleme (mitm denir)", zorder=3)
    # shade the trained region so probe (untrained, sub-20) is visually distinct
    xt = [r["d"] for r in c if r["trained"]]
    ax.axvspan(min(xt), max(d) * 1.15, color="#1b6ca8", alpha=0.05, zorder=0)
    ax.text(min(xt) * 1.05, 0.06, "eğitilen (d≥20)", color=MUTED, fontsize=9)
    ax.text(1.05, 0.06, "probe (eğitilmedi)", color=MUTED, fontsize=9)
    ax.set_xscale("log")
    ax.set_xticks(d, [f"{int(v)}" for v in d])
    ax.set_xlabel("MITM tutma süresi d (ms)"), ax.set_ylabel("oran (40 koşu / d)")
    ax.set_ylim(-0.03, 1.08)
    ax.set_title("MITM: tespit her zaman doygun, tipleme ~d=50'de eşik atlıyor",
                 fontsize=11, color=INK)
    ax.legend(frameon=False, loc="center right")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(axis="y", color="#eef2f4", lw=0.8)
    fig.tight_layout()
    fig.savefig(FIGS / "fig_mitm_curve.png", bbox_inches="tight")
    plt.close(fig)


def fig_topology():
    """Schematic: AP-centred infrastructure Wi-Fi, node roles, victim path and the relay
    interception, plus the imaging congestion source. Not to scale -- laid out for reading."""
    fig, ax = plt.subplots(figsize=(9.6, 6.4))
    ax.set_xlim(0, 10.4), ax.set_ylim(0.2, 7.3), ax.axis("off")
    # positions (schematic; separated so no two node circles overlap)
    pos = {
        "AP": (5.0, 3.5),
        "STA0\nhasta monitörü": (1.9, 5.6),
        "STA2\nEKG kaynağı": (1.9, 1.4),
        "STA8\nSALDIRGAN / relay": (8.5, 3.5),
        "STA1\ntelefon / geçit": (4.3, 6.5),
        "STA7\ngörüntüleme": (8.5, 6.1),
        "STA3-6\nventilatör/oksimetre/\nNIBP/pompa": (8.6, 1.1),
        "Hexoskin\n(BLE)": (6.6, 6.5),
    }
    roles = {  # node -> fill colour
        "AP": "#e8edf0", "STA0\nhasta monitörü": "#dCE7ee", "STA2\nEKG kaynağı": "#dCE7ee",
        "STA8\nSALDIRGAN / relay": "#f2ddc7", "STA1\ntelefon / geçit": "#e8edf0",
        "STA7\ngörüntüleme": "#e8edf0", "STA3-6\nventilatör/oksimetre/\nNIBP/pompa": "#eef2f4",
        "Hexoskin\n(BLE)": "#eef2f4",
    }
    for name, (x, y) in pos.items():
        edge = AMBER if "SALDIRGAN" in name else ("#3a6b86" if "monitör" in name or "EKG" in name else "#9fb0ba")
        ax.add_patch(Circle((x, y), 0.62, facecolor=roles[name], edgecolor=edge,
                            lw=2.0 if "SALDIRGAN" in name else 1.2, zorder=3))
        ax.text(x, y, name, ha="center", va="center", fontsize=8.2, color=INK, zorder=4)

    def arrow(a, b, color, style="-", lw=2, rad=0.0, z=2):
        (x0, y0), (x1, y1) = pos[a], pos[b]
        ax.add_patch(FancyArrowPatch((x0, y0), (x1, y1), connectionstyle=f"arc3,rad={rad}",
                     arrowstyle="-|>", mutation_scale=14, color=color, lw=lw,
                     linestyle=style, shrinkA=24, shrinkB=24, zorder=z))

    # normal victim path: STA2 -> AP -> STA0 (blue)
    arrow("STA2\nEKG kaynağı", "AP", BLUE, rad=0.05)
    arrow("AP", "STA0\nhasta monitörü", BLUE, rad=0.05)
    # attack: relay interception STA2 -> STA8(relay) -> STA0 (amber dashed, via AP conceptually)
    arrow("STA2\nEKG kaynağı", "STA8\nSALDIRGAN / relay", AMBER, style=(0, (5, 3)), rad=-0.25)
    arrow("STA8\nSALDIRGAN / relay", "STA0\nhasta monitörü", AMBER, style=(0, (5, 3)), rad=-0.25)
    # imaging congestion: STA7 -> AP (muted, thick); light background devices -> AP (faint)
    arrow("STA7\ngörüntüleme", "AP", "#9fb0ba", lw=3, rad=0.0)
    arrow("STA3-6\nventilatör/oksimetre/\nNIBP/pompa", "AP", "#cdd6db", lw=1.2, rad=0.0)
    arrow("Hexoskin\n(BLE)", "STA1\ntelefon / geçit", "#9fb0ba", lw=1.5)

    # legend
    from matplotlib.lines import Line2D
    leg = [Line2D([0], [0], color=BLUE, lw=2, label="kurban yolu (EKG): STA2→AP→STA0"),
           Line2D([0], [0], color=AMBER, lw=2, ls="--", label="saldırı: relay araya girer (grey/MITM)"),
           Line2D([0], [0], color="#9fb0ba", lw=3, label="tıkanıklık: görüntüleme ~19 Mbps")]
    ax.legend(handles=leg, loc="lower center", frameon=False, ncol=1,
              bbox_to_anchor=(0.5, -0.02), fontsize=9)
    ax.set_title("IoMT Wi-Fi topolojisi: roller, kurban yolu ve relay araya girmesi\n"
                 "(altyapı modu — her akış AP üzerinden geçer)", fontsize=12, color=INK)
    fig.tight_layout()
    fig.savefig(FIGS / "fig_topology.png", bbox_inches="tight")
    plt.close(fig)


def main():
    res = json.loads((HERE / "sixclass_results.json").read_text())
    fig_confusion(res)
    fig_mitm_curve(res)
    fig_topology()
    print("wrote:", ", ".join(p.name for p in sorted(FIGS.glob("*.png"))))


if __name__ == "__main__":
    main()
