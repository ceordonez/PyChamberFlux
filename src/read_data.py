#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import io
import os
import zipfile
from pathlib import Path

import pandas as pd
import yaml

# Cell temperature, temperature inside the analyser and cell pressure
DIAGNOSTIC_COLUMNS = ["GasT_C", "AmbT_C", "GasP_torr"]


def source_name(path) -> str:
    """Name of an LGR file without a ``.zip`` extension.

    ``gga_2025-07-19_f0003.txt.zip`` and ``gga_2025-07-19_f0003.txt`` hold the
    same data, so both are recorded (in the results and the campaign file) as
    ``gga_2025-07-19_f0003.txt``.
    """
    name = Path(path).name
    return name[: -len(".zip")] if name.lower().endswith(".zip") else name


def read_text(filename: str) -> str:
    """Text of an LGR file, plain (.txt) or zipped (.txt.zip, as the analyser archives them)."""
    if not os.path.isfile(filename):
        raise FileNotFoundError(f"The file '{filename}' does not exist.")
    if zipfile.is_zipfile(filename):
        with zipfile.ZipFile(filename) as zf:
            members = [m for m in zf.namelist() if m.lower().endswith(".txt")]
            if len(members) != 1:
                raise ValueError(f"expected one .txt file in {filename}, found {len(members)}")
            return zf.read(members[0]).decode("latin-1")
    with open(filename, encoding="latin-1") as fh:
        return fh.read()


def footer_pos(text: str) -> int:
    """Number of lines of the footer of an LGR file.

    Closed LGR files end with a signature block whose first line starts with
    ``-----B``; it is skipped when reading.

    Parameters
    ----------
    text : str
        Text of the LGR file (see `read_text`).

    Returns
    -------
    int
        Number of lines from the start of the footer to the end of the file
        (0 when there is no footer).
    """
    lines = text.splitlines()
    starts = [i for i, line in enumerate(lines) if line.startswith("-----B")]
    return len(lines) - starts[-1] if starts else 0


def read_lgr_file(filename: str) -> pd.DataFrame:
    """Read LGR file.

    Parameters
    ----------
    filename: str
        Path of the LGR file (.txt, or .txt.zip as archived by the analyser).

    Returns
    -------
    pd.DataFrame
        Data from the LGR file indexed by Time, columns [[CH4]d_ppm, [CO2]d_ppm]
        and the DIAGNOSTIC_COLUMNS present in the file.
    """
    text = read_text(filename)
    ifoot = footer_pos(text)

    try:
        data = pd.read_csv(
            io.StringIO(text),
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
