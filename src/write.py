#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Result files: CSV files per LGR file and per campaign, optionally Excel."""

import tomllib
from datetime import datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from src.bubbles import DEFAULTS as BUBBLE_DEFAULTS
from src.fitting import GAS_COLUMNS, fit_window, window_seconds
from src.preselect import DEFAULTS as PRESELECT_DEFAULTS
from src.processing_data import bubble_table
from src.read_data import DIAGNOSTIC_COLUMNS

FLUX_UNIT = "(mmol/m2/d)"

# Columns of the Results sheet, from the rows of calculate_fluxes:
# (column of the CH4/CO2 row, column of the Results sheet)
GAS_FIELDS = {
    "CH4": [
        ("Diffusive flux (mmol/m2/d)", f"CH4 diffusive flux {FLUX_UNIT}"),
        ("Diffusive flux SE (mmol/m2/d)", f"CH4 diffusive flux SE {FLUX_UNIT}"),
        ("Ebullitive flux (mmol/m2/d)", f"CH4 ebullitive flux {FLUX_UNIT}"),
        ("Total flux (mmol/m2/d)", f"CH4 total flux {FLUX_UNIT}"),
        ("N bubbles", "CH4 N bubbles"),
    ],
    "CO2": [
        ("Diffusive flux (mmol/m2/d)", f"CO2 flux {FLUX_UNIT}"),
        ("Diffusive flux SE (mmol/m2/d)", f"CO2 flux SE {FLUX_UNIT}"),
    ],
}
FIT_FIELDS = [
    ("Slope (ppm/s)", "slope (ppm/s)"),
    ("Std Error", "slope SE (ppm/s)"),
    ("Pearson", "r"),
    ("Intercept (ppm)", "intercept (ppm)"),
    ("Value start (ppm)", "start (ppm)"),
    ("Value end (ppm)", "end (ppm)"),
    ("N points", "N points"),
    ("Flag", "flag"),
]
WINDOW_FIELDS = ["Time start", "Time end", "Duration (s)"]
CHECK_FIELDS = ["GasT mean (degC)", "AmbT mean (degC)", "GasP mean (torr)", "ID start", "ID end"]

CSV_TIME = "%Y-%m-%d %H:%M:%S"
CSV_SAMPLE_TIME = "%Y-%m-%d %H:%M:%S.%f"  # samples are about 1 s apart

# Excel number formats
TIME_FORMAT = "yyyy-mm-dd hh:mm:ss"
FLOAT_FORMAT = "0.000"
SMALL_FORMAT = "0.00E+00"  # |value| < SMALL, so that small fluxes do not show as 0.000
SMALL = 0.01
SCIENTIFIC = ("slope", "Slope", "Jump")
R_FORMAT = "0.0000"


def write_results(data, results, cfg, name, source=None):
    """Save the results of one LGR file.

    In path_out/<site>_<name>/:
    - results.csv: one row per flux (both gases)
    - bubbles.csv: one row per CH4 jump removed from the fit
    - samples.csv: the samples of each flux with the fitted lines
    - settings.yml: configuration and versions used
    - <site>_<name>.xlsx with the same tables, if Output: excel is true

    The results and bubbles are also added to path_out/<site>_fluxes.csv and
    path_out/<site>_bubbles.csv, which collect all the files processed for
    the site; the rows of a file processed again are replaced.

    Parameters
    ----------
    source : str
        Name of the LGR file, written in the File column (default: name)
    """
    source = source or name
    folder = results_folder(cfg, name)
    folder.mkdir(parents=True, exist_ok=True)

    table = results_table(results, source)
    bubbles = bubble_table(cfg, data, results)
    bubbles.insert(0, "File", source)
    samples = pd.concat(
        [flux_samples(data, res, cfg).assign(Flux=fid) for fid, res in results.groupby("FID")],
        ignore_index=True,
    )
    samples.insert(0, "Flux", samples.pop("Flux"))
    settings = settings_dict(cfg, source)

    table.to_csv(folder / "results.csv", index=False, date_format=CSV_TIME)
    bubbles.to_csv(folder / "bubbles.csv", index=False, date_format=CSV_TIME)
    samples.to_csv(folder / "samples.csv", index=False, date_format=CSV_SAMPLE_TIME)
    with open(folder / "settings.yml", "w") as f:
        yaml.safe_dump(settings, f, sort_keys=False, allow_unicode=True)
    print(f"Results saved in {folder}")

    if (cfg.get("Output") or {}).get("excel", False):
        excelpath = folder / f"{cfg['site']}_{name}.xlsx"
        write_excel(excelpath, table, bubbles, samples, settings)
        print(f"Excel file saved: {excelpath}")

    site = Path(cfg["path_out"]) / cfg["site"]
    for path, rows, keys in (
        (f"{site}_fluxes.csv", table, ["Time start", "Flux"]),
        (f"{site}_bubbles.csv", bubbles, ["Time start", "Flux", "Bubble"]),
    ):
        update_campaign(Path(path), rows, source, keys)
        print(f"Added to {path}")


