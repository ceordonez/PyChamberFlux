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
    "rvalue, duration, expected",
    [
        (0.95, 300, ""),
        (-0.95, 300, ""),  # negative fluxes (uptake) are fine
        (0.5, 300, "|r| < 0.9"),
        (0.95, 60, "shorter than 120 s"),
        (0.5, 60, "|r| < 0.9; shorter than 120 s"),
        (float("nan"), 300, "|r| < 0.9"),
    ],
)
def test_quality_flag(rvalue, duration, expected):
    assert quality_flag(rvalue, duration, {"min_r": 0.9, "min_duration": 120}) == expected


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
