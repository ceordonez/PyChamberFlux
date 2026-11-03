# PyChamberFlux

Interactive tool to calculate floating chamber fluxes of CH<sub>4</sub> and CO<sub>2</sub> from LGR (Los Gatos Research) analyser files. Both gases are processed from one selection of the chamber deployments, and CH<sub>4</sub> bubbles (ebullition) are separated from the diffusive flux. The slope and flux calculations use [PyGHGaq](https://github.com/ceordonez/PyGHGaq) (`chamber_slope` and `chamber_flux`).

## Installation

The project is managed with [uv](https://docs.astral.sh/uv/). From the repository folder:

```sh
uv sync
```

This creates `.venv` with Python ≥ 3.12 and the versions pinned in `uv.lock`, including `pyghgaq>=0.1.5` (taken from its GitHub repository until 0.1.5 is on PyPI). `uv run` (below) also does this automatically.

## Usage

1. Set up `config.yml` once per site or campaign:
   - `path_out`: folder for the results; `path_in`: folder where the file dialog opens.
   - `site`: used in the output file names.
   - `Air`: air temperature (°C) and pressure (hPa) in the chamber.
   - `Chamber`: volume (L, including tubing and analyser) and area (m²).
   - `Plot`: optional y limits of the CH<sub>4</sub> axis of the selection plot.
   - `Output`: `excel: true` to also save the results as an Excel file (CSV only by default).
   - `Preselect` and `Bubbles`: see below. Remove a line to use its default.
2. Run:

   ```sh
   uv run main.py                        # choose the LGR files in a dialog
   uv run main.py gga_2025-01-21_f0001.txt
   uv run main.py path/to/LGR/2025-01-21  # all .txt files in the folder, one after the other
   uv run main.py -c other_site.yml FILE  # another configuration file
   ```

   Windows users can also double-click `main.py` to get the dialog, if `.venv` is the Python that opens `.py` files (otherwise use `uv run main.py`).

   To try it, run `uv run main.py examples/example.txt`: about one hour of LGR data with three chamber deployments.
3. Check the flux windows on the plot of each file (CH<sub>4</sub> on top, CO<sub>2</sub> below, on the same time axis; clicks work on both). The pre-selected windows are shaded and labelled with their number, the Pearson r of each gas and the CH<sub>4</sub> bubbles found (the excluded part of the CH<sub>4</sub> line is drawn in violet). Points are paired in time order (1st–2nd, 3rd–4th, ...).
   - **Left click**: add a point.
   - **Right click**: remove the nearest point. To move the edge of a window, right-click the edge and then left-click the new position.
   - **`d`** (or Delete) with the mouse over a window: delete that window.
   - **Middle click** or closing the window: finish and go to the next file.
   - Use the zoom and pan tools of the toolbar to look closer; clicks do not add points while one of them is active (click the tool again to switch it off).

   An unpaired last point and windows with fewer than 3 samples are ignored. Files that are not LGR files are skipped.

### Pre-selection

When the chamber is placed or lifted, the concentration changes abruptly. Each deployment is the steady trend between two of these breaks. The pre-selection uses `gas` (CO<sub>2</sub> by default, since CH<sub>4</sub> bubbles would split a deployment) and:

1. finds the breaks: rate of change larger than `jump_threshold` times the noise of the record;
2. skips `dead_time` seconds after each break (chamber settling) and `end_margin` seconds before the next one;
3. moves the start forward, in 10 s steps, to where the fit is (nearly) the best;
4. keeps the windows longer than `min_duration` with |r| ≥ `min_r`.

It only suggests windows: always check them. It can miss deployments with a flux close to zero (low r) and suggest windows when the chamber is not deployed. Set `enabled: false` to select everything by hand.

### CH<sub>4</sub> bubbles

A bubble reaching the chamber is an abrupt increase of CH<sub>4</sub>, after which CH<sub>4</sub> keeps rising with the diffusive slope. In each window:

1. a bubble is a CH<sub>4</sub> increase faster than `threshold` times the noise of the window;
2. the samples from `before` seconds before the bubble to `mixing_time` seconds after it are excluded (bubble mixing in the chamber);
3. the jump of each bubble is estimated from lines fitted to the `jump_window` seconds before and after it;
4. the jumps are removed and one line is fitted to the whole window: its slope gives the **diffusive** flux;
5. the sum of the jumps divided by the duration of the window gives the **ebullitive** flux, and **total** = diffusive + ebullitive.

Check the per-flux figures: the excluded samples are open violet circles and the fitted line is drawn on each part between bubbles. Set `enabled: false` to fit CH<sub>4</sub> as a plain line.

## Results

For each LGR file, a folder `path_out/<site>_<file>/` with:

- **`results.csv`**: one row per flux (chamber deployment), the same for both gases:
  - `File`, `Flux` number, `Time start`, `Time end`, `Duration (s)`;
  - CH<sub>4</sub>: diffusive flux and its standard error, ebullitive and total flux (mmol m⁻² d⁻¹), number of bubbles;
  - CO<sub>2</sub>: flux and its standard error (mmol m⁻² d⁻¹);
  - for each gas: slope (ppm s⁻¹) and its standard error, Pearson r, intercept, first and last value, number of samples used and a `flag` when the flux should be checked (|r| < `min_r` or window shorter than `min_duration`, from `Preselect`; empty when it looks fine);
  - the means of the LGR cell temperature (`GasT_C`), the temperature inside the analyser (`AmbT_C`) and the cell pressure (`GasP_torr`), and the row numbers of the window in the LGR file (`ID start`, `ID end`). The LGR temperatures and pressure are only to check the analyser (e.g. the cell pressure should stay at ~140 torr); they are not the chamber conditions and are not used for the flux.

  The standard errors of the fluxes are those of the slopes, converted to fluxes; they do not include the uncertainty of the chamber volume, area, temperature or pressure.
- **`bubbles.csv`**: one row per CH<sub>4</sub> jump removed from the fit: flux number, time, jump (ppm) and its ebullitive flux. Bubbles too close together to fit a line between them give one jump (`N bubbles merged`).
- **`samples.csv`**: the samples of each flux (`Flux` column): time, seconds since the start of the window, each gas with its fitted line and whether the sample was used in the fit, and the LGR diagnostics.
- **`settings.yml`**: the file, the processing date, the PyChamberFlux and pyghgaq versions, the chamber and air conditions and the `Preselect` and `Bubbles` parameters used (including defaults).
- **`<site>_<file>.xlsx`** (only with `Output: excel: true`): the same tables in one formatted file, one sheet per flux.

All the files processed for a site are collected in `path_out/<site>_fluxes.csv` (the `results.csv` rows) and `path_out/<site>_bubbles.csv`, sorted by time. Processing a file again replaces its rows. To read them in Python:

```python
import pandas as pd
fluxes = pd.read_csv("Gambia_fluxes.csv", parse_dates=["Time start", "Time end"])
```

Figures in `path_out/Figures/Figures_<date>/`: one per flux (CH<sub>4</sub> and CO<sub>2</sub> with the fitted lines) and one with the whole file and the selected windows.

## Method

The slopes are fitted by least squares against the real time of each sample (the LGR logs about every 0.995 s). The flux is

$$F = \frac{dC}{dt}\frac{P V}{R T A}$$

with $dC/dt$ the slope of the dry mole fraction, $P$ and $T$ the pressure and temperature in the chamber (`Air` in `config.yml`), $V$ the chamber volume and $A$ its area.