def results_folder(cfg, name):
    """Folder with the results of one LGR file."""
    return Path(cfg["path_out"]) / f"{cfg['site']}_{name}"


def saved_windows(cfg, name, data):
    """Windows of a file processed before, from its results.csv.

    Returns None if the file was not processed before or if the saved
    windows do not match the data (e.g. another file with the same name).
    """
    path = results_folder(cfg, name) / "results.csv"
    if not path.exists():
        return None
    try:
        saved = pd.read_csv(path, parse_dates=["Time start"])
        windows = [(int(a), int(b)) for a, b in zip(saved["ID start"], saved["ID end"])]
    except (KeyError, ValueError, pd.errors.ParserError):
        print(f"Could not read the windows saved in {path}, pre-selecting them again.")
        return None
    n = len(data)
    for (a, b), start in zip(windows, saved["Time start"]):
        if not (0 <= a < b < n) or abs((data.index[a] - start).total_seconds()) > 1:
            print(f"The windows saved in {path} do not match this file, pre-selecting them again.")
            return None
    return windows


def write_excel(path, table, bubbles, samples, settings):
    """The result tables in one formatted Excel file, one sheet per flux."""
    sheets = {"Results": table, "Bubbles": bubbles, "Settings": _flatten(settings)}
    for fid, rows in samples.groupby("Flux"):
        sheets[f"Flux {fid}"] = rows.drop(columns="Flux")
    with pd.ExcelWriter(path, engine="xlsxwriter") as writer:
        for sheet, frame in sheets.items():
            frame.to_excel(writer, sheet_name=sheet, index=False)
            _format_sheet(writer, sheet, frame)


def results_table(results, source):
    """One row per flux: window, then the CH4 and CO2 columns, then checks."""
    rows = []
    for fid, res in results.groupby("FID", sort=True):
        first = res.iloc[0]
        row = {"File": source, "Flux": fid}
        row.update({field: first[field] for field in WINDOW_FIELDS})
        for gas, fields in GAS_FIELDS.items():
            gas_row = res[res["Gas"] == gas].iloc[0]
            row.update({wide: gas_row[long] for long, wide in fields})
            row.update({f"{gas} {wide}": gas_row[long] for long, wide in FIT_FIELDS})
        row.update({field: first[field] for field in CHECK_FIELDS if field in first})
        rows.append(row)
    table = pd.DataFrame(rows)
    for column in ("CH4 N bubbles", "CH4 N points", "CO2 N points", "ID start", "ID end"):
        table[column] = table[column].astype(int)
    return table


def flux_samples(data, res, cfg):
    """Samples of one flux, with the fitted line of each gas."""
    idx1 = int(res["ID start"].iloc[0])
    idx2 = int(res["ID end"].iloc[0])
    seconds = window_seconds(data, idx1, idx2)
    samples = pd.DataFrame({"Time": data.index[idx1 : idx2 + 1], "Seconds (s)": seconds})
    for gas, column in GAS_COLUMNS.items():
        fit = fit_window(data, idx1, idx2, gas, cfg.get("Bubbles"))
        segment = fit.get("segment", np.zeros(len(seconds), dtype=int))
        offset = np.array([fit["offsets"].get(k, np.nan) for k in segment])
        samples[f"{gas} (ppm)"] = data[column].iloc[idx1 : idx2 + 1].to_numpy()
        samples[f"{gas} fit (ppm)"] = offset + fit["slope"] * seconds
        samples[f"{gas} used in fit"] = fit["used"]
    for column in DIAGNOSTIC_COLUMNS:
        if column in data.columns:
            samples[column] = data[column].iloc[idx1 : idx2 + 1].to_numpy()
    return samples


