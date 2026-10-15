# -*- coding: utf-8 -*-
"""make_figures_step4.py -- Step 4 operating-regime figures (reads the CSV under
results/mech_verify/step4)."""
import csv
import io
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent
RES = ROOT / "results" / "mech_verify" / "step4"
FIG = ROOT / "figures" / "mech_verify" / "step4"
FIG.mkdir(parents=True, exist_ok=True)

plt.rcParams.update({
    "font.family": "DejaVu Sans", "axes.edgecolor": "#333333",
    "axes.linewidth": 1.0, "axes.labelsize": 10.5, "axes.titlesize": 11,
    "xtick.labelsize": 9.5, "ytick.labelsize": 9.5, "legend.fontsize": 8,
    "figure.dpi": 100, "axes.grid": True, "grid.color": "#E6E6E6",
    "grid.linewidth": 0.8, "axes.axisbelow": True,
})
C_VEVF = "#ff7f0e"     # VEVF only
C_LIT = "#1f77b4"      # Fluid(literal)+VEVF
C_CAL = "#d62728"      # Fluid(calibrated)+VEVF
ARM_COL = {"vevf": C_VEVF, "fluid_lit": C_LIT, "fluid_cal": C_CAL}
ARM_LABEL = {"vevf": "VEVF", "fluid_lit": "Fluid(lit)+VEVF",
             "fluid_cal": "Fluid(cal)+VEVF"}


def load_csv(name):
    p = RES / name
    if not p.exists():
        return []
    return list(csv.DictReader(io.open(p, encoding="utf-8")))


def mean_by(rows, key, col):
    out = {}
    for r in rows:
        out.setdefault(r[key], []).append(float(r[col]))
    return {k: float(np.mean(v)) for k, v in out.items()}


def sd_by(rows, key, col):
    out = {}
    for r in rows:
        out.setdefault(r[key], []).append(float(r[col]))
    return {k: float(np.std(v)) for k, v in out.items()}


def line(ax, xs, ys, color, label, marker="o"):
    ax.plot(xs, ys, marker=marker, color=color, label=label, lw=1.6, ms=4)


# --------------------------------------------------------------------------- #
def fig_f2():
    rows = load_csv("F2_dense_cluster.csv")
    ts = load_csv("F2_dense_cluster_timeseries.csv")
    if not rows:
        return
    crs = sorted({int(r["cluster_radius"]) for r in rows})
    arms = ("vevf", "fluid_lit", "fluid_cal")
    fig, axes = plt.subplots(2, 3, figsize=(14, 8))
    # (a) coverage(t) for cr=min & max (3 arms, 5-seed mean)
    ax = axes[0, 0]
    for cr in (crs[0], crs[-1]):
        for arm in arms:
            sset = sorted({int(r["step"]) for r in ts
                           if int(r["cluster_radius"]) == cr and r["arm"] == arm})
            m = [np.mean([float(r["coverage"]) for r in ts
                          if int(r["cluster_radius"]) == cr and r["arm"] == arm
                          and int(r["step"]) == t]) for t in sset]
            ax.plot(sset, m, color=ARM_COL[arm], lw=1.5,
                    label=("%s cr=%d" % (ARM_LABEL[arm], cr)) if cr == crs[0] else None)
    ax.axvline(120, color="#999", ls=":", lw=1)
    ax.set_xlabel("step"); ax.set_ylabel("coverage")
    ax.set_title("coverage(t), cr=%d/%d" % (crs[0], crs[-1]))
    ax.legend(fontsize=7.5)
    # (b) T90 vs cluster_radius
    for arm in arms:
        m = mean_by([r for r in rows if r["arm"] == arm], "cluster_radius", "T90")
        line(axes[0, 1], [m[str(c)] for c in crs], crs, ARM_COL[arm], ARM_LABEL[arm])
    axes[0, 1].set_xlabel("cluster radius (m)"); axes[0, 1].set_ylabel("T90 (steps)")
    axes[0, 1].set_title("T90 vs launch cluster radius")
    axes[0, 1].legend()
    # (c) final coverage vs cluster_radius
    for arm in arms:
        m = mean_by([r for r in rows if r["arm"] == arm], "cluster_radius",
                    "final_coverage")
        line(axes[0, 2], [m[str(c)] for c in crs], crs, ARM_COL[arm], ARM_LABEL[arm])
    axes[0, 2].set_xlabel("cluster radius (m)"); axes[0, 2].set_ylabel("final coverage")
    axes[0, 2].set_title("final coverage vs launch radius")
    # (d) gap vs cluster_radius
    for arm in arms:
        m = mean_by([r for r in rows if r["arm"] == arm], "cluster_radius", "gap_m")
        line(axes[1, 0], [m[str(c)] for c in crs], crs, ARM_COL[arm], ARM_LABEL[arm])
    axes[1, 0].set_xlabel("cluster radius (m)"); axes[1, 0].set_ylabel("minimax gap (m)")
    axes[1, 0].set_title("final minimax gap vs launch radius")
    axes[1, 0].legend()
    # (e) cluster_radius_max(t), representative seed (cr=500, seed42)
    ax = axes[1, 1]
    for arm in arms:
        s = [r for r in ts if int(r["cluster_radius"]) == crs[0]
             and r["arm"] == arm and r["seed"] == "42"]
        ax.plot([int(r["step"]) for r in s],
                [float(r["cluster_radius_max"]) for r in s],
                color=ARM_COL[arm], label=ARM_LABEL[arm], lw=1.5)
    ax.set_xlabel("step"); ax.set_ylabel("cluster radius max (m)")
    ax.set_title("swarm spread (cr=%d, seed42)" % crs[0])
    ax.legend(fontsize=7.5)
    # (f) mean NN(t), representative seed
    ax = axes[1, 2]
    for arm in arms:
        s = [r for r in ts if int(r["cluster_radius"]) == crs[0]
             and r["arm"] == arm and r["seed"] == "42"]
        ax.plot([int(r["step"]) for r in s], [float(r["nn_mean"]) for r in s],
                color=ARM_COL[arm], label=ARM_LABEL[arm], lw=1.5)
    ax.set_xlabel("step"); ax.set_ylabel("mean NN distance (m)")
    ax.set_title("mean NN distance (cr=%d, seed42)" % crs[0])
    ax.legend(fontsize=7.5)
    fig.tight_layout()
    fig.savefig(FIG / "FigF2_dense_cluster.png")
    print("FigF2 ->", FIG / "FigF2_dense_cluster.png")


