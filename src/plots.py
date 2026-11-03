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


def plot_select_points(data, cfg):
    """Select the start and end of each flux by clicking on the plot.

    Left click: add the nearest sample. Right click: remove the last point.
    Middle click or closing the window: finish.

    Returns
    -------
    list of (int, int)
        Positions of the first and last sample of each flux, in the order the
        points were clicked (start/end pairs).
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
        "Left click: add point (start, end, start, end, ...)   "
        "Right click: remove last point   Middle click: finish"
    )
    (marks,) = ax2.plot([], [], "or")

    selected = []

    def on_click(event):
        if event.button == MouseButton.MIDDLE:
            plt.close(fig)
            return
        if event.button == MouseButton.LEFT:
            if event.inaxes is None or event.xdata is None:
                return  # click outside the plot
            idx = int(np.abs(xnum - event.xdata).argmin())
            if idx in selected:
                return
            selected.append(idx)
        elif event.button == MouseButton.RIGHT:
            if not selected:
                return
            selected.pop()
        else:
            return
        marks.set_data(xnum[selected], y[selected])
        fig.canvas.draw_idle()

    # Keep a reference to the cursor, otherwise it is garbage collected
    cursor = Cursor(ax=ax2, useblit=False, color="red", linewidth=2)  # noqa: F841
    fig.canvas.mpl_connect("button_press_event", on_click)
    plt.show()

    return points_to_windows(selected)


def points_to_windows(points):
    """Group clicked sample positions into (start, end) pairs.

    An unpaired last point and windows with fewer than MIN_POINTS samples
    are dropped with a warning. A pair clicked end-first is reordered.
    """
    if len(points) % 2:
        print(f"Warning: odd number of points, the last point ({points[-1]}) is ignored.")
    windows = []
    for start, end in zip(points[::2], points[1::2]):
        start, end = sorted((start, end))
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
