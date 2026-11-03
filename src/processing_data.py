#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pandas as pd

from src.fieldlog import conditions
from src.fitting import GAS_COLUMNS, assess_fit, fit_window, to_flux
from src.plots import plot_select_points
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
    "Precision (ppm)",
    "MDF (mmol/m2/d)",
    "Quadratic flux (mmol/m2/d)",
    "Nonlinearity",
    "Flag",
    "Air temp (degC)",
    "Air pres (hPa)",
    "GasT mean (degC)",
    "AmbT mean (degC)",
    "GasP mean (torr)",
]

# Result column for each diagnostic column of the LGR file
DIAGNOSTIC_RESULTS = dict(zip(DIAGNOSTIC_COLUMNS, RESULT_COLUMNS[-3:]))


def processing_data(data, cfg, title="", windows=None):
    """Select the flux windows interactively and calculate the fluxes.

    Parameters
    ----------
    data: DataFrame
        LGR data
    cfg: dictionary
        Configuration information
    title: str
        Shown on the selection plot (e.g. the file name)
    windows: list of (int, int), optional
        Windows shown at the start (e.g. saved when the file was processed
        before). By default they are pre-selected automatically.

    Returns
    -------
    results : DataFrame
        Two rows per flux (CH4 and CO2), see calculate_fluxes.
    action : str
        "save", "skip" (nothing to save) or "quit" (stop processing files)
    """
    if windows is None:
        windows = preselect_windows(data, cfg.get("Preselect"))
        print(f"{len(windows)} flux windows pre-selected, check them on the plot.")
    windows, action = plot_select_points(data, cfg, windows, title=title)
    if action != "save":
        return pd.DataFrame(columns=RESULT_COLUMNS), action
    return calculate_fluxes(cfg, data, windows), action


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

        The air temperature and pressure of each flux come from the field log
        (FieldLog: file) when it has a row for the flux, otherwise from Air in
        the configuration. The extra columns of the field log (e.g. Location)
        are added after RESULT_COLUMNS.

        "MDF" is the minimum detectable flux and "Quadratic flux" the flux
        from the initial slope of a quadratic fit, as a check of the
        linearity ("Nonlinearity" = quadratic / linear slope - 1); see
        src.fitting.assess_fit. "Flag" lists the reasons to check the flux.
    """
    bubble_options = cfg.get("Bubbles")

    rows = []
    extras = []
    unmatched = 0
    for fid, (idx1, idx2) in enumerate(windows, start=1):
        field = conditions(cfg, data.index[idx1])
        unmatched += not field.pop("_matched", True)
        temp, pres = field.pop("Temp"), field.pop("Pres")
        extras = list(field)

        def flux(slope):
            return to_flux(cfg, slope, temp, pres)

        diagnostics = {
            name: data[c].iloc[idx1 : idx2 + 1].mean()
            for c, name in DIAGNOSTIC_RESULTS.items()
            if c in data.columns
        }
        for gas in ("CH4", "CO2"):
            window = data[GAS_COLUMNS[gas]].iloc[idx1 : idx2 + 1]
            fit = fit_window(data, idx1, idx2, gas, bubble_options)
            quality = assess_fit(cfg, data, idx1, idx2, gas, fit, temp, pres)
            diffusive = quality["flux"]
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
                "Diffusive flux SE (mmol/m2/d)": abs(flux(fit["stderr"])),
                "Intercept (ppm)": fit["intercept"],
                "N points": fit["n"],
                "Duration (s)": duration,
                "Precision (ppm)": quality["precision"],
                "MDF (mmol/m2/d)": quality["mdf"],
                "Quadratic flux (mmol/m2/d)": quality["quad_flux"],
                "Nonlinearity": quality["nonlinearity"],
                "Flag": quality["flag"],
                "Air temp (degC)": temp,
                "Air pres (hPa)": pres,
                **diagnostics,
                **field,
            }
            if gas == "CH4":
                # ebullition: sum of the bubble jumps over the window
                ebullitive = flux(sum(fit.get("jumps", [])) / duration)
                row["N bubbles"] = len(fit["bubbles"])
                row["Ebullitive flux (mmol/m2/d)"] = ebullitive
                row["Total flux (mmol/m2/d)"] = diffusive + ebullitive
            rows.append(row)
    if unmatched and unmatched == len(windows):
        print("Warning: no flux of this file matches a row of the field log; Air of the "
              "configuration was used. Check the dates and FieldLog: time_offset.")
    elif unmatched:
        print(f"Warning: {unmatched} flux{'es' if unmatched > 1 else ''} without a row in the "
              "field log; Air of the configuration was used for them.")
    return pd.DataFrame(rows, columns=RESULT_COLUMNS + extras)


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
                "Ebullitive flux (mmol/m2/d)": to_flux(
                    cfg, jump / res["Duration (s)"], res["Air temp (degC)"], res["Air pres (hPa)"]
                ),
            })
    return pd.DataFrame(rows, columns=BUBBLE_COLUMNS)
