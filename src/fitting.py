#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Slope of each gas in a flux window, flux, detection limit and quality."""

import numpy as np
import pyghgaq as pyg

from src.bubbles import detect_bubbles, stepped_fit

# LGR columns with the dry mole fractions
GAS_COLUMNS = {"CH4": "[CH4]d_ppm", "CO2": "[CO2]d_ppm"}

# Defaults, can be overridden in the "Quality" section of config.yml
QUALITY_DEFAULTS = {
    "max_nonlinearity": 0.2,  # flag when the quadratic initial slope differs more
    "CH4_precision": None,  # ppm; None: estimated from the noise of each window
    "CO2_precision": None,
}


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
        fit = stepped_fit(seconds, window.to_numpy(), bubbles, bubble_options)
        return {**fit, "bubbles": bubbles}
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


def to_flux(cfg, slope, temp=None, pres=None):
    """Flux (mmol m-2 d-1) from a slope (ppm/s), with the chamber of the configuration.

    temp (degC) and pres (hPa) default to Air: Temp / Pres of the configuration.
    """
    flux = pyg.chamber_flux(
        slope, cfg["Chamber"]["Volume"], cfg["Chamber"]["Area"],
        cfg["Air"]["Temp"] if temp is None else temp,
        cfg["Air"]["Pres"] if pres is None else pres,
    )
    return flux.to("mmol m^-2 d^-1").magnitude


def quality_flag(rvalue, duration, options, below_mdf=False, nonlinearity=None):
    """Reasons to check a flux, separated by "; ".

    - below the minimum detectable flux (then a low r is expected and not
      reported);
    - |r| below min_r;
    - window shorter than min_duration;
    - quadratic initial slope differing from the linear slope by more than
      max_nonlinearity (only for fluxes above the detection limit):
      "saturating" when the initial slope is steeper (the concentration
      levels off, the linear fit underestimates the flux at closure) and
      "accelerating" when it is flatter (often the chamber still settling
      at the start of the window).
    """
    reasons = []
    if below_mdf:
        reasons.append("below detection limit")
    elif not abs(rvalue) >= options["min_r"]:
        reasons.append(f"|r| < {options['min_r']}")
    if duration < options["min_duration"]:
        reasons.append(f"shorter than {options['min_duration']} s")
    limit = options.get("max_nonlinearity")
    if (limit is not None and not below_mdf and nonlinearity is not None
            and abs(nonlinearity) > limit):
        # saturating: slower at the end (linear fit underestimates the initial
        # flux); accelerating: faster at the end (often settling at the start)
        shape = "saturating" if nonlinearity > 0 else "accelerating"
        reasons.append(f"nonlinear, {shape} ({nonlinearity:+.0%})")
    return "; ".join(reasons)


def noise(values):
    """Sample-to-sample noise (ppm): robust std of the differences / sqrt(2).

    Robust (median absolute deviation), so that bubbles and the trend of the
    window do not count as noise.
    """
    diffs = np.diff(np.asarray(values, dtype=float))
    if diffs.size < 2:
        return np.nan
    mad = np.median(np.abs(diffs - np.median(diffs)))
    return float(1.4826 * mad / np.sqrt(2))


def jump_shift(fit, n):
    """Cumulative bubble jump (ppm) before each of the n samples of a window."""
    segment = fit.get("segment", np.zeros(n, dtype=int))
    return np.array([fit["offsets"].get(k, np.nan) - fit["intercept"] for k in segment])


def quadratic_fit(seconds, values, fit):
    """Coefficients (c2, c1, c0) of a quadratic fit, or None if too few samples.

    Fitted to the samples used for the linear fit, with the bubble jumps
    removed (Wagner et al., 1997). c1 is the initial slope (ppm/s, at the
    start of the window).
    """
    used = fit["used"]
    x = np.asarray(seconds, dtype=float)[used]
    y = (np.asarray(values, dtype=float) - jump_shift(fit, len(values)))[used]
    if x.size < 4:
        return None
    return np.polyfit(x, y, 2)


def quadratic_slope(seconds, values, fit):
    """Initial slope (ppm/s) of the quadratic fit, see quadratic_fit."""
    coefs = quadratic_fit(seconds, values, fit)
    return np.nan if coefs is None else float(coefs[1])


def assess_fit(cfg, data, idx1, idx2, gas, fit, temp=None, pres=None):
    """Flux, detection limit, non-linearity and flag of one gas in one window.

    The minimum detectable flux is MDF = (A / t_c) P V / (R T A_c)
    (Christiansen et al., 2015), with A the precision of the analyser (ppm),
    t_c the duration of the window and A_c the chamber area: the flux that
    changes the concentration by one precision unit over the window.

    Returns
    -------
    dict
        flux, mdf, quad_flux (mmol m-2 d-1), precision (ppm), nonlinearity
        (quadratic initial slope / linear slope - 1) and flag
    """
    from src.preselect import DEFAULTS as PRESELECT_DEFAULTS

    options = {**PRESELECT_DEFAULTS, **(cfg.get("Preselect") or {}),
               **QUALITY_DEFAULTS, **(cfg.get("Quality") or {})}
    values = data[GAS_COLUMNS[gas]].iloc[idx1 : idx2 + 1].to_numpy()
    seconds = window_seconds(data, idx1, idx2)
    duration = seconds[-1]
    precision = options[f"{gas}_precision"]
    if precision is None:
        precision = noise(values)
    flux = to_flux(cfg, fit["slope"], temp, pres)
    mdf = abs(to_flux(cfg, precision / duration, temp, pres)) if duration > 0 else np.nan
    quad = quadratic_slope(seconds, values, fit)
    nonlinearity = quad / fit["slope"] - 1 if fit["slope"] != 0 else np.nan
    below = bool(abs(flux) < mdf)
    return {
        "flux": flux,
        "mdf": mdf,
        "precision": precision,
        "quad_flux": to_flux(cfg, quad, temp, pres),
        "nonlinearity": nonlinearity,
        "below_mdf": below,
        "flag": quality_flag(fit["rvalue"], duration, options, below, nonlinearity),
    }
