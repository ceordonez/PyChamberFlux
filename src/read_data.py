#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os

import pandas as pd
import yaml

# Cell temperature, temperature inside the analyser and cell pressure
DIAGNOSTIC_COLUMNS = ["GasT_C", "AmbT_C", "GasP_torr"]


def footer_pos(filename: str) -> int:
    """Find footer position in LGR file.

    Parameters
    ----------
    filename : str
        File name of LGR file.

    Returns
    -------
    int
        Starting line number of the footer of the LGR file.
    """
    # Ensure the file exists before attempting to open it
    if not os.path.isfile(filename):
        raise FileNotFoundError(f"The file '{filename}' does not exist.")

    with open(filename, "r") as z:
        i = 0
        ib = None  # Initialize ib to avoid potential unbound variable error
        for line in z:
            if line.startswith("-----B"):
                ib = i
            i += 1

        # Check if the footer marker was found
        if ib is not None:
            ifooter = i - ib
        else:
            ifooter = 0

    return ifooter


def read_lgr_data(cfg: dict) -> pd.DataFrame:
    """Read LGR file.

    Parameters
    ----------
    cfg: dict
        Configuration dictionary with the following keys:
        - "date" (str): Date string for the file path.
        - "path_in" (str): Base directory for the input file.
        - "file" (str): Name of the input file without extension.

    Returns
    -------
    pd.DataFrame
        Data from the LGR file indexed by Time, columns [[CH4]d_ppm, [CO2]d_ppm]
        and the DIAGNOSTIC_COLUMNS present in the file.
    """
    # Validate required keys in cfg
    required_keys = ["date", "path_in", "file"]
    for key in required_keys:
        if key not in cfg:
            raise KeyError(f"Missing required configuration key: {key}")

    date = cfg["date"]
    path = cfg["path_in"]
    inputfile = cfg["file"]

    filename = os.path.join(path, date, inputfile + ".txt")

    # Ensure footer_pos function is defined or imported
    ifoot = footer_pos(filename)

    try:
        data = pd.read_csv(
            filename,
            sep=",",
            header=1,
            skipfooter=ifoot,
            engine="python",
        )
        # Strip whitespace from column names
        data.columns = [item.strip() for item in data.columns]
        # Instrument diagnostics, kept to check the measurements (the flux
        # uses the chamber temperature and pressure from the configuration)
        diagnostics = [c for c in DIAGNOSTIC_COLUMNS if c in data.columns]
        data = data.loc[:, ["Time", "[CH4]d_ppm", "[CO2]d_ppm", *diagnostics]]
    except FileNotFoundError:
        raise FileNotFoundError(f"The file {filename} does not exist.")
    except ValueError as e:
        raise ValueError(f"Error reading the file {filename}: {e}")

    # Remove the first three rows (e.g., warm-up data)
    data = data.iloc[3:].copy()

    # Ensure 'Time' column exists
    if "Time" not in data.columns:
        raise KeyError("The required 'Time' column is missing in the data.")

    # Parse the "Time" column as datetime
    data["Time"] = pd.to_datetime(
        data["Time"].str.strip(), format="%d/%m/%Y %H:%M:%S.%f"
    )
    # Keep the sub-second timestamps: the LGR logs every ~0.995 s and the
    # slopes are fitted against the real time of each sample

    # Set 'Time' as the index
    data = data.set_index("Time")

    return data


def read_config(filename: str) -> dict:
    """Read configuration file.

    Parameters
    ----------
    filename : str
        File name of the configuration process file.

    Returns
    -------
    dict
        Configuration data as a dictionary.
    """
    # Validate that the filename is not empty
    if not filename:
        raise ValueError("The filename must not be empty.")

    # Ensure the file exists before attempting to open it
    if not os.path.isfile(filename):
        raise FileNotFoundError(f"The file '{filename}' does not exist.")

    # Read the configuration file safely
    with open(filename, "r") as file:
        try:
            conf_file = yaml.safe_load(file)
        except yaml.YAMLError as e:
            raise ValueError(f"Error parsing the YAML file '{filename}': {e}")

    return conf_file
