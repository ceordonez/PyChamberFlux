#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backend_bases import MouseButton
from matplotlib.dates import date2num
from matplotlib.widgets import Cursor
from pandas.plotting import register_matplotlib_converters

from src.fitting import GAS_COLUMNS, fit_window, window_seconds

register_matplotlib_converters()
# Interactive backend for the point selection, unless one is set explicitly
if "MPLBACKEND" not in os.environ:
    mpl.use("tkAgg")

GAS_COLORS = {"CH4": "b", "CO2": "k"}
BUBBLE_COLOR = "orange"
MIN_POINTS = 3


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


def _window_label(data, i, j, n, bubble_options):
    """Number, r of each gas and number of CH4 bubbles of a window."""
    if j - i + 1 < MIN_POINTS:
        return f"{n}: too short", []
    lines = [str(n)]
    bubbles = []
    for gas in ("CH4", "CO2"):
        try:
            fit = fit_window(data, i, j, gas, bubble_options)
        except ValueError:
            lines.append(f"{gas} ?")
            continue
        text = f"{gas} r={fit['rvalue']:.2f}"
        if fit["bubbles"]:
            bubbles = [(i + a, i + b) for a, b in fit["bubbles"]]
            text += f" ({len(bubbles)} bubble{'s' if len(bubbles) > 1 else ''})"
        lines.append(text)
    return "\n".join(lines), bubbles


