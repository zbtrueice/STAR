# -*- coding: utf-8 -*-
"""
make_figures_sci.py -- SCI multi-panel composite experimental figures (grouped by the
paper's contributions).

Groups the project's existing experimental figures into five composite
multi-panel figures, ordered to match the paper (§7.2-7.5) and its three
contributions. Reads ONLY existing data -- no simulation re-run.

  FigR1  deployment process & convergence   (§7.2, contrib 1+3)
         (a-h) STAR/Lloyd evolution hotspot snapshots x 4 phases
         (i)   5-method coverage convergence, mean+-SD shadow
  FigR2  mechanism: fluid self-diffusion + Laguerre partition (contrib 1+2, §5)
         (a-b) SPH pressure field + compression-force arrows
         (c)   MW-Voronoi partition, cell colour = sensing radius
  FigR3  benchmark performance & allocation quality (§7.2/7.3/7.5)
         (a-b) benchmark bars + significance (N=40/100)
         (c)   6-metric radar (incl. fairness + energy)
         (d)   effect-size forest (STAR vs baselines, 95% CI)
  FigR4  robustness & scalability sweeps (full-axis shadows, STAR+baselines)
         (a) comm radius (b) packet loss (c) swarm size
  FigR5  ablation (§7.4): (a) coverage contribution (b) reliability

Output -> v3/figures/beauty3/
"""
import csv
import io
import json
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import yaml

ROOT = Path(__file__).resolve().parent.parent   # repo root (script lives in figures/)
RES  = ROOT / "results"
DEMO = RES / "demo_figs"
STAR_CSV = RES / "suite" / "all_runs.csv"
SIG_CSV  = RES / "suite" / "significance_tests.csv"
FAIR = RES / "fairness_gap.json"
OUT  = ROOT / "figures" / "beauty3"
OUT.mkdir(parents=True, exist_ok=True)

SEEDS = [42, 7, 123, 2024, 555, 777, 1000, 2025, 666, 314, 2026, 888]
COLORS = {"star": "#E63946", "lloyd": "#457B9D", "pso": "#2A9D8F",
          "vfa": "#E9C46A", "random": "#9AA5B1"}
LAB = {"star": "STAR", "lloyd": "Lloyd", "pso": "PSO", "vfa": "VFA", "random": "Random"}
ORDER = ["star", "lloyd", "pso", "vfa", "random"]

plt.rcParams.update({
    "font.family": "DejaVu Sans", "axes.edgecolor": "#333333",
    "axes.linewidth": 1.0, "axes.labelsize": 10.5, "axes.titlesize": 11,
    "xtick.labelsize": 9.5, "ytick.labelsize": 9.5, "legend.fontsize": 8.5,
    "figure.dpi": 100, "axes.grid": True, "grid.color": "#E6E6E6",
    "grid.linewidth": 0.8, "axes.axisbelow": True,
})

with io.open(ROOT / "configs" / "default.yaml", encoding="utf-8") as f:
    CFG = yaml.safe_load(f)
ENV, U = CFG["environment"], CFG["usv"]


def save(fig, name):
    for fmt, kw in (("png", dict(dpi=300)), ("pdf", {})):
        tgt = OUT / f"{name}.{fmt}"
        tmp = OUT / f".{name}.tmp.{fmt}"
        fig.savefig(tmp, format=fmt, bbox_inches="tight", **kw)
        try:
            tmp.replace(tgt)
        except OSError:
            tmp.replace(OUT / f"{name}.new.{fmt}")
    plt.close(fig)
    print("  wrote", OUT / f"{name}.png")


def clean(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)


def plabel(ax, letter, dx=-0.06, dy=1.04):
    ax.text(dx, dy, letter, transform=ax.transAxes, fontsize=13,
            fontweight="bold", va="bottom", ha="right")


def radii_for(n):
    nh = round(n * U["high_ratio"]); nm = round(n * U["medium_ratio"]); nl = n - nh - nm
    return np.array([U["high_radius"]] * nh + [U["medium_radius"]] * nm
                    + [U["low_radius"]] * nl)


def _grid2d(step=100):
    w = ENV["width"]
    xs = np.linspace(step / 2, w - step / 2, int(w / step))
    gx, gy = np.meshgrid(xs, xs)
    return gx, gy, np.column_stack([gx.ravel(), gy.ravel()])


