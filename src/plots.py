#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backend_bases import MouseButton
from matplotlib.dates import AutoDateLocator, ConciseDateFormatter, date2num
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.widgets import MultiCursor
from pandas.plotting import register_matplotlib_converters

from src.fitting import GAS_COLUMNS, fit_window, quality_flag, to_flux, window_seconds
from src.preselect import DEFAULTS as PRESELECT_DEFAULTS

register_matplotlib_converters()
# Interactive backend for the point selection, unless one is set explicitly
if "MPLBACKEND" not in os.environ:
    mpl.use("tkAgg")

# Colours: one per gas, a distinct one for the CH4 bubbles, neutral for the rest
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#8a8984"
GRID = "#e6e5e0"
GAS_COLORS = {"CH4": "#2a78d6", "CO2": "#eb6834"}
BUBBLE_COLOR = "#6250d6"
WINDOW_COLOR = "#8a8984"
POINT_COLOR = INK
FLAG_COLOR = "#d03b3b"  # label of a window that would be flagged
GAS_LABELS = {"CH4": "CH$_4$", "CO2": "CO$_2$"}
MIN_POINTS = 3

mpl.rcParams.update({
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "axes.edgecolor": MUTED,
    "axes.labelcolor": INK_2,
    "axes.titlecolor": INK,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "axes.axisbelow": True,
    "grid.color": GRID,
    "grid.linewidth": 0.8,
    "xtick.color": INK_2,
    "ytick.color": INK_2,
    "xtick.labelcolor": INK_2,
    "ytick.labelcolor": INK_2,
    "font.size": 10,
    "axes.labelsize": 10,
    "axes.titlesize": 10,
    "legend.frameon": False,
    "legend.fontsize": 9,
    "savefig.bbox": "tight",
})
# Keys used by the selection window instead of matplotlib's save (s) and close (q)
for _keymap, _key in (("keymap.save", "s"), ("keymap.quit", "q")):
    mpl.rcParams[_keymap] = [k for k in mpl.rcParams[_keymap] if k != _key]


def _time_axis(ax):
    """Compact date labels on a time axis."""
    locator = AutoDateLocator()
    ax.xaxis.set_major_locator(locator)
    ax.xaxis.set_major_formatter(ConciseDateFormatter(locator))


def _gas_ylabel(ax, gas):
    ax.set_ylabel(f"{GAS_LABELS[gas]} (ppm)")


def plot_data(data, results, cfg, name):
    """Save one figure per flux and one figure with all the data."""
    folder = figure_folder(data, cfg)
    plot_perflux(data, results, cfg, name, folder)
    plot_alldata(data, results, cfg, name, folder)


def figure_folder(data, cfg):
    """path_out/Figures/Figures_<date of the first sample>, created if needed."""
    date = data.index[0].strftime("%Y-%m-%d")
    path_figout = os.path.join(cfg["path_out"], "Figures", "Figures_" + date)
    os.makedirs(path_figout, exist_ok=True)
    return path_figout


def _window_label(data, i, j, n, cfg):
    """Label of a window: number, flux and r of each gas, CH4 bubbles, flag.

    Returns
    -------
    label : str
    bubbles : list of (int, int)
        First and last sample of each CH4 bubble (positions in data)
    flagged : bool
        True if the flux would be flagged in the results (|r| < min_r or
        window shorter than min_duration)
    """
    if j - i + 1 < MIN_POINTS:
        return f"{n}: too short", [], True
    quality = {**PRESELECT_DEFAULTS, **(cfg.get("Preselect") or {})}
    duration = (data.index[j] - data.index[i]).total_seconds()
    lines = [str(n)]
    bubbles = []
    flags = []
    for gas in ("CH4", "CO2"):
        try:
            fit = fit_window(data, i, j, gas, cfg.get("Bubbles"))
        except ValueError:
            lines.append(f"{GAS_LABELS[gas]} ?")
            flags.append(f"{GAS_LABELS[gas]} fit failed")
            continue
        text = f"{GAS_LABELS[gas]} {to_flux(cfg, fit['slope']):.3g}  r {fit['rvalue']:.2f}"
        if fit["bubbles"]:
            bubbles = [(i + a, i + b) for a, b in fit["bubbles"]]
            text += f"  +{len(bubbles)} bubble{'s' if len(bubbles) > 1 else ''}"
        lines.append(text)
        flag = quality_flag(fit["rvalue"], duration, quality)
        if flag:
            flags += [f"{GAS_LABELS[gas]} {f}" if f.startswith("|r|")
                      else f.replace("shorter than", "<") for f in flag.split("; ")]
    if flags:
        lines.append("check: " + ", ".join(dict.fromkeys(flags)))
    return "\n".join(lines), bubbles, bool(flags)


