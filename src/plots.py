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

register_matplotlib_converters()
# Interactive backend for the point selection, unless one is set explicitly
if "MPLBACKEND" not in os.environ:
    mpl.use("tkAgg")

GAS_COLUMNS = {"CH4": "[CH4]d_ppm", "CO2": "[CO2]d_ppm"}
GAS_COLORS = {"CH4": "b", "CO2": "k"}
MIN_POINTS = 3


def plot_data(data, results, cfg):
    """Save one figure per flux and one figure with all the data."""
    plot_perflux(data, results, cfg)
    plot_alldata(data, results, cfg)


def _figure_folder(cfg):
    path_figout = os.path.join(cfg["path_out"], "Figures", "Figures_" + cfg["date"])
    os.makedirs(path_figout, exist_ok=True)
    return path_figout


def plot_select_points(data, cfg, preselected=()):
    """Select the start and end of each flux on the plot.

    Points are paired in time order (1st-2nd, 3rd-4th, ...) and each window
    is shaded and labelled with its number and Pearson r.

    Left click: add the nearest sample.
    Right click: remove the nearest point (to move an edge: right click it,
    then left click the new position).
    Key "d" or Delete: remove the window under the mouse.
    Middle click or closing the window: finish.

    Parameters
    ----------
    preselected : list of (int, int)
        Windows shown at the start (e.g. from preselect_windows)

    Returns
    -------
    list of (int, int)
        Positions of the first and last sample of each flux, in time order.
    """
    var = cfg["variable"]
    other = "CO2" if var == "CH4" else "CH4"
    ylim_min = cfg["Plot"]["ylim_min"]
    ylim_max = cfg["Plot"]["ylim_max"]

    xnum = date2num(data.index)
    y = data[GAS_COLUMNS[var]].to_numpy()

    fig = plt.figure(figsize=(15, 5))
    ax1 = fig.add_subplot(111, facecolor="#FFFFCC")
    ax2 = ax1.twinx()
    ax2.yaxis.tick_left()
    ax1.yaxis.tick_right()
    ax1.yaxis.set_label_position("right")
    ax2.yaxis.set_label_position("left")

    # Gas to process on the left axis, the other gas on the right axis
    ax1.plot(data[GAS_COLUMNS[other]], GAS_COLORS[other], linewidth=3)
    ax2.plot(data[GAS_COLUMNS[var]], GAS_COLORS[var], linewidth=3)
    ax1.set_ylabel(f"{other} (ppm)")
    ax2.set_ylabel(f"{var} (ppm)")
    for ax, gas, side in ((ax1, other, "right"), (ax2, var, "left")):
        ax.yaxis.label.set_color(GAS_COLORS[gas])
        ax.spines[side].set_color(GAS_COLORS[gas])
        ax.tick_params(axis="y", which="both", colors=GAS_COLORS[gas])
    ax2.set_ylim(ylim_min, ylim_max)
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
            window_artists.append(ax2.axvspan(xnum[i], xnum[j], color="g", alpha=0.2))
            r = np.corrcoef(xnum[i : j + 1], y[i : j + 1])[0, 1] if j - i >= 2 else np.nan
            window_artists.append(
                ax2.text(
                    (xnum[i] + xnum[j]) / 2, 0.98, f"{n}: r={r:.2f}",
                    transform=ax2.get_xaxis_transform(), ha="center", va="top",
                    fontsize=8, color="g",
                )
            )
        fig.canvas.draw_idle()

    def on_click(event):
        if event.button == MouseButton.MIDDLE:
            plt.close(fig)
            return
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


def plot_perflux(data, results, cfg):
    """One figure per flux with the data and the fitted line."""
    var = cfg["variable"]
    vard = GAS_COLUMNS[var]
    path_figout = _figure_folder(cfg)

    for _, res in results.iterrows():
        window = data[vard].iloc[res["ID start"] : res["ID end"] + 1]
        seconds = (window.index - window.index[0]).total_seconds()
        fitted = res["Intercept (ppm)"] + res["Slope (ppm/s)"] * seconds
        text = (
            f"$f(x)$ = {res['Slope (ppm/s)']:.2E}$x$ + {res['Intercept (ppm)']:.2f}\n"
            f"r = {res['Pearson']:.2f}\n"
            f"Flux = {res['Flux (mmol/m2/d)']:.3g} mmol m$^{{-2}}$ d$^{{-1}}$"
        )
        figf = plt.figure(figsize=(7, 5))
        axf = figf.add_subplot(111)
        axf.plot(seconds, window, "o", label="LGR data")
        axf.plot(seconds, fitted, "k-", label=text)
        axf.legend()
        axf.set_xlabel("Time (s)")
        axf.set_ylabel(vard)
        figffile = "_".join(
            [var, cfg["site"], "Flux", str(res["FID"]), cfg["file"] + ".png"]
        )
        figf.savefig(os.path.join(path_figout, figffile), format="png", dpi=300)
        plt.close(figf)


def plot_alldata(data, results, cfg):
    """Figure of the whole LGR file with the selected points."""
    var = cfg["variable"]
    path_figout = _figure_folder(cfg)

    fig = plt.figure(figsize=(10, 6))
    ax = fig.add_subplot(111)
    ax.plot(data.index, data[GAS_COLUMNS[var]], linewidth=3, label="data")
    ax.plot(
        results["Time start"], results["Value start (ppm)"], "ko", label="Selected points"
    )
    ax.plot(results["Time end"], results["Value end (ppm)"], "ko")
    ax.set_xlabel("Time")
    ax.set_ylabel(f"{var} (ppm)")
    ax.legend()
    figfilename = "_".join([cfg["site"], "points", var, cfg["file"] + ".png"])
    fig.savefig(os.path.join(path_figout, figfilename), format="png", dpi=300)
    plt.close(fig)
