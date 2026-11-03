#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pandas as pd
import pyghgaq as pyg

from src.fitting import GAS_COLUMNS, fit_window, window_seconds
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
    "N bubbles",
    "Total flux (mmol/m2/d)",
    "Ebullitive flux (mmol/m2/d)",
    "Temp (degC)",
    "Press (hPa)",
    "Intercept (ppm)",
    "N points",
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
    temp = cfg["Air"]["Temp"]
    press = cfg["Air"]["Pres"]
    vol = cfg["Chamber"]["Volume"]
    area = cfg["Chamber"]["Area"]
    bubble_options = cfg.get("Bubbles")

    def flux(slope):
        return pyg.chamber_flux(slope, vol, area, temp, press).to("mmol m^-2 d^-1").magnitude

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
            diffusive = flux(fit["slope"])
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
                "Temp (degC)": temp,
                "Press (hPa)": press,
                "Intercept (ppm)": fit["intercept"],
                "N points": fit["n"],
                **diagnostics,
            }
            if gas == "CH4":
                # ebullition: sum of the bubble jumps over the window
                seconds = window_seconds(data, idx1, idx2)
                ebullitive = flux(sum(fit.get("jumps", [])) / seconds[-1])
                row["N bubbles"] = len(fit["bubbles"])
                row["Ebullitive flux (mmol/m2/d)"] = ebullitive
                row["Total flux (mmol/m2/d)"] = diffusive + ebullitive
            rows.append(row)
    return pd.DataFrame(rows, columns=RESULT_COLUMNS)