def _unstack_labels(fig, ax, labels, pad=5):
    """Move labels down until they do not overlap the labels before them."""
    renderer = fig.canvas.get_renderer()
    to_axes = ax.transAxes.inverted()

    def extent(label):  # text plus its box padding, in pixels
        box = label.get_window_extent(renderer)
        return box.from_extents(box.x0 - pad, box.y0 - pad, box.x1 + pad, box.y1 + pad)

    placed = []
    for label in labels:
        for _ in range(len(placed)):
            box = extent(label)
            hit = next((other for other in placed if box.overlaps(other)), None)
            if hit is None:
                break
            # top of this label just under the bottom of the one it overlaps
            label.set_y(to_axes.transform((0, hit.y0 - pad))[1])
        placed.append(extent(label))


def plot_select_points(data, cfg, preselected=(), title=""):
    """Select the start and end of each flux on the plot.

    CH4 is on top and CO2 below, on the same time axis. Points are paired in
    time order (1st-2nd, 3rd-4th, ...); each window is shaded and labelled
    with its number, the diffusive flux (mmol m-2 d-1) and Pearson r of each
    gas and the CH4 bubbles found (drawn in violet). Windows that would be
    flagged in the results have a red label.

    Left click: add the nearest sample.
    Right click: remove the nearest point (to move an edge: right click it,
    then left click the new position).
    Key "d" or Delete: remove the window under the mouse.
    Enter, middle click or closing the window: finish and save.
    Key "s": skip this file (nothing saved). Key "q": stop (this file is not
    saved and the remaining files are not processed).
    Clicks are ignored while the zoom or pan tool of the toolbar is active.

    Parameters
    ----------
    preselected : list of (int, int)
        Windows shown at the start (e.g. from preselect_windows)
    title : str
        Figure title, e.g. the file name

    Returns
    -------
    windows : list of (int, int)
        Positions of the first and last sample of each flux, in time order.
    action : str
        "save", "skip" or "quit"
    """
    plot_cfg = cfg.get("Plot") or {}

    xnum = date2num(data.index)
    values = {gas: data[GAS_COLUMNS[gas]].to_numpy() for gas in ("CH4", "CO2")}

    # CH4 on top, CO2 below, sharing the time axis; clicks work on both
    fig, (ax_ch4, ax_co2) = plt.subplots(
        2, 1, figsize=(15, 7.5), sharex=True, gridspec_kw={"hspace": 0.08}
    )
    axes = {"CH4": ax_ch4, "CO2": ax_co2}
    marks = {}
    for gas, ax in axes.items():
        ax.plot(xnum, values[gas], color=GAS_COLORS[gas], linewidth=1.5)
        _gas_ylabel(ax, gas)
        (marks[gas],) = ax.plot(
            [], [], "o", color=POINT_COLOR, ms=7, mec="white", mew=1.5, zorder=5
        )
    _time_axis(ax_co2)
    ax_ch4.set_ylim(plot_cfg.get("ylim_min"), plot_cfg.get("ylim_max"))
    ax_ch4.set_title(title, loc="left", fontsize=12, fontweight="bold", pad=24)
    fig.text(
        0.5, 0.01,
        "Left click: add point   Right click: remove nearest point   d: delete window under mouse   "
        "Enter: save and next file   s: skip file   q: stop   "
        "(fluxes in mmol m$^{-2}$ d$^{-1}$; clicks are ignored while zoom/pan is on)",
        ha="center", va="bottom", fontsize=9, color=MUTED,
    )
    fig.legend(
        handles=[
            Patch(color=WINDOW_COLOR, alpha=0.2, label="Flux window"),
            Line2D([], [], color=BUBBLE_COLOR, lw=3.5, label="CH$_4$ bubble (excluded)"),
            Line2D([], [], marker="o", ls="", color=POINT_COLOR, mec="white",
                   ms=7, label="Window edge"),
        ],
        loc="upper right", ncol=3, bbox_to_anchor=(0.9, 0.955),
    )
    fig.subplots_adjust(left=0.06, right=0.97, top=0.9, bottom=0.1)

    selected = sorted({i for window in preselected for i in window})
    window_artists = []
    action = ["save"]  # changed by the s and q keys

    def redraw():
        for gas, mark in marks.items():
            mark.set_data(xnum[selected], values[gas][selected])
        for artist in window_artists:
            artist.remove()
        window_artists.clear()
        labels = []
        for n, (i, j) in enumerate(zip(selected[::2], selected[1::2]), start=1):
            label, bubbles, flagged = _window_label(data, i, j, n, cfg)
            for ax in axes.values():
                window_artists.append(
                    ax.axvspan(xnum[i], xnum[j], color=WINDOW_COLOR, alpha=0.15, lw=0)
                )
            for a, b in bubbles:
                # the excluded stretch of the CH4 line, drawn over it
                window_artists.extend(ax_ch4.plot(
                    xnum[a : b + 1], values["CH4"][a : b + 1], color=BUBBLE_COLOR,
                    lw=3.5, solid_capstyle="round", zorder=4,
                ))
            label_artist = ax_ch4.text(
                (xnum[i] + xnum[j]) / 2, 0.97, label,
                transform=ax_ch4.get_xaxis_transform(), ha="center", va="top",
                fontsize=8, color=FLAG_COLOR if flagged else INK_2, linespacing=1.3,
                bbox={"boxstyle": "round,pad=0.3", "fc": "white", "alpha": 0.9,
                      "ec": FLAG_COLOR if flagged else GRID,
                      "lw": 1.2 if flagged else 0.8},
            )
            window_artists.append(label_artist)
            labels.append(label_artist)
        _unstack_labels(fig, ax_ch4, labels)
        fig.canvas.draw_idle()

    def toolbar_active():
        toolbar = getattr(fig.canvas, "toolbar", None)
        return toolbar is not None and bool(getattr(toolbar, "mode", ""))

    def on_click(event):
        if event.button == MouseButton.MIDDLE:
            plt.close(fig)
            return
        if toolbar_active():
            return  # zooming or panning
        if event.inaxes is None or event.xdata is None:
            return  # click outside the plot
        idx = int(np.abs(xnum - event.xdata).argmin())
        if event.button == MouseButton.LEFT:
            if idx in selected:
                return
            selected.append(idx)
            selected.sort()
        elif event.button == MouseButton.RIGHT:
            if not selected:
                return
            nearest = min(selected, key=lambda i: abs(xnum[i] - event.xdata))
            selected.remove(nearest)
        else:
            return
        redraw()

    def on_key(event):
        if event.key in ("enter", "s", "q"):
            action[0] = {"enter": "save", "s": "skip", "q": "quit"}[event.key]
            plt.close(fig)
            return
        if event.key not in ("d", "delete") or event.xdata is None:
            return
        for n in range(0, len(selected) - 1, 2):
            if xnum[selected[n]] <= event.xdata <= xnum[selected[n + 1]]:
                del selected[n : n + 2]
                redraw()
                return

    # Keep a reference to the cursor, otherwise it is garbage collected
    cursor = MultiCursor(  # noqa: F841
        None, (ax_ch4, ax_co2), useblit=False, color=INK_2, linewidth=0.8, linestyle="--"
    )
    fig.canvas.mpl_connect("button_press_event", on_click)
    fig.canvas.mpl_connect("key_press_event", on_key)
    redraw()
    plt.show()

    return points_to_windows(selected), action[0]


