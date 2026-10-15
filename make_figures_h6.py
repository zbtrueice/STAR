# -*- coding: utf-8 -*-
"""make_figures_h6.py -- H6 mechanism-boundary figures (reads the CSV/JSON under
results/mech_verify/H6)."""
import csv
import io
import json
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent
RES = ROOT / "results" / "mech_verify" / "H6"
FIG = ROOT / "figures" / "mech_verify" / "H6"
FIG.mkdir(parents=True, exist_ok=True)

plt.rcParams.update({
    "font.family": "DejaVu Sans", "axes.edgecolor": "#333333",
    "axes.linewidth": 1.0, "axes.labelsize": 10.5, "axes.titlesize": 11,
    "xtick.labelsize": 9.5, "ytick.labelsize": 9.5, "legend.fontsize": 8,
    "figure.dpi": 100, "axes.grid": False,
})

VAR_COL = {"off": "#ff7f0e", "on": "#2ca02c"}
VAR_LABEL = {"off": "Hole OFF", "on": "Hole ON"}


def load_csv(name):
    p = RES / name
    if not p.exists():
        return []
    return list(csv.DictReader(io.open(p, encoding="utf-8")))


def heatmap(ax, mat, ratios, diams, title, cmap, vmin=None, vmax=None,
            fmt="{:.2f}", center0=False):
    im = ax.imshow(mat, cmap=cmap, vmin=vmin, vmax=vmax, aspect="auto",
                   origin="lower")
    ax.set_xticks(range(len(diams)))
    ax.set_xticklabels([str(int(d)) for d in diams])
    ax.set_yticks(range(len(ratios)))
    ax.set_yticklabels(["%.1f" % r for r in ratios])
    ax.set_xlabel("target hole diameter (m)")
    ax.set_ylabel("d / $C_{th}$ (target)")
    ax.set_title(title, fontsize=10)
    for i in range(len(ratios)):
        for j in range(len(diams)):
            v = mat[i, j]
            txt = "--" if (v is None or (isinstance(v, float) and np.isnan(v))
                           or v < -0.5) else fmt.format(v)
            ax.text(j, i, txt, ha="center", va="center", fontsize=8,
                    color="white" if (not center0 and abs(float(v if v is not None else 0))
                                      > (vmax or 1) * 0.55) else "black")
    fig_colorbar(im, ax)


def fig_colorbar(im, ax):
    from mpl_toolkits.axes_grid1 import make_axes_locatable
    divider = make_axes_locatable(ax)
    cax = divider.append_axes("right", size="5%", pad=0.05)
    plt.colorbar(im, cax=cax)


def fig_heatmaps():
    rows = load_csv("H6_summary.csv")
    if not rows:
        return
    ratios = sorted({float(r["d_ratio_target"]) for r in rows})
    diams = sorted({float(r["D_target"]) for r in rows})

    def grid(key, missing=np.nan):
        m = np.full((len(ratios), len(diams)), missing)
        for r in rows:
            i = ratios.index(float(r["d_ratio_target"]))
            j = diams.index(float(r["D_target"]))
            v = r.get(key)
            m[i, j] = np.nan if v in (None, "") else float(v)
        return m

    fig, axes = plt.subplots(2, 2, figsize=(13, 10))
    heatmap(axes[0, 0], grid("failure_rate_OFF"), ratios, diams,
            "OFF recovery failure rate", "Oranges", vmin=0, vmax=1)
    heatmap(axes[0, 1], grid("success_rate_ON"), ratios, diams,
            "ON recovery success rate", "Greens", vmin=0, vmax=1)
    heatmap(axes[1, 0], grid("recovery_time_diff_ON_minus_OFF"), ratios, diams,
            "recovery time diff (ON $-$ OFF, steps; -- = not both recovered)",
            "RdBu_r", center0=True)
    heatmap(axes[1, 1], grid("coverage_gain_ON_minus_OFF"), ratios, diams,
            "final coverage gain (ON $-$ OFF)", "RdBu_r", center0=True,
            fmt="{:+.3f}")
    fig.suptitle("H6 hole-fill operating boundary: d/$C_{th}$ × hole diameter "
                 "(5 paired seeds)", y=0.99)
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    fig.savefig(FIG / "Fig_H6_heatmaps.png")
    print("Fig_H6_heatmaps ->", FIG / "Fig_H6_heatmaps.png")


def fig_timeseries():
    p = RES / "H6_timeseries.json"
    if not p.exists():
        return
    with io.open(p, encoding="utf-8") as f:
        data = json.load(f)
    series = data["series"]
    ratios = sorted({float(s["d_ratio_target"]) for s in series})
    diams = sorted({float(s["D_target"]) for s in series})
    # Representative combinations: per d_ratio take the largest hole diameter; plus the
    # smallest diameter of the smallest d_ratio
    picks = []
    for r in ratios:
        picks.append((r, diams[-1]))
    if (ratios[0], diams[0]) not in picks:
        picks.insert(0, (ratios[0], diams[0]))
    picks = picks[:4]
    fig, axes = plt.subplots(1, len(picks), figsize=(4.2 * len(picks), 4),
                             squeeze=False)
    for ax, (r, d) in zip(axes[0], picks):
        for v in ("off", "on"):
            ss = [s for s in series if float(s["d_ratio_target"]) == r
                  and float(s["D_target"]) == d and s["variant"] == v]
            if not ss:
                continue
            steps = ss[0]["steps"]
            arr = np.array([s["hole_area"] for s in ss], dtype=float) / 1e6
            m = arr.mean(axis=0)
            ax.plot(steps, m, color=VAR_COL[v], lw=1.6,
                    label="%s (n=%d)" % (VAR_LABEL[v], len(ss)))
        ax.set_xlabel("recovery step")
        ax.set_ylabel("hole area (km$^2$)")
        ax.set_title("d/C$_{th}$=%.1f, D=%dm" % (r, int(d)), fontsize=10)
        ax.legend(fontsize=7.5)
        ax.grid(True, color="#E6E6E6", lw=0.8)
    fig.suptitle("H6 representative recovery trajectories (hole area, seed-mean)",
                 y=1.02)
    fig.tight_layout()
    fig.savefig(FIG / "Fig_H6_timeseries.png")
    print("Fig_H6_timeseries ->", FIG / "Fig_H6_timeseries.png")


if __name__ == "__main__":
    fig_heatmaps()
    fig_timeseries()
    print("done")