def plot_select_points(data, cfg, preselected=(), title=""):
    """Select the start and end of each flux on the plot.

    CH4 is on the left axis and CO2 on the right axis. Points are paired in
    time order (1st-2nd, 3rd-4th, ...); each window is shaded and labelled
    with its number, the Pearson r of each gas and the CH4 bubbles found
    (marked in orange).

    Left click: add the nearest sample.
    Right click: remove the nearest point (to move an edge: right click it,
    then left click the new position).
    Key "d" or Delete: remove the window under the mouse.
    Middle click or closing the window: finish.
    Clicks are ignored while the zoom or pan tool of the toolbar is active.

    Parameters
    ----------
    preselected : list of (int, int)
        Windows shown at the start (e.g. from preselect_windows)
    title : str
        Figure title, e.g. the file name

    Returns
    -------
    list of (int, int)
        Positions of the first and last sample of each flux, in time order.
    """
    plot_cfg = cfg.get("Plot") or {}
    bubble_options = cfg.get("Bubbles")

    xnum = date2num(data.index)
    y = data[GAS_COLUMNS["CH4"]].to_numpy()

    fig = plt.figure(figsize=(15, 6))
    ax1 = fig.add_subplot(111, facecolor="#FFFFCC")
    ax2 = ax1.twinx()
    ax2.yaxis.tick_left()
    ax1.yaxis.tick_right()
    ax1.yaxis.set_label_position("right")
    ax2.yaxis.set_label_position("left")

    # CH4 on the left axis (ax2, on top: it receives the clicks), CO2 on the right
    ax1.plot(data[GAS_COLUMNS["CO2"]], GAS_COLORS["CO2"], linewidth=3)
    ax2.plot(data[GAS_COLUMNS["CH4"]], GAS_COLORS["CH4"], linewidth=3)
    ax1.set_ylabel("CO2 (ppm)")
    ax2.set_ylabel("CH4 (ppm)")
    for ax, gas, side in ((ax1, "CO2", "right"), (ax2, "CH4", "left")):
        ax.yaxis.label.set_color(GAS_COLORS[gas])
        ax.spines[side].set_color(GAS_COLORS[gas])
        ax.tick_params(axis="y", which="both", colors=GAS_COLORS[gas])
    ax2.set_ylim(plot_cfg.get("ylim_min"), plot_cfg.get("ylim_max"))
    if title:
        fig.suptitle(title)
    ax2.set_title(
        "Left click: add point   Right click: remove nearest point   "
        "d: delete window under mouse   Middle click: finish",
        fontsize=10,
    )
    (marks,) = ax2.plot([], [], "or")

    selected = sorted({i for window in preselected for i in window})
    window_artists = []

    def redraw():
        marks.set_data(xnum[selected], y[selected])
        for artist in window_artists:
            artist.remove()
        window_artists.clear()
        for n, (i, j) in enumerate(zip(selected[::2], selected[1::2]), start=1):
            label, bubbles = _window_label(data, i, j, n, bubble_options)
            window_artists.append(ax2.axvspan(xnum[i], xnum[j], color="g", alpha=0.2))
            for a, b in bubbles:
                window_artists.append(
                    ax2.axvspan(xnum[a], xnum[b], color=BUBBLE_COLOR, alpha=0.6)
                )
            window_artists.append(
                ax2.text(
                    (xnum[i] + xnum[j]) / 2, 0.98, label,
                    transform=ax2.get_xaxis_transform(), ha="center", va="top",
                    fontsize=8, color="g",
                )
            )
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
        if event.key not in ("d", "delete") or event.xdata is None:
            return
        for n in range(0, len(selected) - 1, 2):
            if xnum[selected[n]] <= event.xdata <= xnum[selected[n + 1]]:
                del selected[n : n + 2]
                redraw()
                return

    # Keep a reference to the cursor, otherwise it is garbage collected
    cursor = Cursor(ax=ax2, useblit=False, color="red", linewidth=2)  # noqa: F841
    fig.canvas.mpl_connect("button_press_event", on_click)
    fig.canvas.mpl_connect("key_press_event", on_key)
    redraw()
    plt.show()

    return points_to_windows(selected)


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
            ax.plot(seconds[used], values[used], "o", color=GAS_COLORS[gas], ms=3, label="LGR data")
            if (~used).any():
                ax.plot(seconds[~used], values[~used], "o", color=BUBBLE_COLOR, ms=3,
                        label="Excluded (bubble)")
            segment = fit.get("segment", np.zeros(len(values), dtype=int))
            for k, offset in fit["offsets"].items():
                part = (segment == k) & used
                ax.plot(seconds[part], offset + fit["slope"] * seconds[part], "k-",
                        label="Fit" if k == min(fit["offsets"]) else None)
            text = (
                f"slope = {row['Slope (ppm/s)']:.2E} ppm s$^{{-1}}$, r = {row['Pearson']:.3f}\n"
                f"Diffusive flux = {row['Diffusive flux (mmol/m2/d)']:.3g} mmol m$^{{-2}}$ d$^{{-1}}$"
            )
            if gas == "CH4" and row["N bubbles"] > 0:
                text += (
                    f"\nTotal flux = {row['Total flux (mmol/m2/d)']:.3g}, "
                    f"ebullitive = {row['Ebullitive flux (mmol/m2/d)']:.3g}"
                    f" ({int(row['N bubbles'])} bubbles)"
                )
            ax.set_title(text, fontsize=9, loc="left")
            ax.set_ylabel(f"{gas} (ppm)")
            ax.legend(fontsize=8, loc="lower right")
        axes[-1].set_xlabel("Time (s)")
        fig.suptitle(f"{name}  flux {fid}  {data.index[idx1]:%Y-%m-%d %H:%M:%S}")
        fig.tight_layout()
        figfile = "_".join([cfg["site"], name, "Flux", str(fid)]) + ".png"
        fig.savefig(os.path.join(folder, figfile), format="png", dpi=300)
        plt.close(fig)


def plot_alldata(data, results, cfg, name, folder):
    """Figure of the whole LGR file with the selected windows."""
    fig, axes = plt.subplots(2, 1, figsize=(12, 7), sharex=True)
    windows = results.drop_duplicates("FID")
    for ax, gas in zip(axes, ("CH4", "CO2")):
        ax.plot(data.index, data[GAS_COLUMNS[gas]], color=GAS_COLORS[gas], linewidth=2)
        for _, res in windows.iterrows():
            ax.axvspan(res["Time start"], res["Time end"], color="g", alpha=0.2)
            ax.text(res["Time start"], 0.98, str(res["FID"]), va="top",
                    transform=ax.get_xaxis_transform(), color="g")
        ax.set_ylabel(f"{gas} (ppm)")
    axes[-1].set_xlabel("Time")
    fig.suptitle(name)
    figfile = "_".join([cfg["site"], name, "all"]) + ".png"
    fig.savefig(os.path.join(folder, figfile), format="png", dpi=300)
    plt.close(fig)
