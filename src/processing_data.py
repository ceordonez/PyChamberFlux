#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pandas as pd
import pyghgaq as pyg

from src.fitting import GAS_COLUMNS, fit_window
from src.plots import plot_select_points
from src.preselect import DEFAULTS as PRESELECT_DEFAULTS
from src.preselect import preselect_windows
from src.read_data import DIAGNOSTIC_COLUMNS

RESULT_COLUMNS = [
    "FID",
    "Gas",
    "ID start",
    "ID end",
    "Time start",
    "Time end",
    "Value start (ppm)",
    "Value end (ppm)",
    "Slope (ppm/s)",
    "Std Error",
    "Pearson",
    "Diffusive flux (mmol/m2/d)",
    "Diffusive flux SE (mmol/m2/d)",
    "N bubbles",
    "Total flux (mmol/m2/d)",
    "Ebullitive flux (mmol/m2/d)",
    "Intercept (ppm)",
    "N points",
    "Duration (s)",
    "Flag",
    "GasT mean (degC)",
    "AmbT mean (degC)",
    "GasP mean (torr)",
]

# Result column for each diagnostic column of the LGR file
DIAGNOSTIC_RESULTS = dict(zip(DIAGNOSTIC_COLUMNS, RESULT_COLUMNS[-3:]))


def processing_data(data, cfg, title=""):
    """Select the flux windows interactively and calculate the fluxes.

    Parameters
    ----------
    data: DataFrame
        LGR data
    cfg: dictionary
        Configuration information
    title: str
        Shown on the selection plot (e.g. the file name)

    Returns
    -------
    DataFrame
        Two rows per flux (CH4 and CO2), see calculate_fluxes.
    """
    suggested = preselect_windows(data, cfg.get("Preselect"))
    print(f"{len(suggested)} flux windows pre-selected, check them on the plot.")
    windows = plot_select_points(data, cfg, suggested, title=title)
    return calculate_fluxes(cfg, data, windows)


def calculate_fluxes(cfg, data, windows):
    """Fit each window and convert the slopes to fluxes, for CH4 and CO2.

    Parameters
    ----------
    cfg: dictionary
        Configuration information
    data: DataFrame
        LGR data with a DatetimeIndex
    windows: list of (int, int)
        Positions of the first and last sample of each flux

    Returns
    -------
    DataFrame
        One row per flux and gas with the columns in RESULT_COLUMNS. Slopes
        are fitted against the real time of each sample and converted to
        fluxes with pyghgaq.chamber_flux, with the chamber temperature and
        pressure from the configuration.

        "Diffusive flux" is the flux from the slope. For CH4 the jumps of
        the bubbles are removed before fitting the slope (see src.bubbles);
        "Ebullitive flux" is the sum of the jumps divided by the duration of
        the window (0 when no bubble is found) and "Total flux" = diffusive
        + ebullitive.

        The means of the LGR cell temperature, analyser temperature and cell
        pressure are only for checking the measurements.
    """
    bubble_options = cfg.get("Bubbles")
    quality = {**PRESELECT_DEFAULTS, **(cfg.get("Preselect") or {})}

    rows = []
    for fid, (idx1, idx2) in enumerate(windows, start=1):
        diagnostics = {
            name: data[c].iloc[idx1 : idx2 + 1].mean()
            for c, name in DIAGNOSTIC_RESULTS.items()
            if c in data.columns
        }
        for gas in ("CH4", "CO2"):
            window = data[GAS_COLUMNS[gas]].iloc[idx1 : idx2 + 1]
            fit = fit_window(data, idx1, idx2, gas, bubble_options)
            diffusive = to_flux(cfg, fit["slope"])
            duration = (window.index[-1] - window.index[0]).total_seconds()
            row = {
                "FID": fid,
                "Gas": gas,
                "ID start": idx1,
                "ID end": idx2,
                "Time start": window.index[0],
                "Time end": window.index[-1],
                "Value start (ppm)": window.iloc[0],
                "Value end (ppm)": window.iloc[-1],
                "Slope (ppm/s)": fit["slope"],
                "Std Error": fit["stderr"],
                "Pearson": fit["rvalue"],
                "Diffusive flux (mmol/m2/d)": diffusive,
                "Diffusive flux SE (mmol/m2/d)": abs(to_flux(cfg, fit["stderr"])),
                "Intercept (ppm)": fit["intercept"],
                "N points": fit["n"],
                "Duration (s)": duration,
                "Flag": quality_flag(fit["rvalue"], duration, quality),
                **diagnostics,
            }
            if gas == "CH4":
                # ebullition: sum of the bubble jumps over the window
                ebullitive = to_flux(cfg, sum(fit.get("jumps", [])) / duration)
                row["N bubbles"] = len(fit["bubbles"])
                row["Ebullitive flux (mmol/m2/d)"] = ebullitive
                row["Total flux (mmol/m2/d)"] = diffusive + ebullitive
            rows.append(row)
    return pd.DataFrame(rows, columns=RESULT_COLUMNS)


def to_flux(cfg, slope):
    """Flux (mmol m-2 d-1) from a slope (ppm/s), with the chamber of the configuration."""
    flux = pyg.chamber_flux(
        slope, cfg["Chamber"]["Volume"], cfg["Chamber"]["Area"],
        cfg["Air"]["Temp"], cfg["Air"]["Pres"],
    )
    return flux.to("mmol m^-2 d^-1").magnitude


def quality_flag(rvalue, duration, options):
    """Reasons to check a flux: |r| below min_r, window shorter than min_duration."""
    reasons = []
    if not abs(rvalue) >= options["min_r"]:
        reasons.append(f"|r| < {options['min_r']}")
    if duration < options["min_duration"]:
        reasons.append(f"shorter than {options['min_duration']} s")
    return "; ".join(reasons)


BUBBLE_COLUMNS = [
    "Flux",
    "Bubble",
    "Time start",
    "Time end",
    "N bubbles merged",
    "Jump (ppm)",
    "Ebullitive flux (mmol/m2/d)",
]


def bubble_table(cfg, data, results):
    """One row per CH4 jump removed from the fit.

    Bubbles too close together to fit a line between them give one jump
    ("N bubbles merged" > 1). Time start and end are the first and last
    sample of the abrupt increase. The ebullitive flux of each jump is the
    jump divided by the duration of the window; they add up to the
    ebullitive flux of the window.
    """
    rows = []
    ch4 = results[results["Gas"] == "CH4"]
    for _, res in ch4[ch4["N bubbles"] > 0].iterrows():
        idx1, idx2 = int(res["ID start"]), int(res["ID end"])
        fit = fit_window(data, idx1, idx2, "CH4", cfg.get("Bubbles"))
        segments = sorted(fit["offsets"])
        times = data.index[idx1 : idx2 + 1]
        for n, (a, b, jump) in enumerate(zip(segments[:-1], segments[1:], fit["jumps"]), start=1):
            # bubble k starts segment k + 1: the jump from a to b holds bubbles a .. b-1
            merged = fit["bubbles"][a:b]
            rows.append({
                "Flux": res["FID"],
                "Bubble": n,
                "Time start": times[merged[0][0]],
                "Time end": times[merged[-1][1]],
                "N bubbles merged": len(merged),
                "Jump (ppm)": jump,
                "Ebullitive flux (mmol/m2/d)": to_flux(cfg, jump / res["Duration (s)"]),
            })
    return pd.DataFrame(rows, columns=BUBBLE_COLUMNS)
