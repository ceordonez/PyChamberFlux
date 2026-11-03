#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pandas as pd
import pyghgaq as pyg

from src.plots import plot_select_points

# LGR columns with the dry mole fractions
GAS_COLUMNS = {"CH4": "[CH4]d_ppm", "CO2": "[CO2]d_ppm"}

RESULT_COLUMNS = [
    "FID",
    "ID start",
    "ID end",
    "Time start",
    "Time end",
    "Value start (ppm)",
    "Value end (ppm)",
    "Slope (ppm/s)",
    "Std Error",
    "Pearson",
    "Flux (mmol/m2/d)",
    "Temp (degC)",
    "Press (hPa)",
    "Intercept (ppm)",
    "N points",
]


def processing_data(data, cfg):
    """Select the flux windows interactively and calculate the fluxes.

    Parameters
    ----------
    data: DataFrame
        LGR data
    cfg: dictionary
        Configuration information

    Returns
    -------
    DataFrame
        One row per flux, see calculate_fluxes.
    """
    windows = plot_select_points(data, cfg)
    return calculate_fluxes(cfg, data, windows)


def calculate_fluxes(cfg, data, windows):
    """Fit a line to each window and convert the slope to a flux.

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
        One row per flux with the columns in RESULT_COLUMNS. The slope is
        fitted against the real time of each sample (pyghgaq.chamber_slope)
        and the flux uses pyghgaq.chamber_flux.
    """
    temp = cfg["Air"]["Temp"]
    press = cfg["Air"]["Pres"]
    vol = cfg["Chamber"]["Volume"]
    area = cfg["Chamber"]["Area"]
    col = GAS_COLUMNS[cfg["variable"]]

    rows = []
    for fid, (idx1, idx2) in enumerate(windows, start=1):
        window = data[col].iloc[idx1 : idx2 + 1]
        fit = pyg.chamber_slope(window.index, window)
        flux = pyg.chamber_flux(fit.slope, vol, area, temp, press)
        rows.append(
            {
                "FID": fid,
                "ID start": idx1,
                "ID end": idx2,
                "Time start": window.index[0],
                "Time end": window.index[-1],
                "Value start (ppm)": window.iloc[0],
                "Value end (ppm)": window.iloc[-1],
                "Slope (ppm/s)": fit.slope.to("ppm/s").magnitude,
                "Std Error": fit.stderr.to("ppm/s").magnitude,
                "Pearson": fit.rvalue,
                "Flux (mmol/m2/d)": flux.to("mmol m^-2 d^-1").magnitude,
                "Temp (degC)": temp,
                "Press (hPa)": press,
                "Intercept (ppm)": fit.intercept.to("ppm").magnitude,
                "N points": fit.n,
            }
        )
    return pd.DataFrame(rows, columns=RESULT_COLUMNS)
