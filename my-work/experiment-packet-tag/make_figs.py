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
    """Detailed schematic: AP-centred infrastructure Wi-Fi with every application flow drawn and
    specified (rate/packet/port). Diagram shows structure; the table below carries the numbers.
    Flow specs are from iomt-noise.h + IoMT-wifi_wip.cc. Not to scale -- laid out for reading."""
    # (src, dst, role, rate, packet, port, category)
    flows = [
        ("STA2", "STA0", "EKG dalga formu (kurban)", "128 kbps", "128 B", "8080", "victim"),
        ("STA3", "STA0", "ventilatör", "64 kbps", "128 B", "8110", "bg"),
        ("STA4", "STA0", "pals oksimetre", "8 kbps", "64 B", "8120", "bg"),
        ("STA5", "STA1", "NIBP tansiyon manşonu", "2 kbps", "64 B", "8130", "bg"),
        ("STA6", "STA1", "infüzyon pompası", "16 kbps", "64 B", "8140", "bg"),
        ("STA7", "STA1", "görüntüleme / video geçidi", "~19 Mbps", "1200 B", "8150", "imaging"),
        ("HEX", "STA1", "telefon telemetrisi (BLE)", "64 kbps", "128 B", "9090", "bg"),
        ("STA8", "STA0", "SALDIRI: relay araya girer", "grey p / mitm d", "—", "7070", "attack"),
    ]
    label = {"AP": "AP\nHealthNet_24G", "STA0": "STA0\nhasta monitörü", "STA1": "STA1\ntelefon/geçit",
             "STA2": "STA2\nEKG kaynağı", "STA3": "STA3\nventilatör", "STA4": "STA4\noksimetre",
             "STA5": "STA5\nNIBP", "STA6": "STA6\npompa", "STA7": "STA7\ngörüntüleme",
             "STA8": "STA8\nSALDIRGAN", "HEX": "Hexoskin\n(giyilebilir)"}
    catcol = {"victim": BLUE, "bg": "#b7c2c9", "imaging": "#7f8c94", "attack": AMBER}
    pos = {"AP": (6.0, 4.0), "STA0": (2.4, 6.4), "STA2": (2.4, 1.6), "STA8": (9.9, 4.0),
           "STA1": (5.4, 7.2), "HEX": (7.7, 7.1), "STA7": (9.9, 6.6),
           "STA3": (9.9, 1.4), "STA4": (7.9, 0.9), "STA5": (1.7, 4.0), "STA6": (3.6, 7.0)}

    fig = plt.figure(figsize=(11.8, 9.6))
    gs = fig.add_gridspec(2, 1, height_ratios=[2.35, 1.0], hspace=0.18)
    ax = fig.add_subplot(gs[0]); ax.set_xlim(0, 12), ax.set_ylim(0, 8), ax.axis("off")

    def arrow(a, b, color, style="-", lw=2, rad=0.0, z=2, alpha=1.0):
        (x0, y0), (x1, y1) = pos[a], pos[b]
        ax.add_patch(FancyArrowPatch((x0, y0), (x1, y1), connectionstyle=f"arc3,rad={rad}",
                     arrowstyle="-|>", mutation_scale=12, color=color, lw=lw, alpha=alpha,
                     linestyle=style, shrinkA=22, shrinkB=22, zorder=z))

    # background + imaging flows first (behind), each src -> AP -> dst through the hub
    for src, dst, _l, _r, _p, _pt, cat in flows:
        if cat in ("bg", "imaging"):
            lw = 3.4 if cat == "imaging" else 1.3
            arrow(src, "AP", catcol[cat], lw=lw, rad=0.05, z=1, alpha=0.85)
            arrow("AP", dst, catcol[cat], lw=lw, rad=0.05, z=1, alpha=0.85)
    # victim path STA2 -> AP -> STA0 (blue, on top)
    arrow("STA2", "AP", BLUE, lw=2.6, rad=0.07, z=3)
    arrow("AP", "STA0", BLUE, lw=2.6, rad=0.07, z=3)
    # attack: relay interception STA2 -> STA8 -> STA0 (amber dashed)
    arrow("STA2", "STA8", AMBER, style=(0, (5, 3)), lw=2.2, rad=-0.30, z=3)
    arrow("STA8", "STA0", AMBER, style=(0, (5, 3)), lw=2.2, rad=-0.30, z=3)
    ax.text(4.0, 3.05, "128 kbps · 128 B\nport 8080", color=BLUE, fontsize=8.3, ha="center", zorder=5)
    ax.text(7.7, 5.7, "~19 Mbps · 1200 B\ntıkanıklık sürücüsü", color="#5f6c74", fontsize=8.3, ha="center", zorder=5)
    ax.text(9.9, 2.75, "tutar (MITM d)\nveya düşürür (grey p)", color=AMBER, fontsize=8.0, ha="center", zorder=5)

    for name, (x, y) in pos.items():
        attacker, victim = name == "STA8", name in ("STA0", "STA2")
        fill = "#f2ddc7" if attacker else ("#dbe7ee" if victim else ("#e4ebef" if name == "AP" else "#eef2f4"))
        edge = AMBER if attacker else ("#3a6b86" if victim else "#9fb0ba")
        ax.add_patch(Circle((x, y), 0.66, facecolor=fill, edgecolor=edge,
                            lw=2.2 if attacker else 1.2, zorder=4))
        ax.text(x, y, label[name], ha="center", va="center", fontsize=7.9, color=INK, zorder=5)

    from matplotlib.lines import Line2D
    leg = [Line2D([0], [0], color=BLUE, lw=2.4, label="kurban yolu (EKG) — ölçülen tek yol"),
           Line2D([0], [0], color=AMBER, lw=2.2, ls="--", label="saldırı: relay araya girer (grey/MITM)"),
           Line2D([0], [0], color="#7f8c94", lw=3.4, label="görüntüleme ~19 Mbps (tıkanıklık)"),
           Line2D([0], [0], color="#b7c2c9", lw=1.3, label="hafif arka plan cihazları")]
    ax.set_title("IoMT Wi-Fi topolojisi ve trafik akışları — altyapı modu, her akış AP üzerinden STA→AP→STA",
                 fontsize=12.5, color=INK, pad=6)

    axt = fig.add_subplot(gs[1]); axt.axis("off")
    rows = [[l, f"{s} → {d}", r, p, pt] for s, d, l, r, p, pt, _c in flows]
    cats = [c for *_, c in flows]
    tab = axt.table(cellText=rows, colLabels=["akış", "kaynak → hedef", "hız", "paket", "port"],
                    loc="center", cellLoc="left", colWidths=[0.34, 0.18, 0.17, 0.10, 0.09])
    tab.auto_set_font_size(False); tab.set_fontsize(9.0); tab.scale(1, 1.5)
    for (r, c), cell in tab.get_celld().items():
        cell.set_edgecolor("#dce3e7")
        if r == 0:
            cell.set_facecolor("#eef2f4"); cell.set_text_props(weight="bold", color=INK)
        else:
            cat = cats[r - 1]
            cell.set_facecolor({"victim": "#eaf2f8", "attack": "#fbeede", "imaging": "#f0f2f4"}.get(cat, "white"))
            if c == 0:
                cell.get_text().set_color(catcol[cat])
                cell.get_text().set_weight("bold" if cat in ("victim", "attack") else "normal")
    axt.set_title("Uygulama akışlarının tam dökümü  (arka plan her koşuda rastgele alt küme; "
                  "görüntüleme her zaman açık)", fontsize=9.5, color=MUTED, y=1.0)
    fig.legend(handles=leg, loc="lower center", ncol=4, frameon=False, fontsize=8.6,
               bbox_to_anchor=(0.5, 0.01))
    fig.subplots_adjust(bottom=0.10)
    fig.savefig(FIGS / "fig_topology.png", bbox_inches="tight", dpi=150)
    plt.close(fig)


def main():
    res = json.loads((HERE / "sixclass_results.json").read_text())
    fig_confusion(res)
    fig_mitm_curve(res)
    fig_topology()
    print("wrote:", ", ".join(p.name for p in sorted(FIGS.glob("*.png"))))


if __name__ == "__main__":
    main()
