"""Slopes, fluxes, bubbles and quality flags."""

import pytest
from conftest import EXAMPLE_WINDOWS, synthetic_data

from src.bubbles import detect_bubbles
from src.fitting import fit_window, quality_flag, to_flux, window_seconds
from src.plots import points_to_windows
from src.processing_data import bubble_table, calculate_fluxes

# Reference results of the example file (regression: these must not change
# unless the method changes on purpose)
EXPECTED = {
    # (flux, gas): (slope ppm/s, diffusive flux mmol/m2/d, samples)
    (1, "CH4"): (0.00022271154967307637, 0.10296891792406532, 380),
    (1, "CO2"): (0.12354298970461795, 57.11912105888556, 380),
    (2, "CH4"): (0.00030171855554596576, 0.1394971802216141, 413),
    (2, "CO2"): (0.17728121701344923, 81.96456407820978, 413),
    (3, "CH4"): (0.0006064347805997748, 0.2803803091556757, 821),
    (3, "CO2"): (0.2838241447545379, 131.22384137238603, 821),
}


def test_example_fluxes_do_not_change(cfg, example_data):
    results = calculate_fluxes(cfg, example_data, EXAMPLE_WINDOWS)
    assert len(results) == 6
    for _, row in results.iterrows():
        slope, flux, n = EXPECTED[(row["FID"], row["Gas"])]
        assert row["Slope (ppm/s)"] == pytest.approx(slope, rel=1e-9)
        assert row["Diffusive flux (mmol/m2/d)"] == pytest.approx(flux, rel=1e-9)
        assert row["N points"] == n
    ch4 = results[results["Gas"] == "CH4"]
    assert (ch4["N bubbles"] == 0).all()
    assert (ch4["Total flux (mmol/m2/d)"] == ch4["Diffusive flux (mmol/m2/d)"]).all()


def test_flux_formula_by_hand(cfg):
    # F = dC/dt * P V / (R T A), in mmol m-2 d-1, with the exact gas constant
    slope, volume, area, temp, pres = 2.5e-4, 16.76e-3, 0.126, 30.0, 1014.0
    by_hand = slope * 1e-6 * pres * 100 * volume / (8.314462618 * (temp + 273.15) * area)
    by_hand *= 86400 * 1000
    assert to_flux(cfg, slope) == pytest.approx(by_hand, rel=1e-12)


def test_flux_uses_given_temperature_and_pressure(cfg):
    base = to_flux(cfg, 1e-4)
    other = to_flux(cfg, 1e-4, temp=20, pres=1000)
    assert other / base == pytest.approx((1000 / 1014) * (303.15 / 293.15), rel=1e-9)


def test_bubble_is_separated_from_the_diffusive_flux(cfg):
    step = 0.05
    data = synthetic_data(step=step)
    seconds = window_seconds(data, 0, len(data) - 1)
    bubbles = detect_bubbles(seconds, data.iloc[:, 0].to_numpy())
    assert len(bubbles) == 1

    fit = fit_window(data, 0, len(data) - 1, "CH4")
    assert fit["slope"] == pytest.approx(1e-4, rel=0.03)
    assert fit["jumps"][0] == pytest.approx(step, abs=2e-3)
    assert (~fit["used"]).sum() > 0  # mixing samples excluded

    results = calculate_fluxes(cfg, data, [(0, len(data) - 1)])
    ch4 = results[results["Gas"] == "CH4"].iloc[0]
    duration = seconds[-1]
    assert ch4["N bubbles"] == 1
    assert ch4["Ebullitive flux (mmol/m2/d)"] == pytest.approx(
        to_flux(cfg, fit["jumps"][0] / duration), rel=1e-9
    )
    assert ch4["Total flux (mmol/m2/d)"] == pytest.approx(
        ch4["Diffusive flux (mmol/m2/d)"] + ch4["Ebullitive flux (mmol/m2/d)"]
    )

    table = bubble_table(cfg, data, results)
    assert len(table) == 1
    assert table["Ebullitive flux (mmol/m2/d)"].sum() == pytest.approx(
        ch4["Ebullitive flux (mmol/m2/d)"]
    )
    assert table["Time start"].iloc[0] == data.index[bubbles[0][0]]


def test_no_bubbles_when_disabled(cfg):
    cfg["Bubbles"] = {"enabled": False}
    data = synthetic_data(step=0.05)
    results = calculate_fluxes(cfg, data, [(0, len(data) - 1)])
    assert results.loc[results["Gas"] == "CH4", "N bubbles"].iloc[0] == 0


def test_co2_is_never_split_by_bubbles(cfg):
    data = synthetic_data(step=0.05)
    fit = fit_window(data, 0, len(data) - 1, "CO2")
    assert fit["bubbles"] == []
    assert fit["used"].all()


