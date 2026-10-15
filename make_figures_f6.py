# -*- coding: utf-8 -*-
"""make_figures_f6.py -- F6 parameter-robustness figures (reads the CSV under
results/mech_verify/F6)."""
import csv
import io
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent
RES = ROOT / "results" / "mech_verify" / "F6"
FIG = ROOT / "figures" / "mech_verify" / "F6"
FIG.mkdir(parents=True, exist_ok=True)

plt.rcParams.update({
    "font.family": "DejaVu Sans", "axes.edgecolor": "#333333",
    "axes.linewidth": 1.0, "axes.labelsize": 10.5, "axes.titlesize": 11,
    "xtick.labelsize": 9.5, "ytick.labelsize": 9.5, "legend.fontsize": 8.5,
    "figure.dpi": 100, "axes.grid": True, "grid.color": "#E6E6E6",
    "grid.linewidth": 0.8, "axes.axisbelow": True,
})
CR_COL = {500: "#ff7f0e", 1000: "#1f77b4"}
CR_LABEL = {500: "cluster radius 500 m", 1000: "cluster radius 1000 m"}


def load_csv(name):
    return list(csv.DictReader(io.open(RES / name, encoding="utf-8")))


def main():
    summ = load_csv("F6_summary.csv")
    if not summ:
        print("no F6_summary.csv")
        return
    mults = sorted({float(r["k_mult"]) for r in summ})
    crs = sorted({int(r["cluster_radius"]) for r in summ})
    xticklabels = ["0\n(VEVF-only)"] + [f"{m:g}x" for m in mults[1:]]

    fig, axes = plt.subplots(2, 3, figsize=(14.5, 8))
    panels = [
        ("final_coverage_mean", "final_coverage_sd", "final coverage",
         "coverage vs k"),
        ("T90_mean", "T90_sd", "T90 (steps)", "T90 vs k"),
        ("gap_m_mean", "gap_m_sd", "minimax gap (m)", "gap vs k"),
        ("energy_final_mean", "energy_final_sd", "energy (final)",
         "energy vs k"),
    ]
    for ax, (mcol, scol, yl, ti) in zip([a for row in axes[:2] for a in row][:4],
                                        panels):
        for cr in crs:
            rs = sorted([r for r in summ if int(r["cluster_radius"]) == cr],
                        key=lambda r: float(r["k_mult"]))
            xs = [float(r["k_mult"]) for r in rs]
            m = [float(r[mcol]) for r in rs]
            s = [float(r[scol]) for r in rs]
            ax.errorbar(xs, m, yerr=s, marker="o", ms=5, capsize=3, lw=1.6,
                        color=CR_COL[cr], label=CR_LABEL[cr])
        ax.set_xticks(mults)
        ax.set_xticklabels(xticklabels)
        ax.set_xlabel("k_fluid multiplier (base 1.9367e6)")
        ax.set_ylabel(yl)
        ax.set_title(ti)
    axes[0, 0].legend(fontsize=8)

    # (e) force magnitude vs k (fluid arms only)
    ax = axes[1, 0]
    for cr in crs:
        rs = sorted([r for r in summ if int(r["cluster_radius"]) == cr
                     and float(r["k_mult"]) > 0],
                    key=lambda r: float(r["k_mult"]))
        xs = [float(r["k_mult"]) for r in rs]
        ax.plot(xs, [float(r["force_mean_mean"]) for r in rs], "-o", ms=5,
                color=CR_COL[cr], label=f"{CR_LABEL[cr]} mean")
        ax.plot(xs, [float(r["force_p95_mean"]) for r in rs], "--s", ms=4,
                color=CR_COL[cr], alpha=0.65, label=f"{CR_LABEL[cr]} p95")
        ax.plot(xs, [float(r["force_max_mean"]) for r in rs], ":^", ms=4,
                color=CR_COL[cr], alpha=0.65, label=f"{CR_LABEL[cr]} max")
    ax.set_xticks(mults[1:])
    ax.set_xticklabels(xticklabels[1:])
    ax.set_xlabel("k_fluid multiplier")
    ax.set_ylabel("fluid force |F| (per-agent norm)")
    ax.set_title("fluid force magnitude vs k")
    ax.legend(fontsize=6.5)
    ax.set_yscale("log")

    # (f) paired Delta coverage / Delta T90 vs k (relative to VEVF-only)
    ax = axes[1, 1]
    for cr in crs:
        rs = sorted([r for r in summ if int(r["cluster_radius"]) == cr
                     and "delta_final_coverage_mean" in r
                     and r["delta_final_coverage_mean"] != ""],
                    key=lambda r: float(r["k_mult"]))
        xs = [float(r["k_mult"]) for r in rs]
        ax.errorbar(xs, [float(r["delta_final_coverage_mean"]) for r in rs],
                    yerr=[float(r["delta_final_coverage_sd"]) for r in rs],
                    marker="o", ms=5, capsize=3, lw=1.6, color=CR_COL[cr],
                    label=f"dCov {CR_LABEL[cr]}")
    ax.axhline(0, color="#999", lw=0.8)
    ax.set_xticks(mults[1:])
    ax.set_xticklabels(xticklabels[1:])
    ax.set_xlabel("k_fluid multiplier")
    ax.set_ylabel("paired Δcoverage vs VEVF-only")
    ax.set_title("Δcoverage vs k (paired)")
    ax.legend(fontsize=7.5)

    # (g) Delta T90 (annotation text panel)
    ax = axes[1, 2]
    for cr in crs:
        rs = sorted([r for r in summ if int(r["cluster_radius"]) == cr
                     and r.get("delta_T90_mean", "") != ""],
                    key=lambda r: float(r["k_mult"]))
        xs = [float(r["k_mult"]) for r in rs]
        ax.errorbar(xs, [float(r["delta_T90_mean"]) for r in rs],
                    yerr=[float(r["delta_T90_sd"]) for r in rs],
                    marker="o", ms=5, capsize=3, lw=1.6, color=CR_COL[cr],
                    label=f"dT90 {CR_LABEL[cr]}")
    ax.axhline(0, color="#999", lw=0.8)
    ax.set_xticks(mults[1:])
    ax.set_xticklabels(xticklabels[1:])
    ax.set_xlabel("k_fluid multiplier")
    ax.set_ylabel("paired ΔT90 vs VEVF-only (steps)")
    ax.set_title("ΔT90 vs k (paired)")
    ax.legend(fontsize=7.5)

    fig.tight_layout()
    out = FIG / "Fig_F6.png"
    fig.savefig(out)
    print("Fig_F6 ->", out)


if __name__ == "__main__":
    main()
