#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CH4 bubbles (ebullition) inside a chamber deployment.

A bubble reaching the chamber shows up as an abrupt increase of CH4, after
which the concentration keeps rising with the diffusive slope. The size of
each jump is estimated locally, from lines fitted just before and just after
the bubble (the samples while it mixes in the chamber are excluded). The
jumps are removed and one line is fitted to the whole window, as for a window
without bubbles: its slope gives the diffusive flux. The sum of the jumps
divided by the duration of the window gives the ebullitive flux, and the
total flux is diffusive + ebullitive.
"""

import numpy as np

from src.jumps import find_jumps

# Defaults, can be overridden in the "Bubbles" section of config.yml
DEFAULTS = {
    "enabled": True,
    "threshold": 10,  # bubble if CH4 increases faster than threshold x noise
    "before": 3,  # s excluded before each bubble
    "mixing_time": 20,  # s excluded after each bubble (mixing in the chamber)
    "jump_window": 60,  # s on each side of a bubble used to estimate its jump
}
MIN_SEGMENT = 3  # segments with fewer samples are not used for the slope


def detect_bubbles(seconds, ch4, options=None):
    """Abrupt CH4 increases inside a window.

    Returns
    -------
    list of (int, int)
        First and last sample of each bubble, relative to the window
    """
    opt = {**DEFAULTS, **(options or {})}
    if not opt["enabled"]:
        return []
    return find_jumps(seconds, ch4, opt["threshold"], direction=1)


def excluded_samples(seconds, bubbles, options=None):
    """Boolean mask of the samples excluded around the bubbles."""
    opt = {**DEFAULTS, **(options or {})}
    seconds = np.asarray(seconds, dtype=float)
    excluded = np.zeros(seconds.size, dtype=bool)
    for first, last in bubbles:
        t0 = seconds[first] - opt["before"]
        t1 = seconds[last] + opt["mixing_time"]
        excluded |= (seconds >= t0) & (seconds <= t1)
    return excluded


def stepped_fit(seconds, values, bubbles, options=None):
    """Diffusive slope of a window with bubbles.

    The jump of each bubble is the difference, at the middle of the excluded
    gap, between lines fitted to the jump_window seconds before and after
    it. The jumps are subtracted and one line is fitted to the samples
    outside the bubbles. seconds should start at 0 at the beginning of the
    window.

    Returns
    -------
    dict
        slope, stderr (per s), rvalue and intercept of the line fitted to the
        data without the jumps, n (samples used), used (boolean mask),
        segment (segment of each sample: part of the window after bubble k),
        offsets (dict segment -> intercept of its line, i.e. intercept plus
        the jumps before it) and jumps (size of each jump, ppm)
    """
    opt = {**DEFAULTS, **(options or {})}
    seconds = np.asarray(seconds, dtype=float)
    values = np.asarray(values, dtype=float)
    used = ~excluded_samples(seconds, bubbles, opt)
    segment = np.zeros(seconds.size, dtype=int)
    for first, _ in bubbles:
        segment[first:] += 1
    for k in np.unique(segment):
        if np.sum(used & (segment == k)) < MIN_SEGMENT:
            used &= segment != k
    segments = np.unique(segment[used]).tolist()
    if not segments:
        raise ValueError("not enough samples outside the bubbles to fit a slope")

    # cumulative jump before each segment
    shift = {segments[0]: 0.0}
    jumps = []
    for a, b in zip(segments[:-1], segments[1:]):
        t_a = seconds[used & (segment == a)]
        t_b = seconds[used & (segment == b)]
        left = used & (segment == a) & (seconds >= t_a[-1] - opt["jump_window"])
        right = used & (segment == b) & (seconds <= t_b[0] + opt["jump_window"])
        t_mid = (t_a[-1] + t_b[0]) / 2
        jump = np.polyval(np.polyfit(seconds[right], values[right], 1), t_mid) - np.polyval(
            np.polyfit(seconds[left], values[left], 1), t_mid
        )
        jumps.append(float(jump))
        shift[b] = shift[a] + jump

    x = seconds[used]
    y = values[used] - np.array([shift[k] for k in segment[used]])
    n = x.size
    dx = x - x.mean()
    dy = y - y.mean()
    sxx = np.sum(dx**2)
    syy = np.sum(dy**2)
    slope = np.sum(dx * dy) / sxx
    intercept = y.mean() - slope * x.mean()
    resid = dy - slope * dx
    stderr = float(np.sqrt(np.sum(resid**2) / (n - 2) / sxx)) if n > 2 else np.nan
    rvalue = float(np.sum(dx * dy) / np.sqrt(sxx * syy)) if syy > 0 else 0.0
    return {
        "slope": float(slope),
        "stderr": stderr,
        "rvalue": rvalue,
        "intercept": float(intercept),
        "n": int(n),
        "used": used,
        "segment": segment,
        "offsets": {k: float(intercept + shift[k]) for k in segments},
        "jumps": jumps,
    }