def redundancy(pos, rad, step=100):
    gx, gy, grid = _grid2d(step)
    H = np.zeros(len(grid))
    for c, r in zip(pos, rad):
        H += (np.sum((grid - c) ** 2, axis=1) <= r * r)
    return gx, gy, H.reshape(gx.shape)


def coverage_approx(p, rad, step=250):
    _, _, H = redundancy(p, rad, step=step)
    return float((H > 0).mean())


def load_star_rows():
    with io.open(STAR_CSV, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_sweep_rows():
    fp = DEMO / "sweep_all.csv"
    return list(csv.DictReader(io.open(fp, encoding="utf-8"))) if fp.exists() else []


# --------------------------------------------------------------------------- #
#  panels -- FigR1
# --------------------------------------------------------------------------- #
def panel_snapshot(ax, pos, rad, title):
    gx, gy, H = redundancy(pos, rad, step=100)
    pcm = ax.pcolormesh(gx, gy, H, cmap="magma_r", shading="auto", vmin=0)
    ax.scatter(pos[:, 0], pos[:, 1], c="white", s=9, edgecolors="#111",
               linewidths=0.3, zorder=5)
    for c, r in zip(pos, rad):
        ax.add_patch(mpatches.Circle(c, r, fill=False, edgecolor="#FFF",
                                     alpha=0.30, lw=0.4, zorder=4))
    cov = coverage_approx(pos, rad)
    ax.set_title(title, fontsize=9.5)
    ax.set_aspect("equal"); ax.tick_params(labelleft=False, labelbottom=False)
    clean(ax)
    return pcm


def fig_R1(n=40):
    ph = ["Launch", "Fluid", "Fluid end", "Refined"]
    rows = [("star", "STAR"), ("lloyd", "Lloyd")]
    fig = plt.figure(figsize=(17, 12.4))
    gs = fig.add_gridspec(3, 4, height_ratios=[1, 1, 0.78], hspace=0.22, wspace=0.06)
    letters = iter("abcdefghi")
    pcm = None
    for ri, (m, mlabel) in enumerate(rows):
        d = np.load(DEMO / f"snapshots_{m}_{n}_{SEEDS[0]}.npz", allow_pickle=True)
        steps, pos = d["steps"], d["pos"]
        rad = radii_for(n)
        for ci in range(4):
            ax = fig.add_subplot(gs[ri, ci])
            pcm = panel_snapshot(ax, pos[ci], rad,
                                 f"{ph[ci]}  (step {int(steps[ci])}, cov={coverage_approx(pos[ci], rad):.2f})")
            plabel(ax, f"({next(letters)})", dx=-0.02)
            if ci == 0:
                ax.set_ylabel(mlabel, fontsize=13, fontweight="bold",
                              rotation=90, labelpad=14)
    cb = fig.colorbar(pcm, ax=fig.axes[3], shrink=0.82, pad=0.02)
    cb.set_label("Coverage redundancy (#disks/point)", fontsize=9)

    # (i) convergence shadow, 12 seeds
    ax = fig.add_subplot(gs[2, :])
    for m in ORDER:
        curves, T = [], None
        for sd in SEEDS:
            fp = DEMO / f"convergence_{n}_{sd}.npz"
            if not fp.exists():
                continue
            d = np.load(fp)
            names = [str(x) for x in d["methods"]]
            if m not in names:
                continue
            curves.append(d["cov"][names.index(m)])
            T = np.asarray(d["steps"], dtype=float)
        if not curves:
            continue
        C = np.vstack(curves)
        mu, sd_ = C.mean(0), C.std(0)
        ax.plot(T, mu, color=COLORS[m], lw=2.3, label=LAB[m], zorder=3)
        ax.fill_between(T, mu - sd_, mu + sd_, color=COLORS[m], alpha=0.16, zorder=2)
    ax.axvspan(0, 120, color="#2A9D8F", alpha=0.07)
    ax.axvspan(120, 400, color="#E9C46A", alpha=0.07)
    ylo, yhi = ax.get_ylim()
    ax.text(60, ylo + 0.015 * (yhi - ylo), "fluid self-diffusion", fontsize=9,
            color="#2A9D8F", ha="center", va="bottom")
    ax.text(260, ylo + 0.015 * (yhi - ylo), "VEVF refinement", fontsize=9,
            color="#B09A3F", ha="center", va="bottom")
    ax.axhline(0.90, color="#555", ls="--", lw=1, alpha=0.7)
    ax.text(398, 0.905, "target 0.90", fontsize=8, color="#555", va="bottom", ha="right")
    ax.set_xlabel("Iteration step"); ax.set_ylabel(r"Coverage $\bar{F}$")
    ax.set_ylim(0, 1.05); ax.set_xlim(0, 400)
    ax.legend(loc="lower right", frameon=True, ncol=5)
    clean(ax)
    plabel(ax, "(i)", dx=0.005)
    fig.suptitle("Deployment process and convergence — dense launch, fluid "
                 "self-diffusion, VEVF refinement  (N=40, 12 seeds)",
                 fontsize=14.5, fontweight="bold", y=0.995)
    save(fig, "FigR1_process_convergence")


# --------------------------------------------------------------------------- #
#  panels -- FigR2
# --------------------------------------------------------------------------- #
def _fluid_density(pos, rad, fp, step=100):
    """Kernel mass-density (no rest-mass subtraction) -- shows where mass sits."""
    h = fp["interaction_radius"]
    gx, gy, grid = _grid2d(step)
    dens = np.zeros(len(grid))
    for c, r in zip(pos, rad):
        d = np.linalg.norm(grid - c, axis=1)
        q = np.clip(d / h, 0.0, 1.0)
        dens += (1.0 - 1.5 * q ** 2 + 0.75 * q ** 3) / (np.pi * h * h)
    return gx, gy, dens.reshape(gx.shape)


def _fluid_arrows(pos, fp):
    h = fp["interaction_radius"]; k = fp["k_fluid"]
    d = pos[:, None, :] - pos[None, :, :]
    dist = np.maximum(np.linalg.norm(d, axis=2), 1.0)
    q = dist / h
    shape = np.zeros_like(q); inside = q < 1.0
    shape[inside] = (1.0 - q[inside]) ** 2
    np.fill_diagonal(shape, 0.0)
    return (k * shape / np.maximum(dist, 1e-9))[:, :, None] * d


def panel_mechanism(ax, p, rad, fp, title):
    gx, gy, dens = _fluid_density(p, rad, fp, step=100)
    vmax = max(np.percentile(dens, 99), 1e-12)
    pcm = ax.pcolormesh(gx, gy, dens, cmap="plasma", shading="auto",
                        vmin=0, vmax=vmax)
    forces = _fluid_arrows(p, fp).sum(axis=1)
    mag = np.linalg.norm(forces, axis=1, keepdims=True)
    mag[mag == 0] = 1.0
    u = forces / mag * 520.0          # fixed-length arrows: compression direction
    ax.quiver(p[:, 0], p[:, 1], u[:, 0], u[:, 1], color="white",
              angles="xy", scale_units="xy", scale=1, width=0.004,
              alpha=0.95, zorder=6)
    ax.scatter(p[:, 0], p[:, 1], c="black", s=14, zorder=7)
    # Crop to the swarm extent so the compression mechanism is visible
    m = 900
    ax.set_xlim(p[:, 0].min() - m, p[:, 0].max() + m)
    ax.set_ylim(p[:, 1].min() - m, p[:, 1].max() + m)
    ax.set_title(title, fontsize=10, fontweight="bold")
    ax.set_aspect("equal"); ax.tick_params(labelleft=False, labelbottom=False)
    clean(ax)
    return pcm


def panel_laguerre(ax, n=40):
    d = np.load(DEMO / f"snapshots_star_{n}_{SEEDS[0]}.npz", allow_pickle=True)
    pos = d["pos"][-1]
    rad = radii_for(n)
    rad_norm = (rad - rad.min()) / (rad.max() - rad.min() + 1e-12)
    cell_cmap = plt.get_cmap("viridis")
    cell_colors = np.array([cell_cmap(0.2 + 0.8 * rr) for rr in rad_norm])
    gx, gy, grid = _grid2d(step=100)
    dist2 = ((pos[None, :, :] - grid[:, None, :]) ** 2).sum(-1) - rad[None, :] ** 2
    cell = np.argmin(dist2, axis=1).reshape(gx.shape)
    for cid in np.unique(cell):
        ax.contourf(gx, gy, np.where(cell == cid, 1, 0), levels=[0.5, 1.5],
                    colors=[tuple(cell_colors[cid])], alpha=0.55, antialiased=True)
    for c, r, cc in zip(pos, rad, cell_colors):
        ax.add_patch(mpatches.Circle(c, r, fill=False, edgecolor=tuple(cc),
                                     lw=1.2, zorder=4))
    ax.scatter(pos[:, 0], pos[:, 1], c="white", s=20, edgecolors="black",
               linewidths=0.5, zorder=5)
    ax.contour(gx, gy, cell.astype(float), levels=np.unique(cell) + 0.5,
               colors="#222222", linewidths=0.5, alpha=0.6)
    ax.set_aspect("equal"); ax.tick_params(labelleft=False, labelbottom=False)
    clean(ax)
    sm = matplotlib.cm.ScalarMappable(
        cmap=cell_cmap, norm=matplotlib.colors.Normalize(rad.min(), rad.max()))
    sm.set_array([])
    return sm


def fig_R2(n=40):
    fp = dict(CFG["fluid"])
    d = np.load(DEMO / f"fluxtrace_{n}_{SEEDS[0]}.npz")
    fsteps, fpos = d["steps"], d["pos"]
    rad = radii_for(n)
    fig, axes = plt.subplots(1, 3, figsize=(16.4, 5.4))
    letters = iter("abc")
    for ax, target in zip(axes[:2], (21, 120)):
        k = int(np.argmin(np.abs(fsteps - target)))
        pcm = panel_mechanism(ax, fpos[k], rad, fp,
                              f"fluid step {int(fsteps[k])}")
        plabel(ax, f"({next(letters)})", dx=0.005)
        cb = fig.colorbar(pcm, ax=ax, shrink=0.8, pad=0.02)
        cb.set_label("SPH mass density", fontsize=9)
    sm = panel_laguerre(axes[2], n)
    plabel(axes[2], "(c)", dx=0.005)
    axes[2].set_title("MW-Voronoi (Laguerre) partition", fontsize=10, fontweight="bold")
    cb = fig.colorbar(sm, ax=axes[2], shrink=0.8, pad=0.02)
    cb.set_label("Sensing radius (m)", fontsize=9)
    fig.suptitle("Mechanisms — stage-1 pressure-driven self-diffusion and "
                 "stage-2 heterogeneous responsibility partition (N=40)",
                 fontsize=13.5, fontweight="bold", y=1.0)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    save(fig, "FigR2_mechanism_partition")


# --------------------------------------------------------------------------- #
#  panels -- FigR3
# --------------------------------------------------------------------------- #
def panel_bars(ax, n, sig):
    rows = [r for r in load_star_rows()
            if r["suite"] == "benchmark" and r["N"] == str(n)]
    means, sds = [], []
    for m in ORDER:
        v = [float(r["final_coverage"]) for r in rows if r["method"] == m]
        means.append(np.mean(v)); sds.append(np.std(v))
    bars = ax.bar(np.arange(len(ORDER)), means, yerr=sds,
                  color=[COLORS[m] for m in ORDER], capsize=4, width=0.62,
                  edgecolor="white", error_kw=dict(lw=1.1))
    for i, m in enumerate(ORDER):
        if m == "star":
            continue
        mark = sig.get((int(n), m), "")
        if mark:
            ax.text(i, means[i] + sds[i] + 0.012, mark, ha="center",
                    fontsize=11, fontweight="bold", color="#C1121F")
    ax.axhline(means[0], color=COLORS["star"], ls="--", lw=1.1, alpha=0.8)
    ax.set_xticks(np.arange(len(ORDER)))
    ax.set_xticklabels([LAB[m] for m in ORDER], fontsize=8.5)
    ax.set_ylim(0, 1.08)
    ax.set_title(f"N = {n}  (12 seeds)", fontweight="bold", fontsize=10.5)
    clean(ax)
    bars[0].set_hatch("//")


def panel_radar(ax):
    rows = [r for r in load_star_rows()
            if r["suite"] == "benchmark" and r["N"] == "100"]
    met = {}
    for m in ORDER:
        vals = [r for r in rows if r["method"] == m]
        if not vals:
            continue
        t90 = [float(r["t90"]) for r in vals if float(r["t90"]) > 0]
        fair = json.load(io.open(FAIR, encoding="utf-8"))
        fv = [v["fairness"] for k, v in fair.items()
              if k.startswith("n100_") and k.endswith(f"_{m}")]
        met[m] = dict(
            cov=np.mean([float(r["final_coverage"]) for r in vals]),
            auc=np.mean([float(r["coverage_auc"]) for r in vals]),
            spd=np.mean([1.0 / t for t in t90]) if t90 else 0.0,
            ene=np.mean([float(r["energy"]) for r in vals]),
            nbr=np.mean([float(r["neighbor_fraction"]) for r in vals]),
            fair=float(np.mean(fv)) if fv else 0.0)
    emax = max(v["ene"] for v in met.values())
    smax = max(v["spd"] for v in met.values())
    labels = ["Coverage", "AUC", "Speed\n(1/T$_{90}$)", "Energy\nEfficiency",
              "Neighbor\nConnect.", "Fairness"]
    ang = np.linspace(0, 2 * np.pi, len(labels), endpoint=False).tolist()
    ang += ang[:1]
    for m in ORDER:
        if m not in met:
            continue
        v = [met[m]["cov"], met[m]["auc"] / 70.0, met[m]["spd"] / smax,
             1.0 - met[m]["ene"] / emax, met[m]["nbr"], met[m]["fair"]]
        v += v[:1]
        ax.plot(ang, v, color=COLORS[m], lw=2.2, label=LAB[m])
        ax.fill(ang, v, color=COLORS[m], alpha=0.10)
    ax.set_xticks(ang[:-1]); ax.set_xticklabels(labels, fontsize=8.5)
    ax.set_ylim(0, 1); ax.set_yticks([0.2, 0.4, 0.6, 0.8, 1.0])
    ax.set_yticklabels(["0.2", "0.4", "0.6", "0.8", "1.0"], fontsize=7)
    ax.grid(True, alpha=0.4)
    ax.set_title("Multi-metric profile (N=100)", fontweight="bold", fontsize=10.5, pad=18)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.06), ncol=3, fontsize=8,
              frameon=False, columnspacing=1.2, handletextpad=0.4)


