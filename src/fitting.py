#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Slope of each gas in a flux window."""

import numpy as np
import pyghgaq as pyg

from src.bubbles import detect_bubbles, stepped_fit

# LGR columns with the dry mole fractions
GAS_COLUMNS = {"CH4": "[CH4]d_ppm", "CO2": "[CO2]d_ppm"}


def window_seconds(data, idx1, idx2):
    """Seconds since the first sample of the window."""
    index = data.index[idx1 : idx2 + 1]
    return (index - index[0]).total_seconds().to_numpy()


def fit_window(data, idx1, idx2, gas, bubble_options=None):
    """Slope of one gas in one window.

    CH4 is fitted with a step at each bubble (see src.bubbles); without
    bubbles, and for CO2, it is a plain line (pyghgaq.chamber_slope).

    Returns
    -------
    dict
        slope and stderr (ppm/s), rvalue, intercept (ppm), n, bubbles (list
        of (first, last) relative to the window), used (mask of the samples
        used) and offsets (intercept of each segment between bubbles)
    """
    window = data[GAS_COLUMNS[gas]].iloc[idx1 : idx2 + 1]
    seconds = window_seconds(data, idx1, idx2)
    bubbles = detect_bubbles(seconds, window.to_numpy(), bubble_options) if gas == "CH4" else []
    if bubbles:
        return {**stepped_fit(seconds, window.to_numpy(), bubbles, bubble_options), "bubbles": bubbles}
    fit = pyg.chamber_slope(seconds, window)
    return {
        "slope": fit.slope.to("ppm/s").magnitude,
        "stderr": fit.stderr.to("ppm/s").magnitude,
        "rvalue": fit.rvalue,
        "intercept": fit.intercept.to("ppm").magnitude,
        "n": fit.n,
        "bubbles": [],
        "used": np.ones(len(window), dtype=bool),
        "offsets": {0: fit.intercept.to("ppm").magnitude},
    }
