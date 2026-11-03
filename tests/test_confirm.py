"""The settings window: values, checks and saving to the YAML file."""

import shutil

import pytest
import yaml
from conftest import ROOT

from src.config import ConfigError
from src.confirm import (
    FIELDS,
    apply_values,
    changed_values,
    confirm_settings,
    current_values,
    parse_values,
    summary,
    update_yaml,
)


def texts_with(cfg, **changes):
    """Entry texts of cfg, with some changed: key=text (keys of FIELDS)."""
    texts = current_values(cfg)
    for (section, key) in texts:
        if key in changes:
            texts[(section, key)] = changes[key]
    return texts


def test_values_round_trip(cfg):
    values = parse_values(current_values(cfg))
    assert values[("Chamber", "Volume")] == 16.76
    assert values[("Air", "Pres")] == 1014
    assert values[("FieldLog", "file")] is None
    assert apply_values(cfg, values, "test.yml")["Chamber"]["Volume"] == 16.76
    assert changed_values(cfg, values) == {}


def test_edits_apply_to_the_run(cfg):
    values = parse_values(texts_with(cfg, Volume="17,5", Temp="25", CH4_precision="0.002"))
    new = apply_values(cfg, values, "test.yml")
    assert new["Chamber"]["Volume"] == 17.5  # decimal comma accepted
    assert new["Air"]["Temp"] == 25
    assert new["Quality"]["CH4_precision"] == 0.002
    assert cfg["Chamber"]["Volume"] == 16.76  # the original is not changed
    assert set(changed_values(cfg, values)) == {
        ("Chamber", "Volume"), ("Air", "Temp"), ("Quality", "CH4_precision")
    }


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"Volume": "big"}, "Chamber volume must be a number"),
        ({"Area": "0"}, "must be > 0"),
        ({"Area": ""}, "Chamber: Area"),
        ({"site": ""}, "'site' is missing"),
        ({"CO2_precision": "-1"}, "Quality: CO2_precision"),
        ({"file": "missing.csv"}, "Field log not found"),
    ],
)
def test_wrong_values_are_reported(cfg, changes, message):
    with pytest.raises(ConfigError, match=message):
        apply_values(cfg, parse_values(texts_with(cfg, **changes)), "test.yml")


def test_save_keeps_comments_and_other_settings(tmp_path):
    path = tmp_path / "config.yml"
    shutil.copy(ROOT / "config.yml", path)
    original = path.read_text()
    update_yaml(path, {
        ("Chamber", "Volume"): 17.5,
        (None, "site"): "Lake B",
        ("Quality", "CH4_precision"): 0.002,
        ("FieldLog", "file"): "log.csv",
    })
    saved = path.read_text()
    cfg = yaml.safe_load(saved)
    assert cfg["Chamber"]["Volume"] == 17.5
    assert cfg["site"] == "Lake B"
    assert cfg["Quality"]["CH4_precision"] == 0.002
    assert cfg["FieldLog"]["file"] == "log.csv"
    assert cfg["Bubbles"] == yaml.safe_load(original)["Bubbles"]  # untouched
    assert "# Volume in Liters" in saved  # comments kept
    assert len(saved.splitlines()) == len(original.splitlines())  # edited in place


def test_save_adds_missing_keys_and_sections(tmp_path):
    path = tmp_path / "config.local.yml"
    path.write_text("site: 'A'\nChamber:\n  Volume: 10 # L\nAir:\n  Temp: 30\n")
    update_yaml(path, {("Chamber", "Area"): 0.1, ("Quality", "CO2_precision"): 0.3})
    cfg = yaml.safe_load(path.read_text())
    assert cfg["Chamber"] == {"Volume": 10, "Area": 0.1}
    assert cfg["Air"] == {"Temp": 30}
    assert cfg["Quality"] == {"CO2_precision": 0.3}


def test_save_empty_value(tmp_path):
    path = tmp_path / "c.yml"
    path.write_text("Quality:\n  CH4_precision: 0.002  # ppm\n")
    update_yaml(path, {("Quality", "CH4_precision"): None})
    assert yaml.safe_load(path.read_text()) == {"Quality": {"CH4_precision": None}}
    assert "# ppm" in path.read_text()


def test_summary_lists_all_fields(cfg):
    text = summary(cfg)
    assert len(text.splitlines()) == len(FIELDS)
    assert "16.76 L" in text and "Field log" in text


def test_without_display_values_are_printed(cfg, monkeypatch, capsys):
    import tkinter

    def no_display(*args, **kwargs):
        raise tkinter.TclError("no display name")

    monkeypatch.setattr(tkinter, "Tk", no_display)
    assert confirm_settings(cfg, "config.yml") is cfg
    assert "Chamber volume" in capsys.readouterr().out
