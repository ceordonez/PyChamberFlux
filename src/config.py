#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Check config.yml before processing, with messages that say what to fix."""

from numbers import Real
from pathlib import Path

from src.bubbles import DEFAULTS as BUBBLE_DEFAULTS
from src.fieldlog import FieldLogError, field_log
from src.fitting import GAS_COLUMNS
from src.preselect import DEFAULTS as PRESELECT_DEFAULTS

# Required numbers: (section, key, description, must be > 0)
REQUIRED_NUMBERS = [
    ("Air", "Temp", "air temperature in the chamber (degC)", False),
    ("Air", "Pres", "air pressure in the chamber (hPa)", True),
    ("Chamber", "Volume", "chamber volume, including tubing and analyser (L)", True),
    ("Chamber", "Area", "chamber area (m2)", True),
]
OPTIONAL_SECTIONS = {
    "Preselect": PRESELECT_DEFAULTS,
    "Bubbles": BUBBLE_DEFAULTS,
    "Plot": {"ylim_min": None, "ylim_max": None},
    "Output": {"excel": False},
    "FieldLog": {"file": None},
}
KNOWN_KEYS = {"path_in", "path_out", "site", "Air", "Chamber", *OPTIONAL_SECTIONS}


class ConfigError(ValueError):
    """config.yml has missing or wrong values."""


def _is_number(value):
    return isinstance(value, Real) and not isinstance(value, bool)


def _kind(default):
    """What a setting must be, from its default value."""
    if isinstance(default, bool):
        return "true or false"
    if _is_number(default):
        return "a number"
    return f"text (e.g. {default})"


def _matches(value, default):
    """True if value has the kind of its default (None: anything goes)."""
    if value is None or default is None:
        return True
    if isinstance(default, bool):
        return isinstance(value, bool)
    if _is_number(default):
        return _is_number(value)
    return isinstance(value, type(default))


def validate_config(cfg, filename="config.yml"):
    """Check the configuration and return it.

    Raises
    ------
    ConfigError
        With one line per problem found.
    """
    if not isinstance(cfg, dict):
        raise ConfigError(f"{filename} is empty or is not a list of 'key: value' settings.")
    problems = []
    warnings = []

    for key in ("path_out", "site"):
        if not isinstance(cfg.get(key), str) or not cfg[key].strip():
            problems.append(f"'{key}' is missing (e.g. {key}: 'Gambia').")

    for section, key, description, positive in REQUIRED_NUMBERS:
        values = cfg.get(section)
        if not isinstance(values, dict):
            problems.append(f"Section '{section}' is missing.")
            continue
        value = values.get(key)
        if not _is_number(value):
            problems.append(f"'{section}: {key}' ({description}) must be a number, found {value!r}.")
        elif positive and value <= 0:
            problems.append(f"'{section}: {key}' ({description}) must be > 0, found {value}.")

    for section, defaults in OPTIONAL_SECTIONS.items():
        values = cfg.get(section)
        if values is None:
            continue
        if not isinstance(values, dict):
            problems.append(f"Section '{section}' must contain 'key: value' lines.")
            continue
        for key, value in values.items():
            if key not in defaults:
                problems.append(
                    f"Unknown setting '{section}: {key}'. Valid: {', '.join(defaults)}."
                )
            elif not _matches(value, defaults[key]):
                problems.append(
                    f"'{section}: {key}' must be {_kind(defaults[key])}, found {value!r}."
                )
    gas = (cfg.get("Preselect") or {}).get("gas", "CO2")
    if gas not in GAS_COLUMNS:
        problems.append(f"'Preselect: gas' must be one of {', '.join(GAS_COLUMNS)}, found {gas!r}.")

    if not problems:
        log_cfg = cfg.get("FieldLog") or {}
        if log_cfg.get("file"):
            # a relative path is relative to the folder of the configuration file
            path = Path(log_cfg["file"]).expanduser()
            if not path.is_absolute():
                path = Path(filename).resolve().parent / path
            log_cfg["file"] = str(path)
        try:
            field_log(cfg)  # read it now, so that its errors show before processing
        except FieldLogError as e:
            problems.append(str(e))

    for key in cfg:
        if key.startswith("_"):
            continue
        if key not in KNOWN_KEYS:
            warnings.append(f"Unknown setting '{key}' is ignored.")

    for warning in warnings:
        print(f"Warning ({filename}): {warning}")
    if problems:
        raise ConfigError(
            f"Please fix {filename}:\n" + "\n".join(f"  - {p}" for p in problems)
        )
    return cfg
