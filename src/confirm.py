#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Window to check (and edit) the settings that change between campaigns.

The values are checked with the configuration checks before starting.
Changes apply to this run; with "Save", they are also written to the
configuration file, keeping its comments and the other settings.
"""

import copy
import re
import shutil
import subprocess
import sys
from pathlib import Path

from src.config import ConfigError, validate_config

# (section or None, key, label, unit or hint, kind); kind: text, path, number, optional
FIELDS = [
    (None, "site", "Site", "used in the file names", "text"),
    (None, "path_out", "Output folder", "", "path"),
    ("Chamber", "Volume", "Chamber volume", "L, with tubing and analyser", "number"),
    ("Chamber", "Area", "Chamber area", "m²", "number"),
    ("Air", "Temp", "Air temperature", "°C, when not in the field log", "number"),
    ("Air", "Pres", "Air pressure", "hPa, when not in the field log", "number"),
    ("FieldLog", "file", "Field log", "CSV, empty: none", "path"),
    ("FieldLog", "time_offset", "Field log time offset", "s, LGR - field log", "optional"),
    ("Quality", "CH4_precision", "CH₄ precision", "ppm, empty: from the data", "optional"),
    ("Quality", "CO2_precision", "CO₂ precision", "ppm, empty: from the data", "optional"),
]


def current_values(cfg):
    """The values of FIELDS in the configuration, as text for the entries."""
    values = {}
    for section, key, _, _, _ in FIELDS:
        value = cfg.get(key) if section is None else (cfg.get(section) or {}).get(key)
        values[(section, key)] = "" if value is None else str(value)
    return values


def parse_values(texts):
    """Entry texts -> values: numbers where possible, empty -> None."""
    values = {}
    for section, key, label, _, kind in FIELDS:
        text = texts[(section, key)].strip()
        if kind in ("number", "optional"):
            if not text:
                values[(section, key)] = None
                continue
            try:
                number = float(text.replace(",", "."))
            except ValueError:
                raise ConfigError(f"{label} must be a number, found {text!r}.") from None
            values[(section, key)] = int(number) if number.is_integer() else number
        else:
            values[(section, key)] = text or None
    return values


def apply_values(cfg, values, filename):
    """Configuration with the new values, checked; raises ConfigError."""
    new = copy.deepcopy({k: v for k, v in cfg.items() if not k.startswith("_")})
    for (section, key), value in values.items():
        if section is None:
            new[key] = value
        else:
            new.setdefault(section, None)
            new[section] = dict(new[section] or {})
            new[section][key] = value
    return validate_config(new, filename)


def changed_values(cfg, values):
    """The values that differ from the configuration."""
    old = parse_values(current_values(cfg))
    return {field: value for field, value in values.items() if value != old[field]}


def _yaml_value(value):
    if value is None:
        return ""
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    return str(value)


def update_yaml(path, values):
    """Write values into a YAML configuration file, keeping its comments.

    values: {(section or None, key): value}. Existing keys are replaced in
    place (their comments kept); missing ones are added to their section,
    or with a new section at the end.
    """
    path = Path(path)
    lines = path.read_text().splitlines()
    pending = dict(values)
    section = None
    key_line = re.compile(
        r"^(?P<indent>\s*)(?P<key>[\w.-]+):(?P<value>[^#]*?)(?P<comment>\s*#.*)?$"
    )
    section_end = {}  # section -> index after its last line
    for n, line in enumerate(lines):
        match = key_line.match(line)
        if not match:
            continue
        indent, key = match["indent"], match["key"]
        if not indent:
            section = key
            section_end[section] = n + 1
            field = (None, key)
        else:
            section_end[section] = n + 1
            field = (section, key)
        if field in pending:
            value = _yaml_value(pending.pop(field))
            space = " " if value else ""
            lines[n] = f"{indent}{key}:{space}{value}{match['comment'] or ''}"
    # keys not in the file: add them to their section, or a new section
    for (field_section, key), value in sorted(pending.items(), key=lambda kv: str(kv[0])):
        text = f"{key}: {_yaml_value(value)}".rstrip()
        if field_section is None:
            lines.append(text)
        elif field_section in section_end:
            lines.insert(section_end[field_section], "  " + text)
            for name, end in section_end.items():
                if end >= section_end[field_section] and name != field_section:
                    section_end[name] = end + 1
            section_end[field_section] += 1
        else:
            lines += ["", f"{field_section}:", "  " + text]
            section_end[field_section] = len(lines)
    path.write_text("\n".join(lines) + "\n")


def existing_parent(text):
    """The folder itself or its nearest existing parent (start of the dialogs)."""
    path = Path(text).expanduser() if text.strip() else Path.home()
    while not path.is_dir() and path != path.parent:
        path = path.parent
    return path if path.is_dir() else Path.home()


def zenity_command(folder, current):
    """zenity command for the system file dialog: a folder or a CSV file."""
    if folder:
        command = ["zenity", "--file-selection", "--directory",
                   "--title=Choose the output folder"]
        start = existing_parent(current)
    else:
        command = ["zenity", "--file-selection", "--title=Choose the field log",
                   "--file-filter=CSV files | *.csv", "--file-filter=All files | *"]
        path = Path(current).expanduser()
        start = path if current.strip() and path.is_file() else existing_parent(current)
    # a trailing separator opens the dialog inside the folder
    return [*command, f"--filename={start}{'/' if start.is_dir() else ''}"]


def system_dialog(folder, current):
    """Choose with the system file dialog (zenity) on Linux.

    The Tk dialogs on Linux cannot create folders; zenity (GNOME/GTK) can.
    Returns the chosen path, "" if cancelled, or None when zenity is not
    available (then the Tk dialog is used; on Windows and macOS Tk already
    uses the system dialog).
    """
    if not sys.platform.startswith("linux") or shutil.which("zenity") is None:
        return None
    try:
        done = subprocess.run(zenity_command(folder, current), capture_output=True, text=True)
    except OSError:
        return None
    if done.returncode == 0:
        return done.stdout.strip()
    return "" if done.returncode == 1 else None  # 1: cancelled; other: zenity failed


def summary(cfg):
    """The values of FIELDS as text, for the terminal."""
    values = current_values(cfg)
    width = max(len(label) for _, _, label, _, _ in FIELDS)
    lines = []
    for section, key, label, unit, _ in FIELDS:
        value = values[(section, key)]
        lines.append(f"  {label:<{width}}  {value or '-'} {unit if value else ''}".rstrip())
    return "\n".join(lines)


def confirm_settings(cfg, filename):
    """Show the window; return the configuration to use, or None if cancelled.

    Without a display, the values are printed and the configuration is
    returned unchanged.
    """
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk

        root = tk.Tk()
    except Exception:  # no display (e.g. a server): just show the values
        print(f"Settings ({filename}):\n{summary(cfg)}")
        return cfg

    root.title("PyChamberFlux: check the settings")
    result = {"cfg": None}
    texts = current_values(cfg)
    entries = {}

    frame = ttk.Frame(root, padding=16)
    frame.grid(sticky="nsew")
    ttk.Label(frame, text=f"Settings from {filename}", font=("TkDefaultFont", 11, "bold")).grid(
        row=0, column=0, columnspan=4, sticky="w", pady=(0, 4))
    ttk.Label(frame, text="Check them before processing. Changes apply to this run.",
              foreground="#52514e").grid(row=1, column=0, columnspan=4, sticky="w", pady=(0, 10))

    for row, (section, key, label, unit, kind) in enumerate(FIELDS, start=2):
        ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=2)
        var = tk.StringVar(value=texts[(section, key)])
        entry = ttk.Entry(frame, textvariable=var, width=45 if kind in ("text", "path") else 14)
        entry.grid(row=row, column=1, sticky="w", pady=2)
        entries[(section, key)] = var
        ttk.Label(frame, text=unit, foreground="#8a8984").grid(row=row, column=2, sticky="w",
                                                              padx=(8, 0))
        if kind == "path":
            def browse(var=var, key=key):
                chosen = system_dialog(key != "file", var.get())
                if chosen is None and key == "file":
                    chosen = filedialog.askopenfilename(
                        filetypes=[("CSV files", "*.csv"), ("All files", "*")])
                elif chosen is None:
                    chosen = filedialog.askdirectory(initialdir=existing_parent(var.get()))
                if chosen:
                    var.set(chosen)

            ttk.Button(frame, text="Browse…", command=browse).grid(row=row, column=3, padx=(8, 0))

    save = tk.BooleanVar(value=False)
    ttk.Checkbutton(frame, text=f"Save changes to {Path(filename).name}", variable=save).grid(
        row=len(FIELDS) + 2, column=0, columnspan=4, sticky="w", pady=(10, 0))

    def start(event=None):
        try:
            values = parse_values({field: var.get() for field, var in entries.items()})
            new = apply_values(cfg, values, filename)
        except ConfigError as e:
            messagebox.showerror("Please fix the settings", str(e), parent=root)
            return
        if save.get():
            changed = changed_values(cfg, values)
            if changed:
                update_yaml(filename, changed)
                print(f"Saved {len(changed)} change(s) to {filename}.")
        result["cfg"] = new
        root.destroy()

    def cancel(event=None):
        root.destroy()

    buttons = ttk.Frame(frame)
    buttons.grid(row=len(FIELDS) + 3, column=0, columnspan=4, sticky="e", pady=(12, 0))
    ttk.Button(buttons, text="Cancel", command=cancel).grid(row=0, column=0, padx=(0, 8))
    ttk.Button(buttons, text="Start", command=start, default="active").grid(row=0, column=1)
    root.bind("<Return>", start)
    root.bind("<Escape>", cancel)
    root.protocol("WM_DELETE_WINDOW", cancel)
    root.resizable(False, False)
    root.update_idletasks()
    root.geometry(f"{frame.winfo_reqwidth()}x{frame.winfo_reqheight()}")  # fit the contents
    root.mainloop()
    return result["cfg"]
