"""Shared fixtures. Figures are drawn without a window (Agg backend)."""

import os

os.environ["MPLBACKEND"] = "Agg"  # before matplotlib is imported by src.plots

from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pytest  # noqa: E402

from src.fitting import GAS_COLUMNS  # noqa: E402
from src.read_data import read_lgr_file  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "example.txt"
# The three deployments of the example file (positions of first/last sample)
EXAMPLE_WINDOWS = [(262, 641), (721, 1133), (1210, 2030)]


@pytest.fixture(scope="session")
def example_data():
    return read_lgr_file(str(EXAMPLE))


@pytest.fixture
def cfg(tmp_path):
    """A complete configuration writing to a temporary folder."""
    return {
        "path_in": str(tmp_path),
        "path_out": str(tmp_path / "out"),
        "site": "Test",
        "Air": {"Temp": 30, "Pres": 1014},
        "Chamber": {"Volume": 16.76, "Area": 0.126},
    }


def synthetic_data(n=600, slope_ch4=1e-4, slope_co2=0.1, step=None, step_at=300, seed=1):
    """LGR-like data every second: lines plus noise, optionally a CH4 step."""
    rng = np.random.default_rng(seed)
    seconds = np.arange(n, dtype=float)
    ch4 = 2 + slope_ch4 * seconds + rng.normal(0, 3e-4, n)
    if step is not None:
        ch4[step_at:] += step
    co2 = 420 + slope_co2 * seconds + rng.normal(0, 0.2, n)
    index = pd.Timestamp("2025-01-11 12:00:00") + pd.to_timedelta(seconds, unit="s")
    return pd.DataFrame({GAS_COLUMNS["CH4"]: ch4, GAS_COLUMNS["CO2"]: co2}, index=index)
