"""Reading LGR files, plain or zipped, and finding them in a folder."""

import shutil
import zipfile

import matplotlib.pyplot as plt
import pandas as pd
import pytest
from conftest import EXAMPLE

import main
from src.read_data import footer_pos, read_lgr_file, read_text, source_name


def zip_copy(src, dest):
    """Zip one LGR file the way the analyser archives it (x.txt -> x.txt.zip)."""
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(src, arcname=dest.name.removesuffix(".zip"))
    return dest


def test_zipped_file_reads_like_plain(tmp_path, example_data):
    zipped = zip_copy(EXAMPLE, tmp_path / "example.txt.zip")
    pd.testing.assert_frame_equal(read_lgr_file(str(zipped)), example_data)


def test_zip_without_one_txt_is_refused(tmp_path):
    bad = tmp_path / "x.txt.zip"
    with zipfile.ZipFile(bad, "w") as zf:
        zf.writestr("a.txt", "x")
        zf.writestr("b.txt", "y")
    with pytest.raises(ValueError, match="expected one .txt"):
        read_lgr_file(str(bad))


def test_footer_pos():
    assert footer_pos("h\nh\n1\n2\n-----BEGIN PGP MESSAGE-----\nabc\n-----END\n") == 3
    assert footer_pos("h\nh\n1\n2\n") == 0
    assert footer_pos(read_text(str(EXAMPLE))) == 0  # the example has no signature


def test_source_name():
    assert source_name("d/gga_2025-07-19_f0003.txt.zip") == "gga_2025-07-19_f0003.txt"
    assert source_name("d/gga_2025-07-19_f0003.txt") == "gga_2025-07-19_f0003.txt"


def test_find_files_searches_subfolders_and_prefers_zip(tmp_path):
    day1, day2 = tmp_path / "2025-07-18", tmp_path / "2025-07-19"
    day1.mkdir()
    day2.mkdir()
    zip_copy(EXAMPLE, day1 / "gga_f0000.txt.zip")
    shutil.copy(EXAMPLE, day2 / "gga_f0001.txt")
    shutil.copy(EXAMPLE, day2 / "gga_f0002.txt")  # unzipped copy of the zip next to it
    zip_copy(EXAMPLE, day2 / "gga_f0002.txt.zip")
    (day2 / "notes.csv").write_text("not an LGR file")
    found = [f.relative_to(tmp_path).as_posix() for f in main.find_files([tmp_path])]
    assert found == [
        "2025-07-18/gga_f0000.txt.zip",
        "2025-07-19/gga_f0001.txt",
        "2025-07-19/gga_f0002.txt.zip",
    ]


def test_zipped_and_plain_copies_are_the_same_file(monkeypatch, cfg, tmp_path, capsys):
    """Results of a .txt.zip are recorded under the .txt name, so --new-only
    treats a zipped and an unzipped copy of the same file as one file."""
    zipped_dir, plain_dir = tmp_path / "zipped", tmp_path / "plain"
    zipped_dir.mkdir()
    plain_dir.mkdir()
    zip_copy(EXAMPLE, zipped_dir / "a.txt.zip")
    shutil.copy(EXAMPLE, plain_dir / "a.txt")
    monkeypatch.setattr(main, "read_config", lambda path: cfg)
    monkeypatch.setattr(plt, "show", lambda *a, **k: _press("enter"))

    main.main([str(zipped_dir)])
    assert (tmp_path / "out" / "Test_a" / "results.csv").exists()
    campaign = pd.read_csv(tmp_path / "out" / "Test_fluxes.csv")
    assert set(campaign["File"]) == {"a.txt"}

    main.main(["--new-only", str(plain_dir)])
    assert "Skipping 1 file already in the campaign file" in capsys.readouterr().out


def _press(key):
    from matplotlib.backend_bases import KeyEvent

    fig = plt.gcf()
    fig.canvas.callbacks.process("key_press_event", KeyEvent("key_press_event", fig.canvas, key))