def panel_forest(ax):
    rows = load_star_rows()
    base_order = ["lloyd", "pso", "vfa", "random"]
    y, tick = 0, []
    for n in ("40", "100"):
        b = [r for r in rows if r["suite"] == "benchmark" and r["N"] == n]
        sb = {m: np.array([float(r["final_coverage"]) for r in b if r["method"] == m])
              for m in ["star"] + base_order}
        for m in base_order:
            d = sb["star"] - sb[m]
            mean, sd = d.mean(), d.std(ddof=1)
            ci = 1.96 * sd / np.sqrt(len(d))
            ax.errorbar(mean, y, xerr=ci, fmt="o", ms=5.5, color=COLORS["star"],
                        ecolor=COLORS["star"], elinewidth=1.5, capsize=3.5, zorder=3)
            ax.text(mean + ci + 0.006, y, f"{mean:+.3f}", va="center",
                    fontsize=8, color="#333")
            tick.append(f"N={n}\nvs {LAB[m]}")
            y += 1
        if n == "40":
            ax.axhline(y - 0.5, color="#CCCCCC", lw=1.1, ls="--")
    ax.axvline(0, color="#333", lw=1.0)
    ax.set_yticks(range(y)); ax.set_yticklabels(tick, fontsize=7.5)
    ax.set_xlabel(r"$\bar{F}_{\mathrm{STAR}}-\bar{F}_{\mathrm{baseline}}$"
                  "  (95% CI)", fontsize=9.5)
    ax.set_xlim(-0.12, 0.75)
    ax.set_title("Paired advantage margin", fontweight="bold", fontsize=10.5)
    clean(ax)