def fig_f3():
    rows = load_csv("F3_packet_loss.csv")
    if not rows:
        return
    drops = sorted({float(r["packet_loss"]) for r in rows})
    arms = ("vevf", "fluid_lit", "fluid_cal")
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.2))
    for arm in arms:
        rs = [r for r in rows if r["arm"] == arm]
        m = mean_by(rs, "packet_loss", "final_coverage")
        s = sd_by(rs, "packet_loss", "final_coverage")
        xs = [m[str(d)] for d in drops]
        axes[0].errorbar(drops, xs, yerr=[s[str(d)] for d in drops],
                         color=ARM_COL[arm], marker="o", capsize=3,
                         label=ARM_LABEL[arm], lw=1.6)
        t = mean_by(rs, "packet_loss", "T90")
        line(axes[1], drops, [t[str(d)] for d in drops], ARM_COL[arm], ARM_LABEL[arm])
        fr = {d: float(np.mean([float(r["failed"]) for r in rs
                                if r["packet_loss"] == str(d)])) for d in drops}
        line(axes[2], drops, [fr[d] for d in drops], ARM_COL[arm], ARM_LABEL[arm])
    for ax, yl, ti in ((axes[0], "final coverage", "coverage vs packet loss"),
                       (axes[1], "T90 (steps)", "T90 vs packet loss"),
                       (axes[2], "failure rate", "failure rate (seeds not reaching 0.90)")):
        ax.set_xlabel("packet loss"); ax.set_ylabel(yl); ax.set_title(ti)
    axes[0].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(FIG / "FigF3_packet_loss.png")
    print("FigF3 ->", FIG / "FigF3_packet_loss.png")


