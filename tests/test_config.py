"""Configuration checks and the field log."""

import pandas as pd
import pytest

from src.config import ConfigError, validate_config
from src.fieldlog import FieldLogError, conditions, load_field_log


def check(cfg):
    return validate_config(cfg, "test.yml")


def test_valid_config(cfg):
    assert check(cfg) is cfg


def test_repository_config_is_valid():
    from conftest import ROOT
    from src.read_data import read_config

    check(read_config(str(ROOT / "config.yml")))


@pytest.mark.parametrize(
    "change, message",
    [
        (lambda c: c["Chamber"].pop("Area"), "'Chamber: Area'"),
        (lambda c: c["Chamber"].update(Volume=-1), "must be > 0"),
        (lambda c: c["Air"].update(Pres="1014"), "'Air: Pres'"),
        (lambda c: c.pop("site"), "'site' is missing"),
        (lambda c: c.update(Preselect={"min_rr": 0.9}), "Unknown setting 'Preselect: min_rr'"),
        (lambda c: c.update(Preselect={"min_r": True}), "must be a number"),
        (lambda c: c.update(Bubbles={"enabled": 1}), "must be true or false"),
        (lambda c: c.update(Preselect={"gas": "N2O"}), "'Preselect: gas'"),
        (lambda c: c.update(Output={"excel": "yes"}), "'Output: excel'"),
        (lambda c: c.update(FieldLog={"file": "missing.csv"}), "Field log not found"),
    ],
)
def test_config_problems_are_reported(cfg, change, message):
    change(cfg)
    with pytest.raises(ConfigError, match=message.replace("(", r"\(")):
        check(cfg)


def test_all_problems_reported_at_once(cfg):
    cfg["Chamber"].pop("Area")
    cfg["Bubbles"] = {"treshold": 10}
    with pytest.raises(ConfigError) as error:
        check(cfg)
    assert "Chamber: Area" in str(error.value) and "Bubbles: treshold" in str(error.value)


def test_unknown_top_level_key_is_only_a_warning(cfg, capsys):
    cfg["date"] = "2025-01-01"  # left over from old configurations
    check(cfg)
    assert "Unknown setting 'date' is ignored" in capsys.readouterr().out


def test_empty_config():
    with pytest.raises(ConfigError, match="empty"):
        check(None)


# --- field log ---------------------------------------------------------------

LOG = """Start,End,Temp,Pres,Location,Notes
2025-01-11 17:30,2025-01-11 17:45,20,1000,Site A,3 chambers
2025-01-11 17:50,,25,,Site B,
2025-01-11 18:30,,,,Site C,no T/P
"""


@pytest.fixture
def logged_cfg(cfg, tmp_path):
    (tmp_path / "log.csv").write_text(LOG)
    cfg["FieldLog"] = {"file": "log.csv"}  # relative to the configuration file
    return validate_config(cfg, str(tmp_path / "config.yml"))


@pytest.mark.parametrize(
    "time, temp, pres, location",
    [
        ("17:20", 30, 1014, ""),  # before the first row: config values
        ("17:35", 20, 1000, "Site A"),  # inside Start-End
        ("17:47", 30, 1014, ""),  # after End of Site A, before Site B
        ("18:10", 25, 1014, "Site B"),  # no End: until the next Start; Pres from config
        ("19:00", 30, 1014, "Site C"),  # row without T/P: config values, location kept
    ],
)
def test_field_log_matching(logged_cfg, time, temp, pres, location):
    result = conditions(logged_cfg, pd.Timestamp(f"2025-01-11 {time}"))
    assert (result["Temp"], result["Pres"], result["Location"]) == (temp, pres, location)


def test_without_field_log_only_air(cfg):
    assert conditions(cfg, pd.Timestamp("2025-01-11")) == {"Temp": 30, "Pres": 1014}


def test_field_log_columns_in_results(logged_cfg, example_data):
    from conftest import EXAMPLE_WINDOWS
    from src.processing_data import calculate_fluxes
    from src.write import results_table

    results = calculate_fluxes(logged_cfg, example_data, EXAMPLE_WINDOWS)
    table = results_table(results, "example.txt")
    assert list(table.columns[:4]) == ["File", "Flux", "Location", "Notes"]
    assert table["Location"].tolist() == ["Site A", "Site A", ""]  # flux 3 at 17:47
    assert table["Air temp (degC)"].tolist() == [20, 20, 30]


@pytest.mark.parametrize(
    "content, message",
    [
        ("Time,Temp\n2025-01-11 17:30,20\n", "needs a 'Start' column"),
        ("Start,Temp\n11/01/2025 17:30,20\n", "line 2 has '11/01/2025 17:30'"),
        ("Start,Temp\n2025-01-11 17:30,warm\n", "'Temp' .* must be numbers"),
        ("Start,End\n2025-01-11 17:30,2025-01-11 17:00\n", "End is not after Start"),
    ],
)
def test_field_log_errors(tmp_path, content, message):
    path = tmp_path / "log.csv"
    path.write_text(content)
    with pytest.raises(FieldLogError, match=message):
        load_field_log(path)