def fig_R3():
    sig = {}
    with io.open(SIG_CSV, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            sig[(int(r["N"]), r["baseline"])] = r["t_sig"]
    fig = plt.figure(figsize=(15.6, 5.0))
    gs = fig.add_gridspec(1, 4, width_ratios=[1, 1, 1.35, 1.15], wspace=0.28)
    ax = fig.add_subplot(gs[0, 0]); panel_bars(ax, 40, sig); plabel(ax, "(a)", dx=0.005)
    ax = fig.add_subplot(gs[0, 1]); panel_bars(ax, 100, sig); plabel(ax, "(b)", dx=0.005)
    ax = fig.add_subplot(gs[0, 2], projection="polar"); panel_radar(ax)
    ax.text(-0.06, 1.06, "(c)", transform=ax.transAxes, fontsize=13,
            fontweight="bold", va="bottom", ha="right")
    ax = fig.add_subplot(gs[0, 3]); panel_forest(ax); plabel(ax, "(d)", dx=0.005)
    ax.yaxis.grid(False)
    fig.suptitle("Benchmark performance and mission-quality profile "
                 "(mean over 12 seeds; *** p<0.001, t / Wilcoxon vs STAR)",
                 fontsize=13.5, fontweight="bold", y=1.02)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    save(fig, "FigR3_benchmark_radar_forest")


# --------------------------------------------------------------------------- #
#  FigR4 -- robustness & scalability (3 error-shadow panels)
# --------------------------------------------------------------------------- #
def _agg(rows, key, val, xvals):
    out = {}
    for xv in xvals:
        v = [float(r[val]) for r in rows if abs(float(r[key]) - float(xv)) < 1e-9]
        if v:
            out[xv] = (float(np.mean(v)), float(np.std(v)))
    return out


def panel_sweep(ax, kind):
    star_rows, bas = load_star_rows(), load_sweep_rows()
    if kind == "comm":
        key, xs = "comm_radius", [500, 1000, 1500, 2000, 2500, 3000, 3500, 4000, 5000]
        xlab, suite, ttl = ("Communication radius $C_{\\mathrm{th}}$ (m)",
                            "comm_radius", "Communication radius")
    elif kind == "pl":
        key, xs = "drop", [0, 0.1, 0.2, 0.3, 0.4, 0.5]
        xlab, suite, ttl = ("Packet loss rate (%)", "packet_loss", "Packet loss")
    else:
        key, xs = "N", [20, 40, 60, 80, 100, 150, 200, 300]
        xlab, suite, ttl = ("Swarm size $N$", "scalability", "Swarm size")

    def plot(rows, m, label, marker):
        agg = _agg(rows, key, "final_coverage", xs)
        if not agg:
            return
        ks = sorted(agg)
        mu = np.array([agg[k][0] for k in ks])
        sd = np.array([agg[k][1] for k in ks])
        xx = np.array(ks) * 100 if kind == "pl" else np.array(ks)
        ax.plot(xx, mu, color=COLORS[m], lw=2.2, label=label, zorder=3,
                marker=marker, ms=3.5)
        ax.fill_between(xx, mu - sd, mu + sd, color=COLORS[m], alpha=0.16, zorder=2)

    plot([r for r in star_rows if r["suite"] == suite and r["method"] == "star"],
         "star", "STAR (12 seeds)", "o")
    for m in ["lloyd", "pso", "vfa", "random"]:
        plot([r for r in bas if r["method"] == m and r["suite"] == suite],
             m, LAB[m], "s")
    if kind == "scal":
        ax.set_xscale("log", base=2)
        ax.set_xticks(xs); ax.set_xticklabels(xs)
    ax.set_xlabel(xlab); ax.set_ylabel(r"Coverage $\bar{F}$")
    ax.set_title(ttl, fontweight="bold", fontsize=10.5)
    if kind == "pl":
        ax.set_xlim(-3, 55); ax.set_ylim(0.22, 1.03)
    elif kind == "comm":
        ax.set_ylim(0, 1.06)
    else:
        ax.set_ylim(0.55, 1.05)
    ax.grid(True, which="both", alpha=0.3)
    ax.legend(loc="best", frameon=True, ncol=2, fontsize=7.5)
    clean(ax)


def fig_R4():
    fig, axes = plt.subplots(1, 3, figsize=(16.4, 4.9))
    for ax, kind, letter in zip(axes, ("comm", "pl", "scal"), ("a", "b", "c")):
        panel_sweep(ax, kind)
        plabel(ax, f"({letter})", dx=0.005)
    fig.suptitle("Robustness and scalability — coverage under communication "
                 "and scale variations (mean$\\pm$SD, full axis)",
                 fontsize=13.5, fontweight="bold", y=1.02)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    save(fig, "FigR4_robustness_scalability")


# --------------------------------------------------------------------------- #
#  FigR5 -- ablation
# --------------------------------------------------------------------------- #
def fig_R5(n=40):
    from scipy.stats import ttest_rel
    rows = load_star_rows()
    ab = {m: np.array([float(r["final_coverage"]) for r in rows
                       if r["suite"] == "ablation" and r["N"] == str(n)
                       and r["method"] == m])
          for m in ("star", "no_fluid", "no_laguerre", "no_vevf", "no_hole_fill")}
    ref = ab["star"]
    comps = [("no_fluid", "Fluid self-diffusion"),
             ("no_laguerre", "MW-Voronoi (Laguerre)"),
             ("no_vevf", "EVFA + VEVF"),
             ("no_hole_fill", "Hole-filling")]
    names, deltas, d_sds, pvals, fail = [], [], [], [], []
    for key, nm in comps:
        names.append(nm)
        d = ref - ab[key]
        deltas.append(float(d.mean())); d_sds.append(float(d.std(ddof=1)))
        _, p = ttest_rel(ref, ab[key]); pvals.append(p)
        t90 = np.array([float(r["t90"]) for r in rows
                        if r["suite"] == "ablation" and r["N"] == str(n)
                        and r["method"] == key])
        fail.append(100.0 * (1.0 - (t90 > 0).mean()))
    ypos = np.arange(len(comps))[::-1]

    fig, axes = plt.subplots(1, 2, figsize=(12.6, 4.4), width_ratios=[1.5, 1])
    ax = axes[0]
    ax.barh(ypos, deltas, xerr=d_sds,
            color=[COLORS["star"] if d >= 0 else "#8D6E63" for d in deltas],
            height=0.58, edgecolor="white", error_kw=dict(lw=1.2, ecolor="#444"))
    for yy, d_, p in zip(ypos, deltas, pvals):
        mark = "***" if p < 0.001 else ("**" if p < 0.01 else ("*" if p < 0.05 else "n.s."))
        ax.text(d_ + (0.004 if d_ >= 0 else -0.004), yy, mark, va="center",
                ha="left" if d_ >= 0 else "right", fontsize=10,
                fontweight="bold", color="#333")
    ax.axvline(0, color="#333", lw=1.1)
    ax.set_yticks(ypos); ax.set_yticklabels(names)
    ax.set_xlabel(r"$\Delta\bar{F}$ when stage removed (mean$\pm$1SD)")
    ax.set_title(f"Coverage contribution  (STAR $\\bar{{F}}$={ref.mean():.3f})",
                 fontweight="bold")
    ax.set_xlim(-0.03, max(deltas) * 1.40 + 0.05)
    clean(ax); plabel(ax, "(a)", dx=-0.55)

    ax = axes[1]
    ax.barh(ypos, fail, color=["#E63946" if f > 5 else "#9AA5B1" for f in fail],
            height=0.58, edgecolor="white")
    for yy, f in zip(ypos, fail):
        ax.text(f + 2, yy, f"{f:.0f}%", va="center", ha="left", fontsize=9.5)
    ax.set_yticks(ypos); ax.set_yticklabels([""] * len(comps))
    ax.set_xlim(0, 105); ax.set_xlabel("Seeds failing to reach 90% coverage (%)")
    ax.set_title("Reliability impact", fontweight="bold")
    clean(ax); plabel(ax, "(b)", dx=-0.42)

    fig.suptitle(f"Ablation — role of each stage (N={n}, 12 seeds)",
                 fontweight="bold", fontsize=13, y=1.02)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    save(fig, "FigR5_ablation")


def main():
    print("Composing SCI multi-panel figures ->", OUT)
    fig_R1()
    fig_R2()
    fig_R3()
    fig_R4()
    fig_R5()
    print("DONE")


if __name__ == "__main__":
    main()
