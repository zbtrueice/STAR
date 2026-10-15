# -*- coding: utf-8 -*-
"""make_figures_mech_verify.py -- Step1/2/3 comparison figures (reads the CSV/JSON under
results/mech_verify)."""
import csv
import io
import json
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent
RES = ROOT / "results" / "mech_verify"
FIG = ROOT / "figures" / "mech_verify"
FIG.mkdir(parents=True, exist_ok=True)

plt.rcParams.update({
    "font.family": "DejaVu Sans", "axes.edgecolor": "#333333",
    "axes.linewidth": 1.0, "axes.labelsize": 10.5, "axes.titlesize": 11,
    "xtick.labelsize": 9.5, "ytick.labelsize": 9.5, "legend.fontsize": 8.5,
    "figure.dpi": 100, "axes.grid": True, "grid.color": "#E6E6E6",
    "grid.linewidth": 0.8, "axes.axisbelow": True,
})
C_ON = "#1f77b4"; C_CAL = "#d62728"; C_OFF = "#7f7f7f"


def load_csv(name):
    p = RES / name
    if not p.exists():
        return []
    return list(csv.DictReader(io.open(p, encoding="utf-8")))


def fig_step1():
    rows = load_csv("s1_fluid_summary.csv")
    ts = load_csv("s1_fluid_timeseries.csv")
    ns = sorted({int(r["N"]) for r in rows})
    arms = ("off", "on", "cal")
    arm_label = {"off": "Fluid OFF", "on": "Fluid ON (literal)", "cal": "Fluid ON (calibrated)"}

    def agg(col):
        out = {}
        for a in arms:
            out[a] = []
            for n in ns:
                rs = [r for r in rows if r["N"] == str(n) and r["arm"] == a]
                out[a].append(float(np.mean([float(r[col]) for r in rs])))
        return out

    disp = agg("disp_mean"); nn = agg("nn1")
    cov = agg("cov1"); red = agg("red1")

    fig, axes = plt.subplots(2, 3, figsize=(13, 7.5))
    for a in arms:
        col = {"off": C_OFF, "on": C_ON, "cal": C_CAL}[a]
        axes[0, 0].plot(ns, disp[a], "-o", color=col, label=arm_label[a])
        axes[0, 1].plot(ns, nn[a], "-o", color=col, label=arm_label[a])
        axes[0, 2].plot(ns, cov[a], "-o", color=col, label=arm_label[a])
        axes[1, 0].plot(ns, red[a], "-o", color=col, label=arm_label[a])
    axes[0, 0].set_xlabel("N"); axes[0, 0].set_ylabel("mean displacement (m)")
    axes[0, 0].set_title("Fluid stage displacement")
    axes[0, 1].set_xlabel("N"); axes[0, 1].set_ylabel("mean NN distance (m)")
    axes[0, 1].set_title("spatial spread (fluid end)")
    axes[0, 2].set_xlabel("N"); axes[0, 2].set_ylabel("coverage")
    axes[0, 2].set_title("coverage (fluid end)")
    axes[1, 0].set_xlabel("N"); axes[1, 0].set_ylabel("redundancy (overlap ratio)")
    axes[1, 0].set_title("overlap / redundancy")
    axes[0, 0].legend(fontsize=8)

    # Time series (N=40 example): NN distance & displacement
    for a in arms:
        col = {"off": C_OFF, "on": C_ON, "cal": C_CAL}[a]
        s = [r for r in ts if r["N"] == "40" and r["seed"] == "42" and r["arm"] == a]
        st = [int(r["step"]) for r in s]
        axes[1, 1].plot(st, [float(r["nn_mean"]) for r in s], color=col, label=arm_label[a])
        axes[1, 2].plot(st, [float(r["disp_mean"]) for r in s], color=col, label=arm_label[a])
    axes[1, 1].set_xlabel("fluid step"); axes[1, 1].set_ylabel("mean NN distance (m)")
    axes[1, 1].set_title("N=40 seed42 NN evolution")
    axes[1, 1].legend(fontsize=8)
    axes[1, 2].set_xlabel("fluid step"); axes[1, 2].set_ylabel("mean displacement (m)")
    axes[1, 2].set_title("N=40 seed42 displacement")
    fig.tight_layout()
    fig.savefig(FIG / "FigM1_fluid_only.png")
    print("FigM1 ->", FIG / "FigM1_fluid_only.png")


