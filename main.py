#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Floating chamber CH4 and CO2 fluxes from LGR files.

Usage:
    uv run main.py                     choose the files in a dialog
    uv run main.py FILE [FILE ...]     process these LGR files
    uv run main.py FOLDER              process all .txt files in the folder
    uv run main.py -c other.yml FILE   use another configuration file
"""

import argparse
import sys
from pathlib import Path

from src.config import ConfigError, validate_config
from src.plots import plot_data
from src.processing_data import processing_data
from src.read_data import read_config, read_lgr_file
from src.write import results_folder, saved_windows, write_results

HERE = Path(__file__).resolve().parent


def default_config():
    """config.local.yml (personal, not tracked by git) if it exists, else config.yml."""
    local = HERE / "config.local.yml"
    return local if local.exists() else HERE / "config.yml"


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
        sys.exit("No file dialog available, give the LGR files as arguments: uv run main.py FILE")
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
    """Select the fluxes of one LGR file and save figures and results.

    Returns "save", "skip" or "quit" (stop processing the remaining files).
    """
    print(f"\n=== {path}")
    try:
        data = read_lgr_file(str(path))
    except (KeyError, ValueError) as e:
        print(f"Skipped, not a readable LGR file: {e}")
        return "skip"
    if data.empty:
        print("Skipped, no data.")
        return "skip"

    name = path.stem
    windows = saved_windows(cfg, name, data)
    if windows is not None:
        print(f"Processed before: showing the {len(windows)} windows saved in "
              f"{results_folder(cfg, name)}.")
    results, action = processing_data(data, cfg, title=path.name, windows=windows)
    if action == "skip":
        print("Skipped, nothing saved.")
        return action
    if action == "quit":
        print("Stopped, this file was not saved.")
        return action
    if results.empty:
        print("No fluxes selected, nothing saved.")
        return action

    plot_data(data, results, cfg, name)
    write_results(data, results, cfg, name, source=path.name)
    return action


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Floating chamber CH4 and CO2 fluxes from LGR files."
    )
    parser.add_argument(
        "paths", nargs="*",
        help="LGR files or folders (all .txt files). Without paths, a dialog opens.",
    )
    parser.add_argument(
        "-c", "--config", default=str(default_config()),
        help="configuration file (default: config.local.yml next to main.py if it "
             "exists, otherwise config.yml)",
    )
    args = parser.parse_args(argv)

    try:
        cfg = validate_config(read_config(args.config), args.config)
    except (ConfigError, FileNotFoundError, ValueError) as e:
        sys.exit(str(e))
    print(f"Configuration: {args.config}")
    files = find_files(args.paths) if args.paths else ask_files(cfg.get("path_in"))
    if not files:
        print("No files to process.")
        return

    for n, path in enumerate(files, start=1):
        if process_file(path, cfg) == "quit":
            remaining = len(files) - n
            if remaining:
                print(f"{remaining} file{'s' if remaining > 1 else ''} not processed.")
            break


if __name__ == "__main__":
    main()