@pytest.mark.parametrize(
    "rvalue, duration, below, nonlinearity, expected",
    [
        (0.95, 300, False, 0.0, ""),
        (-0.95, 300, False, 0.0, ""),  # negative fluxes (uptake) are fine
        (0.5, 300, False, 0.0, "|r| < 0.9"),
        (0.95, 60, False, 0.0, "shorter than 120 s"),
        (0.5, 60, False, 0.0, "|r| < 0.9; shorter than 120 s"),
        (float("nan"), 300, False, 0.0, "|r| < 0.9"),
        (0.3, 300, True, 0.0, "below detection limit"),  # no r flag below the MDF
        (0.3, 300, True, 0.9, "below detection limit"),  # nor non-linearity
        (0.99, 300, False, 0.35, "nonlinear, saturating (+35%)"),
        (0.99, 300, False, -0.3, "nonlinear, accelerating (-30%)"),
        (0.99, 300, False, 0.15, ""),
    ],
)
def test_quality_flag(rvalue, duration, below, nonlinearity, expected):
    options = {"min_r": 0.9, "min_duration": 120, "max_nonlinearity": 0.2}
    assert quality_flag(rvalue, duration, options, below, nonlinearity) == expected


def test_flags_in_results(cfg, example_data):
    # a 60 s window and a window without trend (end of the example file)
    results = calculate_fluxes(cfg, example_data, [(721, 781), (3000, 3500)])
    flags = results.set_index(["FID", "Gas"])["Flag"]
    assert "shorter than 120 s" in flags[(1, "CH4")]
    assert "|r| < 0.9" in flags[(2, "CO2")]


def test_points_to_windows():
    assert points_to_windows([50, 10, 30, 20]) == [(10, 20), (30, 50)]
    assert points_to_windows([10, 20, 30]) == [(10, 20)]  # unpaired last point dropped
    assert points_to_windows([10, 11, 30, 40]) == [(30, 40)]  # fewer than 3 samples


# --- detection limit and non-linearity ----------------------------------------

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from src.fitting import GAS_COLUMNS, assess_fit, noise, quadratic_slope  # noqa: E402


def series(values, seconds=None):
    """One-window data with the same values for both gases."""
    seconds = np.arange(len(values), dtype=float) if seconds is None else seconds
    index = pd.Timestamp("2025-01-11 12:00") + pd.to_timedelta(seconds, unit="s")
    return pd.DataFrame({GAS_COLUMNS["CH4"]: values, GAS_COLUMNS["CO2"]: values}, index=index)


def test_noise_ignores_trend_and_bubbles():
    rng = np.random.default_rng(3)
    t = np.arange(600.0)
    values = 2 + 1e-3 * t + rng.normal(0, 0.002, t.size)
    values[300:] += 0.5  # a bubble
    assert noise(values) == pytest.approx(0.002, rel=0.1)


def test_minimum_detectable_flux(cfg):
    cfg["Quality"] = {"CO2_precision": 0.5}
    data = synthetic_data()
    fit = fit_window(data, 0, len(data) - 1, "CO2")
    result = assess_fit(cfg, data, 0, len(data) - 1, "CO2", fit)
    duration = window_seconds(data, 0, len(data) - 1)[-1]
    assert result["precision"] == 0.5
    assert result["mdf"] == pytest.approx(to_flux(cfg, 0.5 / duration), rel=1e-12)
    assert not result["below_mdf"]


def test_flat_window_is_below_detection_not_low_r(cfg):
    rng = np.random.default_rng(4)
    data = series(2 + rng.normal(0, 0.001, 300))  # no trend, only noise
    fit = fit_window(data, 0, 299, "CH4", {"enabled": False})
    result = assess_fit(cfg, data, 0, 299, "CH4", fit)
    assert result["below_mdf"]
    assert result["flag"] == "below detection limit"  # the low r is expected


def test_quadratic_recovers_initial_slope(cfg):
    t = np.arange(400.0)
    data = series(2 + 1e-3 * t - 1e-6 * t**2)  # slows down: saturating
    fit = fit_window(data, 0, 399, "CO2")
    assert quadratic_slope(t, data.iloc[:, 1].to_numpy(), fit) == pytest.approx(1e-3, rel=1e-6)
    result = assess_fit(cfg, data, 0, 399, "CO2", fit)
    assert result["nonlinearity"] > 0.2
    assert "nonlinear, saturating" in result["flag"]


def test_example_windows_accelerate(cfg, example_data):
    # flux 1 of the example: the chamber is still settling at the start
    fit = fit_window(example_data, 262, 641, "CH4")
    result = assess_fit(cfg, example_data, 262, 641, "CH4", fit)
    assert result["nonlinearity"] < -0.2
    assert "nonlinear, accelerating" in result["flag"]
    cfg["Quality"] = {"max_nonlinearity": 0.5}  # more tolerant: not flagged
    assert assess_fit(cfg, example_data, 262, 641, "CH4", fit)["flag"] == ""


def test_quadratic_ignores_bubble_jumps(cfg):
    t = np.arange(600.0)
    values = 2 + 1e-4 * t
    values[300:] += 0.05
    data = series(values + np.random.default_rng(5).normal(0, 3e-4, t.size))
    fit = fit_window(data, 0, 599, "CH4")
    assert len(fit["bubbles"]) == 1
    result = assess_fit(cfg, data, 0, 599, "CH4", fit)
    assert abs(result["nonlinearity"]) < 0.1  # a straight line with a step


def test_preselection_waits_until_the_chamber_has_settled(example_data):
    from src.preselect import preselect_windows

    plain = preselect_windows(example_data)
    settled = preselect_windows(example_data, None, max_nonlinearity=0.2)
    assert plain == EXAMPLE_WINDOWS
    # window 2 starts later (settling excluded); 1 and 3 have no better start
    assert settled[0] == plain[0] and settled[2] == plain[2]
    assert settled[1][0] > plain[1][0] and settled[1][1] == plain[1][1]