def fig_step2():
    rows = load_csv("s2_ablation.csv")
    curves = load_csv("s2_ablation_curves.csv")
    combo_label = {"A_noF_noV": "A: noFluid noVEVF", "B_F_only": "B: Fluid only",
                   "C_V_only": "C: VEVF only", "D_F_V": "D: Fluid+VEVF",
                   "E_calF_V": "E: calFluid+VEVF"}
    order = ["A_noF_noV", "B_F_only", "C_V_only", "D_F_V", "E_calF_V"]
    colors = {"A_noF_noV": "#7f7f7f", "B_F_only": "#1f77b4",
              "C_V_only": "#ff7f0e", "D_F_V": "#2ca02c", "E_calF_V": "#d62728"}

    fig, axes = plt.subplots(2, 3, figsize=(13.5, 7.5))
    for ni, n in enumerate(("40", "100")):
        ax = axes[ni, 0]
        for c in order:
            s = [r for r in curves if r["N"] == n and r["combo"] == c]
            if not s:
                continue
            st = [int(r["step"]) for r in s]
            cv = [float(r["coverage"]) for r in s]
            ax.plot(st, cv, color=colors[c], label=combo_label[c], lw=1.6)
        ax.set_xlabel("step"); ax.set_ylabel("coverage")
        ax.set_title("coverage(t) N=%s" % n)
        ax.axvline(120, color="#999", ls=":", lw=1)
        ax.text(124, ax.get_ylim()[1] * 0.05 + ax.get_ylim()[0], "fluid_end",
                fontsize=7, color="#666")
        if ni == 0:
            ax.legend(fontsize=7.5, loc="lower right")
    # Final-value bars: coverage / fairness / t90
    for n, ax in ((40, axes[0, 1]), (100, axes[1, 1])):
        cs = order if n == 40 else ["A_noF_noV", "B_F_only", "C_V_only", "D_F_V"]
        cv = [np.mean([float(r["final_coverage"]) for r in rows
                       if r["combo"] == c and r["N"] == str(n)]) for c in cs]
        fa = [np.mean([float(r["fairness"]) for r in rows
                       if r["combo"] == c and r["N"] == str(n)]) for c in cs]
        x = np.arange(len(cs))
        ax.bar(x - 0.2, cv, 0.4, color=[colors[c] for c in cs], label="coverage")
        ax.bar(x + 0.2, fa, 0.4, color="#aaa", label="fairness")
        ax.set_xticks(x)
        ax.set_xticklabels([combo_label[c].split(":")[0] for c in cs], fontsize=8)
        ax.set_title("final coverage / fairness N=%s" % n)
        ax.legend(fontsize=7.5)
    for n, ax in ((40, axes[0, 2]), (100, axes[1, 2])):
        cs = order if n == 40 else ["A_noF_noV", "B_F_only", "C_V_only", "D_F_V"]
        t90 = [np.mean([float(r["t90"]) for r in rows
                        if r["combo"] == c and r["N"] == str(n)]) for c in cs]
        x = np.arange(len(cs))
        ax.bar(x, t90, 0.55, color=[colors[c] for c in cs])
        ax.set_xticks(x)
        ax.set_xticklabels([combo_label[c].split(":")[0] for c in cs], fontsize=8)
        ax.set_title("T90 (steps to 0.90) N=%s" % n)
    fig.tight_layout()
    fig.savefig(FIG / "FigM2_ablation.png")
    print("FigM2 ->", FIG / "FigM2_ablation.png")


