#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Floating chamber CH4 and CO2 fluxes from LGR files.

Usage:
    uv run main.py                     choose the files in a dialog
    uv run main.py FILE [FILE ...]     process these LGR files
    uv run main.py FOLDER              process all .txt files in the folder
    uv run main.py -c other.yml FILE   use another configuration file
    uv run main.py -n FOLDER           only the files not processed yet
    uv run main.py --batch FOLDER      recalculate the files processed before, with
                                       their saved windows, without the plot window
    uv run main.py --no-confirm FILE   without the window to check the settings
"""

import argparse
import sys
from pathlib import Path

from src.config import ConfigError, validate_config
from src.confirm import confirm_settings
from src.plots import plot_data
from src.processing_data import calculate_fluxes, processing_data
from src.read_data import read_config, read_lgr_file
from src.write import processed_files, results_folder, saved_windows, write_results

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


def process_file(path, cfg, progress="", batch=False):
    """Select the fluxes of one LGR file and save figures and results.

    progress (e.g. "3 of 12") is shown in the title of the selection plot.
    With batch=True, the windows saved when the file was processed before
    are used without showing the plot (files not processed before are
    skipped).

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
    if batch:
        if windows is None:
            print("Skipped: not processed before (no saved windows to recalculate).")
            return "skip"
        save_results(data, calculate_fluxes(cfg, data, windows), cfg, name, path)
        return "save"
    if windows is not None:
        print(f"Processed before: showing the {len(windows)} windows saved in "
              f"{results_folder(cfg, name)}.")
    title = f"{path.name}   ({progress})" if progress else path.name
    results, action = processing_data(data, cfg, title=title, windows=windows)
    if action == "skip":
        print("Skipped, nothing saved.")
        return action
    if action == "quit":
        print("Stopped, this file was not saved.")
        return action
    if results.empty:
        print("No fluxes selected, nothing saved.")
        return action

    save_results(data, results, cfg, name, path)
    return action


def save_results(data, results, cfg, name, path):
    """Figures and result files of one LGR file."""
    plot_data(data, results, cfg, name)
    write_results(data, results, cfg, name, source=path.name)


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
    parser.add_argument(
        "-n", "--new-only", action="store_true",
        help="skip the files already in <path_out>/<site>_fluxes.csv",
    )
    parser.add_argument(
        "--batch", action="store_true",
        help="recalculate the files processed before with their saved windows, without "
             "the plot window (e.g. after changing the configuration)",
    )
    parser.add_argument(
        "--no-confirm", action="store_true",
        help="do not show the window to check the settings before processing",
    )
    args = parser.parse_args(argv)

    try:
        cfg = validate_config(read_config(args.config), args.config)
    except (ConfigError, FileNotFoundError, ValueError) as e:
        sys.exit(str(e))
    print(f"Configuration: {args.config}")
    if not args.no_confirm:
        cfg = confirm_settings(cfg, args.config)
        if cfg is None:
            print("Cancelled.")
            return
    files = find_files(args.paths) if args.paths else ask_files(cfg.get("path_in"))
    if args.new_only:
        done = processed_files(cfg)
        skipped = [f for f in files if f.name in done]
        files = [f for f in files if f.name not in done]
        if skipped:
            print(f"Skipping {len(skipped)} file{'s' if len(skipped) > 1 else ''} "
                  f"already in the campaign file (--new-only).")
    if not files:
        print("No files to process.")
        return

    if args.batch:
        import matplotlib.pyplot as plt

        plt.switch_backend("Agg")  # figures are only saved, no window needed
    for n, path in enumerate(files, start=1):
        if process_file(path, cfg, f"{n} of {len(files)}", args.batch) == "quit":
            remaining = len(files) - n
            if remaining:
                print(f"{remaining} file{'s' if remaining > 1 else ''} not processed.")
            break


if __name__ == "__main__":
    main()