def points_to_windows(points):
    """Pair sample positions in time order into (start, end) windows.

    An unpaired last point and windows with fewer than MIN_POINTS samples
    are dropped with a warning.
    """
    points = sorted(points)
    if len(points) % 2:
        print(f"Warning: odd number of points, the last point ({points[-1]}) is ignored.")
    windows = []
    for start, end in zip(points[::2], points[1::2]):
        if end - start + 1 < MIN_POINTS:
            print(f"Warning: window {start}-{end} has less than {MIN_POINTS} samples, ignored.")
            continue
        windows.append((start, end))
    return windows


def _flux_text(gas, row):
    """Slope, r and fluxes of one gas, for the per-flux figure."""
    unit = "mmol m$^{-2}$ d$^{-1}$"
    lines = [
        f"slope = {row['Slope (ppm/s)']:.3g} ppm s$^{{-1}}$    r = {row['Pearson']:.3f}",
        f"Diffusive flux = {row['Diffusive flux (mmol/m2/d)']:.3g} {unit}",
    ]
    if gas == "CH4" and row["N bubbles"] > 0:
        n = int(row["N bubbles"])
        lines.append(
            f"Ebullitive flux = {row['Ebullitive flux (mmol/m2/d)']:.3g} {unit}"
            f"  ({n} bubble{'s' if n > 1 else ''})"
        )
        lines.append(f"Total flux = {row['Total flux (mmol/m2/d)']:.3g} {unit}")
    return "\n".join(lines)


