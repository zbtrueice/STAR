# -*- coding: utf-8 -*-
"""make_figures_step5.py -- Step 5 F4/H4 figures (reads the CSV under
results/mech_verify/step5)."""
import csv
import io
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent
RES = ROOT / "results" / "mech_verify" / "step5"
FIG = ROOT / "figures" / "mech_verify" / "step5"
FIG.mkdir(parents=True, exist_ok=True)

plt.rcParams.update({
    "font.family": "DejaVu Sans", "axes.edgecolor": "#333333",
    "axes.linewidth": 1.0, "axes.labelsize": 10.5, "axes.titlesize": 11,
    "xtick.labelsize": 9.5, "ytick.labelsize": 9.5, "legend.fontsize": 8,
    "figure.dpi": 100, "axes.grid": True, "grid.color": "#E6E6E6",
    "grid.linewidth": 0.8, "axes.axisbelow": True,
})
C_VEVF = "#ff7f0e"
C_CAL = "#d62728"
ARM_COL = {"vevf": C_VEVF, "fluid_cal": C_CAL}
ARM_LABEL = {"vevf": "A: VEVF only", "fluid_cal": "B: Fluid(cal)+VEVF"}
VAR_COL = {"off": "#ff7f0e", "on": "#2ca02c"}
VAR_LABEL = {"off": "Hole OFF", "on": "Hole ON"}


def load_csv(name):
    p = RES / name
    if not p.exists():
        return []
    return list(csv.DictReader(io.open(p, encoding="utf-8")))


def mean_of(rows, col):
    return float(np.mean([float(r[col]) for r in rows]))


def fig_f4():
    rows = load_csv("F4_dense_init.csv")
    ts = load_csv("F4_dense_init_timeseries.csv")
    if not rows:
        return
    crs = sorted({int(r["cluster_radius"]) for r in rows})
    arms = ("vevf", "fluid_cal")
    fig, axes = plt.subplots(2, 3, figsize=(14, 8))
    # (a) overlap(t) -- core evidence for early crowding (cr=500 and 1500, 5-seed mean)
    ax = axes[0, 0]
    for cr in (crs[0], crs[-1]):
        for arm in arms:
            sset = sorted({int(r["step"]) for r in ts
                           if int(r["cluster_radius"]) == cr and r["arm"] == arm})
            m = [np.mean([float(r["overlap"]) for r in ts
                          if int(r["cluster_radius"]) == cr and r["arm"] == arm
                          and int(r["step"]) == t]) for t in sset]
            ax.plot(sset, m, color=ARM_COL[arm], lw=1.5,
                    ls="-" if cr == crs[0] else "--",
                    label="cr=%d %s" % (cr, ARM_LABEL[arm].split(":")[0].strip()))
    ax.axvline(120, color="#999", ls=":", lw=1)
    ax.set_xlabel("step"); ax.set_ylabel("overlap ratio")
    ax.set_title("overlap(t): early crowding (solid cr=500, dashed cr=%d)" % crs[-1])
    ax.legend(fontsize=7.5)
    # (b) cluster_radius_max(t) cr=500
    ax = axes[0, 1]
    for arm in arms:
        sset = sorted({int(r["step"]) for r in ts
                       if int(r["cluster_radius"]) == crs[0] and r["arm"] == arm})
        m = [np.mean([float(r["cluster_radius_max"]) for r in ts
                      if int(r["cluster_radius"]) == crs[0] and r["arm"] == arm
                      and int(r["step"]) == t]) for t in sset]
        ax.plot(sset, m, color=ARM_COL[arm], lw=1.5, label=ARM_LABEL[arm])
    ax.axhline(2000, color="#999", ls=":", lw=1)
    ax.text(2, 2050, "threshold 2000 m", fontsize=7, color="#666")
    ax.set_xlabel("step"); ax.set_ylabel("cluster radius max (m)")
    ax.set_title("swarm spread (cr=%d, 5-seed mean)" % crs[0])
    ax.legend(fontsize=7.5)
    # (c) T50/T90 vs cr
    ax = axes[0, 2]
    w = 0.35
    x = np.arange(len(crs))
    for i, (metric, lab) in enumerate((("T50", "T50"), ("T90", "T90"))):
        for j, arm in enumerate(arms):
            v = [mean_of([r for r in rows if int(r["cluster_radius"]) == cr
                          and r["arm"] == arm], metric) for cr in crs]
            ax.bar(x + (i - 0.5) * w + (j - 0.5) * w / 2, v, w / 2,
                   color=ARM_COL[arm] if metric == "T90" else None,
                   alpha=0.55 if metric == "T50" else 1.0,
                   label="%s %s" % (lab, ARM_LABEL[arm].split(":")[0].strip()))
    ax.set_xticks(x); ax.set_xticklabels(crs)
    ax.set_xlabel("cluster radius (m)"); ax.set_ylabel("steps")
    ax.set_title("T50 (light) / T90 (solid)")
    ax.legend(fontsize=7)
    # (d) first crossing of the 2000 m threshold vs cr
    ax = axes[1, 0]
    col = "t_cr_gt_2000"
    for arm in arms:
        v = [mean_of([r for r in rows if int(r["cluster_radius"]) == cr
                      and r["arm"] == arm], col) for cr in crs]
        axes[1, 0].plot(crs, v, marker="o", color=ARM_COL[arm], lw=1.6,
                        label=ARM_LABEL[arm])
    ax.set_xlabel("cluster radius (m)")
    ax.set_ylabel("first step cluster radius > 2000 m")
    ax.set_title("escape time (threshold 2000 m)")
    ax.legend()
    # (e) final coverage vs cr
    ax = axes[1, 1]
    for arm in arms:
        v = [mean_of([r for r in rows if int(r["cluster_radius"]) == cr
                      and r["arm"] == arm], "final_coverage") for cr in crs]
        ax.plot(crs, v, marker="o", color=ARM_COL[arm], lw=1.6,
                label=ARM_LABEL[arm])
    ax.set_xlabel("cluster radius (m)"); ax.set_ylabel("final coverage")
    ax.set_title("final coverage vs launch radius")
    ax.legend()
    # (f) gap vs cr
    ax = axes[1, 2]
    for arm in arms:
        v = [mean_of([r for r in rows if int(r["cluster_radius"]) == cr
                      and r["arm"] == arm], "gap_m") for cr in crs]
        ax.plot(crs, v, marker="o", color=ARM_COL[arm], lw=1.6,
                label=ARM_LABEL[arm])
    ax.set_xlabel("cluster radius (m)"); ax.set_ylabel("minimax gap (m)")
    ax.set_title("final minimax gap")
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIG / "Fig_F4.png")
    print("Fig_F4 ->", FIG / "Fig_F4.png")


