#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Floating chamber CH4 and CO2 fluxes from LGR files.

Usage:
    python main.py                     choose the files in a dialog
    python main.py FILE [FILE ...]     process these LGR files
    python main.py FOLDER              process all .txt files in the folder
    python main.py -c other.yml FILE   use another configuration file
"""

import argparse
import sys
from pathlib import Path

from src.plots import plot_data
from src.processing_data import processing_data
from src.read_data import read_config, read_lgr_file
from src.write import write_excelres

HERE = Path(__file__).resolve().parent


def find_files(paths):
    """LGR files from the arguments: files as given, folders -> their .txt files."""
    files = []
    for path in map(Path, paths):
        if path.is_dir():
            found = sorted(path.glob("*.txt"))
            if not found:
                print(f"No .txt files in {path}")
            files += found
        elif path.is_file():
            files.append(path)
        else:
            print(f"Not found: {path}")
    return files


def ask_files(initialdir=None):
    """Choose LGR files in a dialog."""
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError:
        sys.exit("No file dialog available, give the LGR files as arguments: python main.py FILE")
    root = tk.Tk()
    root.withdraw()
    names = filedialog.askopenfilenames(
        title="Select LGR files",
        initialdir=initialdir if initialdir and Path(initialdir).is_dir() else None,
        filetypes=[("LGR files", "*.txt"), ("All files", "*")],
    )
    root.destroy()
    return [Path(name) for name in names]


def process_file(path, cfg):
    """Select the fluxes of one LGR file and save figures and results."""
    print(f"\n=== {path}")
    try:
        data = read_lgr_file(str(path))
    except (KeyError, ValueError) as e:
        print(f"Skipped, not a readable LGR file: {e}")
        return
    if data.empty:
        print("Skipped, no data.")
        return

    results = processing_data(data, cfg, title=path.name)
    if results.empty:
        print("No fluxes selected, nothing saved.")
        return

    name = path.stem
    plot_data(data, results, cfg, name)
    write_excelres(data, results, cfg, name)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Floating chamber CH4 and CO2 fluxes from LGR files."
    )
    parser.add_argument(
        "paths", nargs="*",
        help="LGR files or folders (all .txt files). Without paths, a dialog opens.",
    )
    parser.add_argument(
        "-c", "--config", default=str(HERE / "config.yml"),
        help="configuration file (default: config.yml next to main.py)",
    )
    args = parser.parse_args(argv)

    cfg = read_config(args.config)
    files = find_files(args.paths) if args.paths else ask_files(cfg.get("path_in"))
    if not files:
        print("No files to process.")
        return

    for path in files:
        process_file(path, cfg)


if __name__ == "__main__":
    main()
