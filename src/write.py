#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os

import pandas as pd

from src.processing_data import GAS_COLUMNS


def write_excelres(data, results, cfg):
    """Excel file with the raw data of each flux and a sheet with the results."""
    path_out = cfg["path_out"]
    var = cfg["variable"]
    vard = GAS_COLUMNS[var]

    os.makedirs(path_out, exist_ok=True)
    excel_filename = "_".join([var, cfg["site"], cfg["file"] + ".xlsx"])
    excelpath = os.path.join(path_out, excel_filename)

    with pd.ExcelWriter(
        excelpath, datetime_format="mmm d yyyy hh:mm:ss", engine="xlsxwriter"
    ) as writer:
        # Raw LGR data of each flux
        for _, res in results.iterrows():
            window = data[vard].iloc[res["ID start"] : res["ID end"] + 1]
            window.to_excel(writer, sheet_name=f"FID_{res['FID']}")

        # Final results
        results.to_excel(writer, sheet_name="Results", index=False)
        workbook = writer.book
        worksheet = writer.sheets["Results"]
        dateformat = workbook.add_format({"num_format": "yyyy/mm/dd hh:mm:ss"})
        sciformat = workbook.add_format({"num_format": "0.00E+0"})
        floatformat = workbook.add_format({"num_format": "0.000"})
        # Columns follow processing_data.RESULT_COLUMNS
        worksheet.set_column("D:E", 20, dateformat)  # Time start, Time end
        worksheet.set_column("F:G", None, floatformat)  # Values
        worksheet.set_column("H:I", None, sciformat)  # Slope, Std Error
        worksheet.set_column("J:K", None, floatformat)  # Pearson, Flux
        worksheet.set_column("N:N", None, floatformat)  # Intercept
    print(f"Results saved in {excelpath}")
