#!/usr/bin/env python3
"""
make_figs.py — report figures for the Stage-2 congestion calibration.

Two figures, each answering one question:
  Sekil 1: at what offered load does the medium congest?  (the measured knee)
  Sekil 2: did the baseline actually change?              (Stage 1 vs Stage 2)

Style follows the detector notebooks (CVD-safe palette, recessive grid, thin
marks) so the figures sit next to the existing report figures unchanged.
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
FIGDIR = HERE / "figs"
FIGDIR.mkdir(exist_ok=True)

# Ink tokens + palette: identical to the EDA/detector notebooks.
PRIMARY, SECONDARY, MUTED = "#0b0b0b", "#52514e", "#898781"
GRID, AXIS, SURFACE = "#e1e0d9", "#c3c2b7", "#fcfcfb"
BLUE, AMBER, RED = "#2a78d6", "#eda100", "#e34948"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "text.color": PRIMARY, "axes.labelcolor": SECONDARY, "axes.titlecolor": PRIMARY,
    "xtick.color": MUTED, "ytick.color": MUTED, "axes.edgecolor": AXIS,
    "font.size": 10, "axes.titlesize": 11, "axes.titleweight": "bold",
    "figure.dpi": 110, "savefig.dpi": 130, "savefig.bbox": "tight",
})


def style_ax(ax):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(True, color=GRID, linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)


# --------------------------------------------------------------------------
# Sekil 1 — the congestion knee.
# Delivery and throughput are different quantities on different scales, so they
# get two stacked panels sharing the x-axis, never a second y-axis.
# --------------------------------------------------------------------------
p = pd.read_csv(HERE / "probe_results.csv")
g = p.groupby("heavy_mbps")["delivery_ratio"].agg(["mean", "min", "max"])
t = p.groupby("heavy_mbps")["total_throughput_mbps"].mean()
x = g.index.values

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(7.0, 5.6), sharex=True,
                               gridspec_kw={"height_ratios": [1.35, 1]})

# Acceptance band: where the baseline must land to be a noise floor and not saturation.
ax1.axhspan(0.95, 1.0, color=BLUE, alpha=0.07, zorder=1)
ax1.text(40.3, 0.975, "kabul bandı\n0.95–1.0", color=SECONDARY, fontsize=8,
         va="center", ha="left")
ax1.fill_between(x, g["min"], g["max"], color=BLUE, alpha=0.18, lw=0, zorder=2)
ax1.plot(x, g["mean"], color=BLUE, lw=2, marker="o", ms=5, zorder=3)
ax1.axvline(19, color=RED, lw=1.4, ls="--", zorder=4)
ax1.text(19.6, 0.60, "seçilen taban\n19 Mbps ±%20", color=RED, fontsize=8.5, va="center")

for xv in (15, 20, 25):
    ax1.annotate(f"{g.loc[xv, 'mean']:.3f}", (xv, g.loc[xv, "mean"]),
                 textcoords="offset points", xytext=(0, -14), ha="center",
                 fontsize=8.5, color=SECONDARY)
ax1.set_ylabel("kurban yolu delivery")
ax1.set_title("Tıkanıklık dizi: görüntüleme yükü arttıkça tıbbi yolun teslimi", loc="left")
ax1.set_ylim(0.55, 1.03)
style_ax(ax1)

ax2.axhline(12.9, color=MUTED, lw=1, ls=":", zorder=1)
ax2.text(0.4, 13.3, "ortam tavanı ≈ 12.9 Mbps (STA→AP→STA)", color=SECONDARY, fontsize=8.5)
ax2.plot(x, t.values, color=SECONDARY, lw=2, marker="s", ms=4.5, zorder=3)
ax2.axvline(19, color=RED, lw=1.4, ls="--", zorder=4)
ax2.set_ylabel("toplam throughput (Mbps)")
ax2.set_xlabel("görüntüleme/video gateway'inin sunduğu yük (Mbps)")
ax2.set_title("Aynı süpürmede ölçülen doyum", loc="left")
ax2.set_ylim(0, 15.5)
style_ax(ax2)

fig.tight_layout()
fig.savefig(FIGDIR / "S1-tikaniklik-dizi.png")
plt.close(fig)

# --------------------------------------------------------------------------
# Sekil 2 — did the baseline change? Stage 1 vs Stage 2, per run.
# Two series -> legend + direct labels (amber's contrast warns, so it never
# carries meaning by colour alone).
# --------------------------------------------------------------------------
s1 = pd.read_csv(HERE / "../day3-4-08072026-09072026-dataset/"
                        "_pre-stage2-congestion-backup/dataset.csv")
s1 = s1[s1.scenario == "normal"]
s2 = pd.read_csv(HERE / "calib_results.csv")

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.4, 3.5))

rng = np.random.default_rng(0)
for i, (df, name, col) in enumerate([(s1, "Aşama 1 (40 koşu)", AMBER),
                                     (s2, "Aşama 2 (15 koşu)", BLUE)]):
    y = np.full(len(df), i) + rng.uniform(-0.13, 0.13, len(df))
    ax1.scatter(df.delivery_ratio, y, s=26, color=col, alpha=0.75,
                edgecolor=SURFACE, linewidth=0.8, zorder=3, label=name)
ax1.set_yticks([0, 1])
ax1.set_yticklabels(["Aşama 1", "Aşama 2"])
ax1.set_xlabel("normal koşunun delivery_ratio'su")
ax1.set_title("Taban artık 1.0'a çakılı değil", loc="left")
ax1.annotate(f"{(s1.delivery_ratio == 1.0).sum()}/40 koşu tam 1.0",
             (1.0, 0), textcoords="offset points", xytext=(-8, 26), ha="right",
             fontsize=8.5, color=SECONDARY,
             arrowprops=dict(arrowstyle="->", color=MUTED, lw=0.9))
ax1.text(0.02, 0.95, f"Aşama 2 — ort. {s2.delivery_ratio.mean():.3f}, "
                     f"std {s2.delivery_ratio.std():.3f}",
         transform=ax1.transAxes, fontsize=8.5, color=SECONDARY, va="top")
ax1.set_ylim(-0.5, 1.7)
style_ax(ax1)

vals = sorted(set(s1.n_flows) | set(s2.n_flows))
w = 0.38
c1 = [(s1.n_flows == v).sum() / len(s1) * 100 for v in vals]
c2 = [(s2.n_flows == v).sum() / len(s2) * 100 for v in vals]
idx = np.arange(len(vals))
ax2.bar(idx - w / 2, c1, w - 0.04, color=AMBER, zorder=3, label="Aşama 1 (40 koşu)")
ax2.bar(idx + w / 2, c2, w - 0.04, color=BLUE, zorder=3, label="Aşama 2 (15 koşu)")
ax2.set_xticks(idx)
ax2.set_xticklabels(vals)
ax2.set_xlabel("normal koşunun akış sayısı (n_flows)")
ax2.set_ylabel("koşuların %'si")
ax2.set_title("Yapısal artefakt: akış sayısı artık dağılıyor", loc="left")
ax2.annotate("Aşama 1'de hep 2 →\n“>2 akış = atak”\nbedava bir bayraktı",
             xy=(0 - w / 2, 100), xytext=(0.9, 62), fontsize=8.5, color=SECONDARY,
             arrowprops=dict(arrowstyle="->", color=MUTED, lw=0.9))
ax2.set_ylim(0, 112)
ax2.legend(frameon=False, fontsize=8.5, loc="upper right")
style_ax(ax2)

fig.tight_layout()
fig.savefig(FIGDIR / "S2-taban-karsilastirma.png")
plt.close(fig)

print("wrote:", *(p.name for p in sorted(FIGDIR.glob("*.png"))))
