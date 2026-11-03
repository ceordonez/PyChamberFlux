#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Detection of abrupt changes in a concentration record."""

import numpy as np
import pandas as pd

SMOOTH_SAMPLES = 5  # rolling median applied before taking the rate of change
JUMP_GAP = 5  # jumps closer than this (samples) are one jump


def find_jumps(seconds, values, threshold, direction=0):
    """Find abrupt changes: rate of change larger than threshold x noise.

    The noise is the robust standard deviation (MAD) of the rate of change of
    the smoothed series, so a steady trend (a chamber deployment) is not a
    jump, but a chamber being placed or lifted, or a bubble, is.

    Parameters
    ----------
    seconds : array
        Time of each sample (s)
    values : array
        Concentration
    threshold : float
        Jump if |rate - median rate| > threshold x noise
    direction : int
        0: any jump, 1: only increases, -1: only decreases

    Returns
    -------
    list of (int, int)
        First and last sample of each jump
    """
    seconds = np.asarray(seconds, dtype=float)
    values = np.asarray(values, dtype=float)
    if values.size < SMOOTH_SAMPLES:
        return []
    smooth = pd.Series(values).rolling(SMOOTH_SAMPLES, center=True, min_periods=1).median()
    rate = np.gradient(smooth.to_numpy(), seconds)
    deviation = rate - np.median(rate)
    noise = 1.4826 * np.median(np.abs(deviation))
    if noise == 0:
        return []
    if direction > 0:
        is_jump = deviation > threshold * noise
    elif direction < 0:
        is_jump = deviation < -threshold * noise
    else:
        is_jump = np.abs(deviation) > threshold * noise
    jumps = np.flatnonzero(is_jump)
    if jumps.size == 0:
        return []
    groups = np.split(jumps, np.flatnonzero(np.diff(jumps) > JUMP_GAP) + 1)
    return [(int(g[0]), int(g[-1])) for g in groups]
