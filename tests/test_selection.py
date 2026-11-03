"""The selection window, driven by simulated mouse and key events."""

import matplotlib.pyplot as plt
import pytest
from matplotlib.backend_bases import KeyEvent, MouseButton, MouseEvent
from matplotlib.dates import date2num

import main
from conftest import EXAMPLE_WINDOWS
from src.plots import plot_select_points


class Session:
    """Replaces plt.show: runs scripted actions on the open figure."""

    def __init__(self, data, actions):
        self.data = data
        self.actions = actions

    def show(self, *args, **kwargs):
        fig = plt.gcf()
        fig.canvas.draw()  # so that the transforms are set
        self.fig = fig
        self.ax = fig.axes[0]
        for action in self.actions:
            action(self)
        if plt.fignum_exists(fig.number):
            self.key("enter")

    def pixel(self, sample, ax=None):
        ax = ax or self.ax
        x = date2num(self.data.index[sample])
        y = sum(ax.get_ylim()) / 2
        return ax.transData.transform((x, y))

    def mouse(self, name, sample, button=MouseButton.LEFT, dx=0):
        x, y = self.pixel(sample)
        event = MouseEvent(name, self.fig.canvas, x + dx, y, button=button)
        self.fig.canvas.callbacks.process(name, event)

    def click(self, sample, button=MouseButton.LEFT, dx=0):
        self.mouse("button_press_event", sample, button, dx)
        self.mouse("button_release_event", sample, button, dx)

    def drag(self, start, end):
        self.mouse("button_press_event", start)
        self.mouse("motion_notify_event", (start + end) // 2)
        self.mouse("motion_notify_event", end)
        self.mouse("button_release_event", end)

    def key(self, key, sample=None):
        x, y = self.pixel(sample) if sample is not None else (None, None)
        event = KeyEvent("key_press_event", self.fig.canvas, key, x, y)
        self.fig.canvas.callbacks.process("key_press_event", event)


def select(monkeypatch, cfg, data, preselected, *actions):
    session = Session(data, actions)
    monkeypatch.setattr(plt, "show", lambda *args, **kwargs: session.show())
    return plot_select_points(data, cfg, preselected, title="test")


@pytest.mark.parametrize("key, action", [("enter", "save"), ("s", "skip"), ("q", "quit")])
def test_finish_keys(monkeypatch, cfg, example_data, key, action):
    windows, result = select(monkeypatch, cfg, example_data, EXAMPLE_WINDOWS,
                             lambda s: s.key(key))
    assert result == action
    assert windows == EXAMPLE_WINDOWS


def test_add_and_remove_points(monkeypatch, cfg, example_data):
    windows, _ = select(
        monkeypatch, cfg, example_data, EXAMPLE_WINDOWS,
        lambda s: s.click(3000), lambda s: s.click(3400),  # new window
        lambda s: s.click(262, MouseButton.RIGHT),  # remove the start of window 1
    )
    # points are paired in time order: without 262 they pair up differently,
    # and the last point (3400) is left unpaired and dropped
    assert windows == [(641, 721), (1133, 1210), (2030, 3000)]


def test_delete_window_and_undo(monkeypatch, cfg, example_data):
    windows, _ = select(monkeypatch, cfg, example_data, EXAMPLE_WINDOWS,
                        lambda s: s.key("d", 900))
    assert windows == [EXAMPLE_WINDOWS[0], EXAMPLE_WINDOWS[2]]

    windows, _ = select(monkeypatch, cfg, example_data, EXAMPLE_WINDOWS,
                        lambda s: s.key("d", 900), lambda s: s.key("u"))
    assert windows == EXAMPLE_WINDOWS

    windows, _ = select(
        monkeypatch, cfg, example_data, EXAMPLE_WINDOWS,
        lambda s: s.key("d", 900), lambda s: s.key("d", 300),
        lambda s: s.key("ctrl+z"), lambda s: s.key("u"), lambda s: s.key("u"),  # extra undo: no-op
    )
    assert windows == EXAMPLE_WINDOWS


def test_drag_an_edge(monkeypatch, cfg, example_data):
    windows, _ = select(monkeypatch, cfg, example_data, EXAMPLE_WINDOWS,
                        lambda s: s.drag(262, 300))
    assert windows[0] == (300, 641)
    assert windows[1:] == EXAMPLE_WINDOWS[1:]

    # undo puts it back
    windows, _ = select(monkeypatch, cfg, example_data, EXAMPLE_WINDOWS,
                        lambda s: s.drag(262, 300), lambda s: s.key("u"))
    assert windows == EXAMPLE_WINDOWS


def test_click_on_a_point_without_moving_changes_nothing(monkeypatch, cfg, example_data):
    windows, _ = select(monkeypatch, cfg, example_data, EXAMPLE_WINDOWS,
                        lambda s: s.click(262, dx=3), lambda s: s.key("u"))
    assert windows == EXAMPLE_WINDOWS  # no new point, and nothing to undo


# --- whole program -------------------------------------------------------------


def test_main_new_only_and_quit(monkeypatch, cfg, tmp_path, example_data, capsys):
    import shutil

    from conftest import EXAMPLE

    lgr = tmp_path / "lgr"
    lgr.mkdir()
    for name in ("a.txt", "b.txt", "c.txt"):
        shutil.copy(EXAMPLE, lgr / name)
    monkeypatch.setattr(main, "read_config", lambda path: cfg)

    keys = iter(["enter", "q"])
    monkeypatch.setattr(plt, "show", lambda *a, **k: _press(next(keys)))
    main.main([str(lgr)])
    out = capsys.readouterr().out
    assert "Fluxes (mmol m-2 d-1)" in out  # summary of a.txt
    assert "Stopped, this file was not saved." in out and "1 file not processed." in out

    keys = iter(["enter", "enter"])
    main.main(["--new-only", str(lgr)])
    out = capsys.readouterr().out
    assert "Skipping 1 file already in the campaign file" in out
    assert "a.txt" not in out.split("Skipping")[1]
    campaign = (tmp_path / "out" / "Test_fluxes.csv").read_text()
    assert "a.txt" in campaign and "b.txt" in campaign and "c.txt" in campaign


def _press(key):
    fig = plt.gcf()
    fig.canvas.callbacks.process("key_press_event", KeyEvent("key_press_event", fig.canvas, key))


def test_main_reports_config_errors(monkeypatch, cfg):
    cfg["Chamber"].pop("Area")
    monkeypatch.setattr(main, "read_config", lambda path: cfg)
    with pytest.raises(SystemExit) as error:
        main.main(["whatever.txt"])
    assert "Chamber: Area" in str(error.value)
