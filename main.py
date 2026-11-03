#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from src.plots import plot_data
from src.processing_data import processing_data
from src.read_data import read_config, read_lgr_data
from src.write import write_excelres


def main():

    cfg = read_config("config.yml")

    ## STEP 1: Read data
    data = read_lgr_data(cfg)

    ## STEP 2: Select the fluxes and calculate them
    results = processing_data(data, cfg)
    if results.empty:
        print("No fluxes selected, nothing to save.")
        return

    ## STEP 3: Save figures and results
    plot_data(data, results, cfg)
    write_excelres(data, results, cfg)


if __name__ == "__main__":
    main()