def fig_step3():
    rows = load_csv("s3_hole.csv")
    ts = load_csv("s3_hole_timeseries.csv")
    tgt = sorted({int(r["target_diam"]) for r in rows})
    var_label = {"off": "HoleFill OFF", "on": "HoleFill ON"}
    var_col = {"off": "#ff7f0e", "on": "#2ca02c"}

    fig, axes = plt.subplots(2, 3, figsize=(13.5, 7.5))
    # Recovery curves: pick two representative diameters (smallest / a size with a
    # visible recovery difference)
    for pick in (min(tgt), 1000):
        ax = axes[0, 0]
        for var in ("off", "on"):
            s = [r for r in ts if r["target_diam"] == str(pick) and r["variant"] == var]
            if not s:
                continue
            st = [int(r["step"]) for r in s]
            ha = [float(r["hole_area"]) for r in s]
            # Average per step (3 seeds)
            sset = sorted({int(r["step"]) for r in s})
            hm = [np.mean([float(r["hole_area"]) for r in s if int(r["step"]) == t]) for t in sset]
            ax.plot(sset, hm, color=var_col[var], lw=1.6,
                    label="%s (d=%s)" % (var_label[var], pick))
        ax.set_xlabel("recovery step"); ax.set_ylabel("hole-zone uncovered area (m$^2$)")
        ax.set_title("hole area recovery (d=%s, 3-seed mean)" % pick)
        ax.legend(fontsize=7.5)
    # Recovery time vs achieved diameter
    for var in ("off", "on"):
        pts = [(float(r["achieved_diam"]), float(r["recovery_time"])) for r in rows
               if r["variant"] == var]
        pts.sort()
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        axes[0, 1].scatter(xs, ys, color=var_col[var], label=var_label[var], s=18)
    axes[0, 1].set_xlabel("achieved hole diameter (m)")
    axes[0, 1].set_ylabel("recovery time (steps, -1=none)")
    axes[0, 1].set_title("recovery time vs hole size")
    axes[0, 1].legend(fontsize=8)
    # Detection rate
    for var in ("on",):
        pts = [(float(r["achieved_diam"]), float(r["detection_rate"])) for r in rows
               if r["variant"] == var]
        pts.sort()
        axes[0, 2].plot([p[0] for p in pts], [p[1] for p in pts], "-o",
                        color=var_col[var], label=var_label[var])
    axes[0, 2].set_xlabel("achieved hole diameter (m)")
    axes[0, 2].set_ylabel("hole detection rate")
    axes[0, 2].set_title("HoleFill detection rate (ON)")
    axes[0, 2].legend(fontsize=8)
    # Final coverage & largest uncovered component
    for n, ax, metric in ((1, axes[1, 0], "final_coverage"),
                          (2, axes[1, 1], "final_largest_comp")):
        for var in ("off", "on"):
            pts = sorted((float(r["achieved_diam"]), float(r[metric]))
                         for r in rows if r["variant"] == var)
            ax.plot([p[0] for p in pts], [p[1] for p in pts], "-o", color=var_col[var],
                    label=var_label[var])
        ax.set_xlabel("achieved hole diameter (m)")
        ax.set_ylabel({"final_coverage": "final global coverage",
                       "final_largest_comp": "final largest uncovered comp (m$^2$)"}[metric])
        ax.set_title({"final_coverage": "final coverage vs hole size",
                      "final_largest_comp": "residual uncovered component"}[metric])
        ax.legend(fontsize=8)
    # Energy
    for var in ("off", "on"):
        pts = sorted((float(r["achieved_diam"]), float(r["energy_final"]))
                     for r in rows if r["variant"] == var)
        axes[1, 2].plot([p[0] for p in pts], [p[1] for p in pts], "-o",
                        color=var_col[var], label=var_label[var])
    axes[1, 2].set_xlabel("achieved hole diameter (m)")
    axes[1, 2].set_ylabel("recovery energy")
    axes[1, 2].set_title("recovery energy vs hole size")
    axes[1, 2].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(FIG / "FigM3_hole.png")
    print("FigM3 ->", FIG / "FigM3_hole.png")


if __name__ == "__main__":
    if (RES / "s1_fluid_summary.csv").exists():
        fig_step1()
    if (RES / "s2_ablation.csv").exists():
        fig_step2()
    if (RES / "s3_hole.csv").exists():
        fig_step3()
    print("done")