def plot_perflux(data, results, cfg, name, folder):
    """One figure per flux: CH4 (with bubbles) and CO2 with the fitted lines."""
    bubble_options = cfg.get("Bubbles")
    for fid, res in results.groupby("FID", sort=True):
        idx1 = int(res["ID start"].iloc[0])
        idx2 = int(res["ID end"].iloc[0])
        seconds = window_seconds(data, idx1, idx2)

        fig, axes = plt.subplots(2, 1, figsize=(7, 8), sharex=True)
        for ax, gas in zip(axes, ("CH4", "CO2")):
            row = res[res["Gas"] == gas].iloc[0]
            values = data[GAS_COLUMNS[gas]].iloc[idx1 : idx2 + 1].to_numpy()
            fit = fit_window(data, idx1, idx2, gas, bubble_options)
            used = fit["used"]
            ax.plot(seconds[used], values[used], "o", color=GAS_COLORS[gas], ms=3.5,
                    alpha=0.7, mew=0, label=f"{GAS_LABELS[gas]} data")
            if (~used).any():
                ax.plot(seconds[~used], values[~used], "o", mfc="none", mec=BUBBLE_COLOR,
                        ms=4, mew=1, label="Excluded (bubble)")
            segment = fit.get("segment", np.zeros(len(values), dtype=int))
            for k, offset in fit["offsets"].items():
                part = (segment == k) & used
                ax.plot(seconds[part], offset + fit["slope"] * seconds[part], color=INK,
                        lw=1.5, label="Linear fit" if k == min(fit["offsets"]) else None)
            # statistics and legend in the corners the data does not reach
            rising = fit["slope"] >= 0
            ax.text(0.02, 0.97 if rising else 0.03, _flux_text(gas, row),
                    transform=ax.transAxes, va="top" if rising else "bottom",
                    fontsize=9, color=INK, linespacing=1.5,
                    bbox={"boxstyle": "round,pad=0.4", "fc": "white", "ec": GRID})
            ax.legend(loc="lower right" if rising else "upper right")
            _gas_ylabel(ax, gas)
        axes[-1].set_xlabel("Time since start of window (s)")
        axes[0].set_title(
            f"{name}  ·  flux {fid}  ·  {data.index[idx1]:%Y-%m-%d %H:%M:%S}",
            loc="left", fontsize=11, fontweight="bold",
        )
        fig.tight_layout()
        figfile = "_".join([cfg["site"], name, "Flux", str(fid)]) + ".png"
        fig.savefig(os.path.join(folder, figfile), format="png", dpi=300)
        plt.close(fig)


def plot_alldata(data, results, cfg, name, folder):
    """Figure of the whole LGR file with the selected windows."""
    fig, axes = plt.subplots(2, 1, figsize=(12, 7), sharex=True,
                             gridspec_kw={"hspace": 0.08})
    windows = results.drop_duplicates("FID")
    for ax, gas in zip(axes, ("CH4", "CO2")):
        ax.plot(data.index, data[GAS_COLUMNS[gas]], color=GAS_COLORS[gas], linewidth=1.5)
        for _, res in windows.iterrows():
            ax.axvspan(res["Time start"], res["Time end"], color=WINDOW_COLOR,
                       alpha=0.15, lw=0)
        _gas_ylabel(ax, gas)
    for _, res in windows.iterrows():
        middle = res["Time start"] + (res["Time end"] - res["Time start"]) / 2
        axes[0].text(middle, 0.97, str(res["FID"]), transform=axes[0].get_xaxis_transform(),
                     ha="center", va="top", fontsize=9, fontweight="bold", color=INK_2)
    _time_axis(axes[-1])
    axes[0].set_title(f"{name}  ·  shaded: flux windows", loc="left", fontsize=11,
                      fontweight="bold")
    figfile = "_".join([cfg["site"], name, "all"]) + ".png"
    fig.savefig(os.path.join(folder, figfile), format="png", dpi=300)
    plt.close(fig)
