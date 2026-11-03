"""
Configuration utilities for LGR_SurfFlux.

This module loads a YAML configuration file and validates its contents,
ensuring required fields are present and applying sensible defaults.
"""

import yaml
from pathlib import Path


class ConfigError(Exception):
    """Raised when the configuration file is invalid or incomplete."""
    pass


def load_config(path):
    """
    Load and validate a YAML configuration file.

    Parameters
    ----------
    path : str or Path
        Path to the YAML configuration file.

    Returns
    -------
    dict
        Nested configuration dictionary with validated keys and defaults applied.

    Raises
    ------
    ConfigError
        If the configuration file is missing required sections or keys.
    """
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"Configuration file not found: {path}")

    # --- Load YAML ---
    try:
        with open(path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ConfigError(f"YAML parsing error in {path}: {e}")

    if not isinstance(cfg, dict):
        raise ConfigError(f"Configuration file {path} must define a dictionary at the top level.")

    # --- Validate sections ---
    for section in ("data", "regions", "output"):
        if section not in cfg:
            raise ConfigError(f"Missing required section '{section}' in configuration file.")

    # --- Validate data section ---
    data = cfg["data"]
    if "path" not in data:
        raise ConfigError("Missing 'data.path' in configuration file.")
    data.setdefault("time_col", "time")
    data.setdefault("value_col", "value")

    # --- Validate regions section ---
    regions = cfg["regions"]
    if not isinstance(regions, list) or len(regions) == 0:
        raise ConfigError("Configuration must include a non-empty 'regions' list.")
    for region in regions:
        if "start" not in region or "end" not in region:
            raise ConfigError("Each region must include 'start' and 'end' keys.")

    # --- Validate output section ---
    output = cfg["output"]
    output.setdefault("csv", None)
    output.setdefault("excel", None)
    output.setdefault("plots_dir", "plots")

    # --- Ensure output folder exists ---
    if output["plots_dir"]:
        Path(output["plots_dir"]).mkdir(parents=True, exist_ok=True)

    return cfg

