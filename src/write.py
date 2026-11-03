#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os

import pandas as pd

from src.fitting import GAS_COLUMNS, fit_window
from src.read_data import DIAGNOSTIC_COLUMNS

NUMBER_FORMATS = {
    "Time start": "yyyy/mm/dd hh:mm:ss",
    "Time end": "yyyy/mm/dd hh:mm:ss",
    "Slope (ppm/s)": "0.00E+0",
    "Std Error": "0.00E+0",
}
FLOAT_FORMAT = "0.000"


def write_excelres(data, results, cfg, name):
    """Excel file with the raw data of each flux and a sheet with the results.

    Saved as path_out/<site>_<name>.xlsx. The FID_n sheets have both gases,
    the LGR diagnostics and whether each CH4 sample was used in the fit (not
    used: while a bubble mixes in the chamber).
    """
    path_out = cfg["path_out"]
    os.makedirs(path_out, exist_ok=True)
    excelpath = os.path.join(path_out, "_".join([cfg["site"], name]) + ".xlsx")

    columns = list(GAS_COLUMNS.values()) + [c for c in DIAGNOSTIC_COLUMNS if c in data.columns]
    with pd.ExcelWriter(
        excelpath, datetime_format="mmm d yyyy hh:mm:ss", engine="xlsxwriter"
    ) as writer:
        # Raw LGR data of each flux
        for fid, res in results.groupby("FID", sort=True):
            idx1 = int(res["ID start"].iloc[0])
            idx2 = int(res["ID end"].iloc[0])
            window = data[columns].iloc[idx1 : idx2 + 1].copy()
            fit = fit_window(data, idx1, idx2, "CH4", cfg.get("Bubbles"))
            window["CH4 used in fit"] = fit["used"]
            window.to_excel(writer, sheet_name=f"FID_{fid}")

        # Final results
        results.to_excel(writer, sheet_name="Results", index=False)
        workbook = writer.book
        worksheet = writer.sheets["Results"]
        floatformat = workbook.add_format({"num_format": FLOAT_FORMAT})
        for col, column in enumerate(results.columns):
            if column in NUMBER_FORMATS:
                fmt = workbook.add_format({"num_format": NUMBER_FORMATS[column]})
                worksheet.set_column(col, col, 20 if "Time" in column else None, fmt)
            elif results[column].dtype.kind == "f":
                worksheet.set_column(col, col, None, floatformat)
    print(f"Results saved in {excelpath}")
