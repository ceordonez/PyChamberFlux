#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Optional field log: air conditions and notes for each deployment.

The field log is a CSV file with one row per location (or per deployment):

    Start,End,Temp,Pres,Location,Notes
    2025-01-11 17:30,2025-01-11 17:50,31.5,1013,Site A,3 chambers
    2025-01-11 17:50,,29.8,1014,Site B,

- Start (required): when the row starts to apply, as YYYY-MM-DD HH:MM[:SS],
  in the same clock as the LGR analyser.
- End (optional): when it stops applying. Without End, a row applies until
  the Start of the next row, and at most until the end of its day.
- Temp (degC) and Pres (hPa) (optional): air temperature and pressure in the
  chamber. Empty values (or no column) use Air: Temp / Pres of config.yml.
- Any other column (Location, Chamber, Notes, ...) is copied to the results.
- Empty rows and columns without a name and without values (e.g. trailing
  commas left by a spreadsheet) are ignored.

A template is in examples/fieldlog.csv.

If the clock of the LGR analyser and the field log differ, set
FieldLog: time_offset (seconds) so that field-log time + time_offset =
LGR time (e.g. 3600 if the LGR is one hour ahead).

A flux uses the row that applies at the start of its window. Fluxes without
a row use the values of config.yml and empty extra columns.
"""

from pathlib import Path

import pandas as pd

TIME_COLUMNS = ["Start", "End"]
CONDITION_COLUMNS = {"Temp": "Temp", "Pres": "Pres"}  # field log -> config Air key


class FieldLogError(ValueError):
    """The field log cannot be read or has wrong values."""


def load_field_log(path):
    """Read and check a field log.

    Returns
    -------
    DataFrame
        Sorted by Start, with an End column (NaT when not given).
    """
    path = Path(path)
    if not path.is_file():
        raise FieldLogError(f"Field log not found: {path}")
    try:
        log = pd.read_csv(path, skipinitialspace=True)
    except (pd.errors.ParserError, UnicodeDecodeError) as e:
        raise FieldLogError(f"Cannot read the field log {path}: {e}") from e
    log.columns = [str(c).strip() for c in log.columns]
    # spreadsheets leave empty rows and unnamed empty columns (trailing commas)
    unnamed = [c for c in log.columns if c == "" or c.startswith("Unnamed:")]
    log = log.drop(columns=[c for c in unnamed if log[c].isna().all()])
    log = log.dropna(how="all").reset_index(drop=True)
    if "Start" not in log.columns:
        raise FieldLogError(f"The field log {path} needs a 'Start' column.")
    if "End" not in log.columns:
        log["End"] = pd.NaT
    for column in TIME_COLUMNS:
        parsed = pd.to_datetime(log[column], format="ISO8601", errors="coerce")
        bad = parsed.isna() & log[column].notna()
        if bad.any():
            line = log.index[bad][0] + 2  # header is line 1
            raise FieldLogError(
                f"'{column}' in the field log {path} must be dates like 2025-01-11 17:30 "
                f"(year first); line {line} has {log.loc[bad, column].iloc[0]!r}."
            )
        log[column] = parsed
    if log["Start"].isna().any():
        rows = (log.index[log["Start"].isna()] + 2).tolist()
        raise FieldLogError(f"Rows without Start in the field log {path}: lines {rows}.")
    for column in CONDITION_COLUMNS:
        if column in log.columns and not pd.api.types.is_numeric_dtype(log[column]):
            raise FieldLogError(f"'{column}' in the field log {path} must be numbers.")
    bad = log["End"].notna() & (log["End"] <= log["Start"])
    if bad.any():
        raise FieldLogError(
            f"End is not after Start in the field log {path}: "
            f"lines {(log.index[bad] + 2).tolist()}."
        )
    return log.sort_values("Start", ignore_index=True)


def extra_columns(log):
    """Columns of the field log copied to the results."""
    return [c for c in log.columns if c not in TIME_COLUMNS and c not in CONDITION_COLUMNS]


def missing_conditions(log, cfg):
    """Warnings for Temp / Pres columns missing in the field log.

    A misspelt column (e.g. 'Press') would otherwise only be copied to the
    results while the values of the configuration are used.
    """
    names = {"Temp": ("temperature", "degC"), "Pres": ("pressure", "hPa")}
    warnings = []
    for column, key in CONDITION_COLUMNS.items():
        if column in log.columns:
            continue
        similar = [c for c in log.columns if c.lower().startswith(column.lower()[:3])]
        hint = f" Rename {similar[0]!r} to '{column}' to use it." if similar else ""
        what, unit = names[column]
        warnings.append(
            f"Warning: the field log has no '{column}' column; the air {what} of the "
            f"configuration is used for all fluxes (Air: {key} = {cfg['Air'][key]} {unit}).{hint}"
        )
    return warnings


def field_log(cfg):
    """The field log of the configuration (read once), in the LGR clock, or None."""
    options = cfg.get("FieldLog") or {}
    path = options.get("file")
    if not path:
        return None
    offset = options.get("time_offset") or 0
    cached = cfg.get("_field_log")
    if cached is None or cached[0] != (path, offset):
        log = load_field_log(path)
        for warning in missing_conditions(log, cfg):
            print(warning)
        shift = pd.Timedelta(seconds=offset)
        log["Start"] += shift
        log["End"] += shift
        cfg["_field_log"] = ((path, offset), log)
    return cfg["_field_log"][1]


def conditions(cfg, start):
    """Air conditions and field-log columns for a flux starting at `start`.

    Returns
    -------
    dict
        Temp (degC), Pres (hPa) and the extra columns of the field log (empty
        strings when no row applies). With a field log, "_matched" says
        whether a row applies.
    """
    result = {"Temp": cfg["Air"]["Temp"], "Pres": cfg["Air"]["Pres"]}
    log = field_log(cfg)
    if log is None:
        return result
    extras = extra_columns(log)
    result.update({c: "" for c in extras})
    result["_matched"] = False
    before = log[log["Start"] <= start]
    if before.empty:
        return result
    row = before.iloc[-1]
    # without End: until the next Start (already ensured) or the end of the day
    end = row["End"] if pd.notna(row["End"]) else row["Start"].normalize() + pd.Timedelta(days=1)
    if end < start:
        return result
    result["_matched"] = True
    for column, key in CONDITION_COLUMNS.items():
        if column in log.columns and pd.notna(row[column]):
            result[key] = float(row[column])
    result.update({c: ("" if pd.isna(row[c]) else row[c]) for c in extras})
    return result
