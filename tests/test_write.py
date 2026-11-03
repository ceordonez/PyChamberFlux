"""Result files, campaign files and re-opening saved windows."""

from pathlib import Path

import pandas as pd
import pytest
from conftest import EXAMPLE_WINDOWS, synthetic_data

from src.processing_data import calculate_fluxes
from src.write import processed_files, saved_windows, summary, write_results


def write(cfg, data, windows, name="example", source="example.txt"):
    results = calculate_fluxes(cfg, data, windows)
    write_results(data, results, cfg, name, source=source)
    return Path(cfg["path_out"])


def test_result_files(cfg, example_data):
    out = write(cfg, example_data, EXAMPLE_WINDOWS)
    folder = out / "Test_example"
    assert sorted(p.name for p in folder.iterdir()) == [
        "bubbles.csv", "results.csv", "samples.csv", "settings.yml"
    ]
    results = pd.read_csv(folder / "results.csv", parse_dates=["Time start"])
    assert len(results) == 3  # one row per flux, both gases in it
    assert results["CO2 flux (mmol/m2/d)"].iloc[0] == pytest.approx(57.11912105888556)
    assert results["File"].unique().tolist() == ["example.txt"]
    for gas in ("CH4", "CO2"):
        for column in ("MDF (mmol/m2/d)", "quadratic flux (mmol/m2/d)", "nonlinearity",
                       "precision (ppm)", "flag"):
            assert f"{gas} {column}" in results.columns

    samples = pd.read_csv(folder / "samples.csv")
    assert samples.groupby("Flux").size().tolist() == [380, 413, 821]
    assert {"CH4 fit (ppm)", "CO2 fit (ppm)", "CH4 used in fit"} <= set(samples.columns)

    settings = (folder / "settings.yml").read_text()
    assert "pyghgaq" in settings and "Volume: 16.76" in settings
    assert (out / "Test_fluxes.csv").exists() and (out / "Test_bubbles.csv").exists()


def test_excel_is_optional(cfg, example_data):
    out = write(cfg, example_data, EXAMPLE_WINDOWS)
    assert not list(out.rglob("*.xlsx"))
    cfg["Output"] = {"excel": True}
    write(cfg, example_data, EXAMPLE_WINDOWS)
    assert (out / "Test_example" / "Test_example.xlsx").exists()


def test_campaign_rows_are_replaced_not_duplicated(cfg, example_data):
    out = write(cfg, example_data, EXAMPLE_WINDOWS)
    write(cfg, example_data, EXAMPLE_WINDOWS[:2])  # same file again, one window less
    other = example_data.shift(freq="1D")
    write(cfg, other, EXAMPLE_WINDOWS, name="other", source="other.txt")
    campaign = pd.read_csv(out / "Test_fluxes.csv", parse_dates=["Time start"])
    assert campaign.groupby("File").size().to_dict() == {"example.txt": 2, "other.txt": 3}
    assert campaign["Time start"].is_monotonic_increasing
    assert processed_files(cfg) == {"example.txt", "other.txt"}


def test_campaign_bubbles_removed_when_file_has_none_anymore(cfg):
    data = synthetic_data(step=0.05)
    out = write(cfg, data, [(0, len(data) - 1)], name="a", source="a.txt")
    assert len(pd.read_csv(out / "Test_bubbles.csv")) == 1
    write(cfg, data, [(0, 250)], name="a", source="a.txt")  # window before the bubble
    assert len(pd.read_csv(out / "Test_bubbles.csv")) == 0


def test_saved_windows(cfg, example_data, capsys):
    assert saved_windows(cfg, "example", example_data) is None  # never processed
    write(cfg, example_data, EXAMPLE_WINDOWS)
    assert saved_windows(cfg, "example", example_data) == EXAMPLE_WINDOWS
    # another file with the same name: the saved windows do not match
    assert saved_windows(cfg, "example", example_data.shift(freq="1D")) is None
    assert saved_windows(cfg, "example", example_data.iloc[:1000]) is None
    assert "do not match" in capsys.readouterr().out


def test_summary(cfg, example_data):
    from src.write import results_table

    results = calculate_fluxes(cfg, example_data, EXAMPLE_WINDOWS + [(3000, 3500)])
    text = summary(results_table(results, "example.txt"))
    assert "CH4 diff" in text and "57.1" in text
    assert "|r| < 0.9" in text.splitlines()[-1]  # the flat window is flagged