def settings_dict(cfg, source):
    """Configuration and versions used for the results."""
    return {
        "File": source,
        "Site": cfg["site"],
        "Processed": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Versions": {
            "PyChamberFlux": _project_version(),
            "pyghgaq": _package_version("pyghgaq"),
        },
        "Air": dict(cfg["Air"]),  # Temp (degC) and Pres (hPa), used for the flux
        "Chamber": dict(cfg["Chamber"]),  # Volume (L) and Area (m2)
        "Preselect": {**PRESELECT_DEFAULTS, **(cfg.get("Preselect") or {})},
        "Bubbles": {**BUBBLE_DEFAULTS, **(cfg.get("Bubbles") or {})},
    }


def _flatten(settings):
    """Settings as a two-column table (Setting, Value) for Excel."""
    rows = []
    for key, value in settings.items():
        if isinstance(value, dict):
            rows += [(f"{key}: {k}", str(v)) for k, v in value.items()]
        else:
            rows.append((key, str(value)))
    return pd.DataFrame(rows, columns=["Setting", "Value"])


def update_campaign(path, rows, source, sort_by):
    """Add the rows of one file to a campaign CSV.

    Rows of the same file already in the CSV are replaced.
    """
    if path.exists():
        old = pd.read_csv(path, parse_dates=["Time start", "Time end"])
        old = old[old["File"] != source]
        if not old.empty:
            rows = pd.concat([old, rows], ignore_index=True) if not rows.empty else old
    rows.sort_values(sort_by).to_csv(path, index=False, date_format=CSV_TIME)


def _project_version():
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    try:
        with open(pyproject, "rb") as f:
            return tomllib.load(f)["project"]["version"]
    except (OSError, KeyError, tomllib.TOMLDecodeError):
        return "unknown"


def _package_version(package):
    try:
        return version(package)
    except PackageNotFoundError:
        return "unknown"


def _format_sheet(writer, sheet, frame):
    """Header, number formats, column widths, frozen header and filters."""
    book = writer.book
    ws = writer.sheets[sheet]
    header = book.add_format({
        "bold": True, "text_wrap": True, "valign": "top",
        "bg_color": "#F0EFEC", "bottom": 1, "border_color": "#B4B2A9",
    })
    formats = {
        "time": book.add_format({"num_format": TIME_FORMAT}),
        "float": book.add_format({"num_format": FLOAT_FORMAT}),
        "sci": book.add_format({"num_format": SMALL_FORMAT}),
        "r": book.add_format({"num_format": R_FORMAT}),
        "int": book.add_format({"num_format": "0"}),
    }
    small = book.add_format({"num_format": SMALL_FORMAT})
    nrows = len(frame)

    for col, column in enumerate(frame.columns):
        ws.write(0, col, column, header)
        kind = frame[column].dtype.kind
        width = max(10, min(len(column) * 0.55 + 2, 22))
        fmt = None
        if kind == "M":
            fmt, width = formats["time"], 20
        elif kind == "f":
            if any(word in column for word in SCIENTIFIC):
                fmt = formats["sci"]
            elif column.endswith(" r"):
                fmt = formats["r"]
            elif column in ("Duration (s)", "Seconds (s)"):
                fmt = formats["int"] if column == "Duration (s)" else formats["float"]
            else:
                fmt = formats["float"]
                if nrows:
                    for low, high in ((-SMALL, -1e-12), (1e-12, SMALL)):
                        ws.conditional_format(1, col, nrows, col, {
                            "type": "cell", "criteria": "between",
                            "minimum": low, "maximum": high, "format": small,
                        })
        elif kind == "O":
            longest = frame[column].astype(str).str.len().max() if nrows else 0
            width = max(width, min(longest + 2, 45))
        ws.set_column(col, col, width, fmt)

    ws.set_row(0, 45 if sheet == "Results" else 30)
    ws.freeze_panes(1, 2 if sheet in ("Results", "Bubbles") else 1)
    if nrows:
        ws.autofilter(0, 0, nrows, len(frame.columns) - 1)
