#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Automatic pre-selection of chamber deployments.

A deployment shows up as a steady trend in the gas concentration that ends
abruptly when the chamber is lifted (or starts abruptly when it is placed).
The series is split at those abrupt changes ("breaks"), the first seconds
after each break are skipped (chamber settling), the start is moved to where
the series becomes linear, and only windows that are long and linear enough
are kept. The result is only a suggestion: the windows are shown on the
selection plot for the user to check and edit.
"""

import numpy as np

from src.fitting import GAS_COLUMNS
from src.jumps import find_jumps

# Defaults, can be overridden in the "Preselect" section of config.yml
DEFAULTS = {
    "enabled": True,
    "gas": "CO2",  # gas used to find the deployments (CH4 bubbles would split them)
    "jump_threshold": 15,  # break if rate of change > jump_threshold x noise
    "dead_time": 60,  # s skipped after each break
    "end_margin": 5,  # s skipped before each break
    "min_duration": 120,  # s, shortest window kept
    "min_r": 0.9,  # minimum |Pearson r| of a kept window
}

START_STEP = 10  # s, step when searching the start of the linear part
R2_TOLERANCE = 0.005  # earliest start within this of the best r^2


def preselect_windows(data, options=None):
    """Suggest flux windows in an LGR record.

    Parameters
    ----------
    data : DataFrame
        LGR data with a DatetimeIndex
    options : dict, optional
        Overrides for DEFAULTS

    Returns
    -------
    list of (int, int)
        Positions of the first and last sample of each suggested window
    """
    opt = {**DEFAULTS, **(options or {})}
    if not opt["enabled"] or len(data) < 3:
        return []

    seconds = (data.index - data.index[0]).total_seconds().to_numpy()
    values = data[GAS_COLUMNS[opt["gas"]]].to_numpy(dtype=float)

    windows = []
    for start, end in _segments(seconds, values, opt):
        window = _linear_part(seconds, values, start, end, opt)
        if window is not None:
            windows.append(window)
    return windows


def _segments(seconds, values, opt):
    """Parts of the record between breaks, without dead time and end margin."""
    # (first, last) sample of each break; the record edges act as breaks
    breaks = [(-1, -1)]
    breaks += find_jumps(seconds, values, opt["jump_threshold"])
    breaks.append((len(values), len(values)))

    segments = []
    for (_, prev_end), (next_start, _) in zip(breaks[:-1], breaks[1:]):
        if prev_end < 0:
            t0 = seconds[0]  # no settling time at the start of the file
        else:
            t0 = seconds[prev_end] + opt["dead_time"]
        if next_start >= len(values):
            t1 = seconds[-1]
        else:
            t1 = seconds[next_start] - opt["end_margin"]
        start = int(np.searchsorted(seconds, t0, side="left"))
        end = int(np.searchsorted(seconds, t1, side="right")) - 1
        if end > start:
            segments.append((start, end))
    return segments


def _r2(x, y):
    dx = x - x.mean()
    dy = y - y.mean()
    sxx, syy = np.sum(dx**2), np.sum(dy**2)
    if sxx == 0 or syy == 0:
        return 0.0
    return np.sum(dx * dy) ** 2 / (sxx * syy)


def _linear_part(seconds, values, start, end, opt):
    """Earliest start that gives (nearly) the best fit, or None if rejected."""
    t_end = seconds[end]
    if t_end - seconds[start] < opt["min_duration"]:
        return None

    best = []  # (start, r2)
    t_start = seconds[start]
    while t_end - t_start >= opt["min_duration"]:
        i = int(np.searchsorted(seconds, t_start, side="left"))
        best.append((i, _r2(seconds[i : end + 1], values[i : end + 1])))
        t_start += START_STEP
    r2_max = max(r2 for _, r2 in best)
    if r2_max < opt["min_r"] ** 2:
        return None
    first = next(i for i, r2 in best if r2 >= r2_max - R2_TOLERANCE)
    return first, end