def fig_h2():
    rows = load_csv("H2_operating_regime.csv")
    if not rows:
        return
    positions = ("center", "boundary", "sparse_edge")
    pos_label = {"center": "center", "boundary": "boundary", "sparse_edge": "sparse-edge"}
    pos_col = {"center": "#2ca02c", "boundary": "#9467bd", "sparse_edge": "#ff7f0e"}
    vars_ = ("off", "on")
    var_ls = {"off": "--", "on": "-"}
    var_label = {"off": "Hole OFF", "on": "Hole ON"}
    diam = sorted({int(r["target_diam"]) for r in rows})

    fig, axes = plt.subplots(2, 3, figsize=(14, 8))
    # (a) recovery time vs target diam (by position; on/off dashed)
    ax = axes[0, 0]
    for p in positions:
        for v in vars_:
            m = mean_by([r for r in rows if r["position"] == p and r["variant"] == v],
                        "target_diam", "recovery_time")
            ax.plot(diam, [m[str(d)] for d in diam], color=pos_col[p],
                    ls=var_ls[v], marker="o", ms=4, lw=1.5,
                    label="%s %s" % (pos_label[p], var_label[v]))
    ax.set_xlabel("target hole diameter (m)"); ax.set_ylabel("recovery time (steps)")
    ax.set_title("recovery time (3-seed mean, N pooled)")
    ax.legend(fontsize=7, ncol=2)
    # (b) residual hole area
    ax = axes[0, 1]
    for p in positions:
        for v in vars_:
            m = mean_by([r for r in rows if r["position"] == p and r["variant"] == v],
                        "target_diam", "final_hole_area")
            ax.plot(diam, [m[str(d)] / 1e6 for d in diam], color=pos_col[p],
                    ls=var_ls[v], marker="o", ms=4, lw=1.5,
                    label="%s %s" % (pos_label[p], var_label[v]))
    ax.set_xlabel("target hole diameter (m)"); ax.set_ylabel("residual hole area (km$^2$)")
    ax.set_title("residual hole area")
    ax.legend(fontsize=7, ncol=2)
    # (c) detection rate (ON only)
    ax = axes[0, 2]
    for p in positions:
        m = mean_by([r for r in rows if r["position"] == p and r["variant"] == "on"],
                    "target_diam", "detection_rate")
        ax.plot(diam, [m[str(d)] for d in diam], color=pos_col[p], marker="o",
                ms=4, lw=1.5, label=pos_label[p])
    ax.set_xlabel("target hole diameter (m)"); ax.set_ylabel("detection rate")
    ax.set_title("HoleFill detection rate (ON)")
    ax.legend()
    # (d) final coverage by N
    ax = axes[1, 0]
    for nn in ("20", "30", "40"):
        m = mean_by([r for r in rows if r["N"] == nn and r["variant"] == "on"],
                    "target_diam", "final_coverage")
        mb = mean_by([r for r in rows if r["N"] == nn and r["variant"] == "off"],
                     "target_diam", "final_coverage")
        ax.plot(diam, [m[str(d)] for d in diam], marker="o", ms=4, lw=1.5,
                label="N=%s ON" % nn, color="#2ca02c")
        ax.plot(diam, [mb[str(d)] for d in diam], ls="--", marker="o", ms=4, lw=1.4,
                label="N=%s OFF" % nn, color="#999")
    ax.set_xlabel("target hole diameter (m)"); ax.set_ylabel("final coverage")
    ax.set_title("final coverage (all positions pooled)")
    ax.legend(fontsize=7.5)
    # (e) recovery time vs N (ON/OFF, all diam pooled)
    ax = axes[1, 1]
    for v in vars_:
        for nn in ("20", "30", "40"):
            rs = [r for r in rows if r["N"] == nn and r["variant"] == v]
            m = float(np.mean([float(r["recovery_time"]) for r in rs
                               if float(r["recovery_time"]) >= 0]))
            ax.bar([int(nn)], [m], width=0.6, color="#2ca02c" if v == "on" else "#aaa",
                   alpha=0.75 if v == "on" else 0.5)
    ax.set_xlabel("N"); ax.set_ylabel("mean recovery time (steps)")
    ax.set_title("mean recovery time vs N (recovered only)")
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(color="#2ca02c", label="Hole ON"),
                       Patch(color="#aaa", label="Hole OFF")], fontsize=7.5)
    # (f) largest uncovered component at end
    ax = axes[1, 2]
    for p in positions:
        for v in vars_:
            m = mean_by([r for r in rows if r["position"] == p and r["variant"] == v],
                        "target_diam", "final_largest_comp")
            ax.plot(diam, [m[str(d)] / 1e6 for d in diam], color=pos_col[p],
                    ls=var_ls[v], marker="o", ms=4, lw=1.5,
                    label="%s %s" % (pos_label[p], var_label[v]))
    ax.set_xlabel("target hole diameter (m)")
    ax.set_ylabel("largest uncovered comp (km$^2$)")
    ax.set_title("final largest uncovered component")
    ax.legend(fontsize=7, ncol=2)
    fig.tight_layout()
    fig.savefig(FIG / "FigH2_operating_regime.png")
    print("FigH2 ->", FIG / "FigH2_operating_regime.png")


def fig_h3():
    rows = load_csv("H3_force_sweep.csv")
    if not rows:
        return
    fm = sorted({float(r["hole_fmax"]) for r in rows})
    fig, axes = plt.subplots(1, 5, figsize=(16, 3.6))
    panels = [("recovery_time", "recovery time (steps)"),
              ("final_hole_area", "residual hole area"),
              ("final_coverage", "final coverage"),
              ("energy", "energy"),
              ("oscillation_count", "oscillation count")]
    for ax, (col, yl) in zip(axes, panels):
        v = {float(k): val for k, val in mean_by(rows, "hole_fmax", col).items()}
        ax.plot(fm, [v[x] for x in fm], marker="o", color="#d62728", lw=1.6)
        ax.set_xlabel("hole-fill f_max"); ax.set_ylabel(yl)
        ax.set_title(yl)
    fig.suptitle("H3 hole force-conflict sweep (fixed layout/hole/seed)", y=1.03)
    fig.tight_layout()
    fig.savefig(FIG / "FigH3_force_sweep.png")
    print("FigH3 ->", FIG / "FigH3_force_sweep.png")


if __name__ == "__main__":
    fig_f2()
    fig_f3()
    fig_h2()
    fig_h3()
    print("done")