def fig_h4():
    rows = load_csv("H4_isolated_hole.csv")
    ts = load_csv("H4_isolated_hole_timeseries.csv")
    if not rows:
        return
    fig, axes = plt.subplots(1, 4, figsize=(16, 4))
    # (a) hole area(t)
    ax = axes[0]
    for v in ("off", "on"):
        sset = sorted({int(r["step"]) for r in ts if r["variant"] == v})
        m = [np.mean([float(r["hole_area"]) for r in ts
                      if r["variant"] == v and int(r["step"]) == t]) / 1e6
             for t in sset]
        ax.plot(sset, m, color=VAR_COL[v], lw=1.6, label=VAR_LABEL[v])
    ax.set_xlabel("recovery step"); ax.set_ylabel("hole area (km$^2$)")
    ax.set_title("isolated hole area(t) (3-seed mean)")
    ax.legend()
    # (b) largest component(t)
    ax = axes[1]
    for v in ("off", "on"):
        sset = sorted({int(r["step"]) for r in ts if r["variant"] == v})
        m = [np.mean([float(r["largest_comp"]) for r in ts
                      if r["variant"] == v and int(r["step"]) == t]) / 1e6
             for t in sset]
        ax.plot(sset, m, color=VAR_COL[v], lw=1.6, label=VAR_LABEL[v])
    ax.set_xlabel("recovery step"); ax.set_ylabel("largest uncovered comp (km$^2$)")
    ax.set_title("largest uncovered component(t)")
    ax.legend()
    # (c) detection & success
    ax = axes[2]
    x = np.arange(2)
    det = [mean_of([r for r in rows if r["variant"] == v], "detection_rate")
           for v in ("off", "on")]
    suc = [mean_of([r for r in rows if r["variant"] == v], "recovery_success")
           for v in ("off", "on")]
    ax.bar(x - 0.2, det, 0.4, color="#1f77b4", label="detection rate")
    ax.bar(x + 0.2, suc, 0.4, color="#2ca02c", label="recovery success")
    ax.set_xticks(x); ax.set_xticklabels(["OFF", "ON"])
    ax.set_ylim(0, 1.05); ax.set_ylabel("rate")
    ax.set_title("detection / recovery success")
    ax.legend()
    # (d) residual & final coverage
    ax = axes[3]
    res_a = [mean_of([r for r in rows if r["variant"] == v], "final_hole_area") / 1e6
             for v in ("off", "on")]
    cov = [mean_of([r for r in rows if r["variant"] == v], "final_coverage")
           for v in ("off", "on")]
    ax.bar(x - 0.2, res_a, 0.4, color="#888", label="residual area (km$^2$)")
    for i, c in enumerate(cov):
        ax.text(i + 0.2, 0.05, "%.4f" % c, ha="center", fontsize=8, rotation=90)
        ax.bar([i + 0.2], [c], 0.4, color="#2ca02c", alpha=0.6,
               label="final coverage" if i == 0 else None)
    ax.set_xticks(x); ax.set_xticklabels(["OFF", "ON"])
    ax.set_ylabel("km$^2$ / coverage")
    ax.set_title("residual hole / final coverage")
    ax.legend(fontsize=7.5)
    fig.tight_layout()
    fig.savefig(FIG / "Fig_H4.png")
    print("Fig_H4 ->", FIG / "Fig_H4.png")


if __name__ == "__main__":
    fig_f4()
    fig_h4()
    print("done")
