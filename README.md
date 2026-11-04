# PyChamberFlux

[![tests](https://github.com/ceordonez/PyChamberFlux/actions/workflows/tests.yml/badge.svg)](https://github.com/ceordonez/PyChamberFlux/actions/workflows/tests.yml) [![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Interactive tool to calculate floating chamber fluxes of CH<sub>4</sub> and CO<sub>2</sub> from LGR (Los Gatos Research) analyser files. Both gases are processed from one selection of the chamber deployments, and CH<sub>4</sub> bubbles (ebullition) are separated from the diffusive flux. The slope and flux calculations use [PyGHGaq](https://github.com/ceordonez/PyGHGaq) (`chamber_slope` and `chamber_flux`).

## Quick start

1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and get the code:

   ```sh
   git clone https://github.com/ceordonez/PyChamberFlux.git
   cd PyChamberFlux
   ```

2. Copy `config.yml` to `config.local.yml` (your own settings, not tracked by git) and set at least `path_out` (where the results go; `./results` by default), `site`, and the `Air` and `Chamber` values of your chamber.
3. Try it with the example file (the first run installs the dependencies):

   ```sh
   uv run main.py examples/example.txt
   ```

4. On the plot, check the shaded flux windows (red labels need a look), adjust them with the mouse (left click: add a point, drag a point to move it, right click: remove, `d`: delete a window, `u`: undo) and press **Enter** to save.
5. The results are in `path_out`: `<site>_example/results.csv` with one row per flux, and `<site>_fluxes.csv` collecting all the files of the site.

Then run it on your own data: `uv run main.py path/to/LGR/folder` processes every `.txt` file in the folder, one after the other (`s` skips a file, `q` stops). See [Usage](#usage) for details.

## Installation

The project is managed with [uv](https://docs.astral.sh/uv/). From the repository folder:

```sh
uv sync
```

This creates `.venv` with Python ≥ 3.12 and the versions pinned in `uv.lock`, including `pyghgaq>=0.1.5` (taken from its GitHub repository until 0.1.5 is on PyPI). `uv run` (below) also does this automatically.

## Usage

1. Set up the configuration once per site or campaign, in `config.local.yml` (a copy of `config.yml`; used automatically when it exists and not tracked by git, so `git pull` never overwrites it):
   - `path_out`: folder for the results; `path_in`: folder where the file dialog opens.
   - `site`: used in the output file names.
   - `Air`: air temperature (°C) and pressure (hPa) in the chamber, used for all fluxes unless a field log gives them.
   - `Chamber`: volume (L, including tubing and analyser) and area (m²).
   - `Plot`: optional y limits of the CH<sub>4</sub> axis of the selection plot.
   - `Output`: `excel: true` to also save the results as an Excel file (CSV only by default); `units` to add the fluxes in `umol m-2 s-1`, `mg m-2 d-1` or `mg C m-2 d-1` next to mmol m⁻² d⁻¹.
   - `FieldLog`: optional CSV with the air temperature/pressure and notes (e.g. location) of each location or deployment, see [Field log](#field-log).
   - `Quality`: limits of the quality checks, see [Quality checks](#quality-checks).
   - `Preselect` and `Bubbles`: see below. Remove a line to use its default.

   The configuration is checked before processing: missing or wrong values and misspelled settings are listed with what to fix.
2. Run:

   ```sh
   uv run main.py                        # choose the LGR files in a dialog
   uv run main.py gga_2025-01-21_f0001.txt
   uv run main.py path/to/LGR/2025-01-21  # all .txt files in the folder, one after the other
   uv run main.py -c other_site.yml FILE  # another configuration file
   uv run main.py -n path/to/LGR          # only the files not in <site>_fluxes.csv yet
   uv run main.py --batch path/to/LGR     # recalculate processed files with their saved windows
   uv run main.py --no-confirm FILE       # without the settings window
   ```

   A window first shows the settings that change between campaigns (site, output folder, chamber volume and area, air temperature and pressure, field log, analyser precision), so that you check them before processing. Edit a value to use it for this run (on Linux, *Browse…* opens the system file dialog through `zenity` when it is installed, so you can also create a new folder there); tick *Save changes* to also write it to the configuration file (its comments and other settings are kept). Enter starts, Escape cancels. Without a display (e.g. on a server) the values are printed instead; `--no-confirm` skips the window.

   Windows users can also double-click `main.py` to get the dialog, if `.venv` is the Python that opens `.py` files (otherwise use `uv run main.py`).

   To try it, run `uv run main.py examples/example.txt`: about one hour of LGR data with three chamber deployments.
3. Check the flux windows on the plot of each file (CH<sub>4</sub> on top, CO<sub>2</sub> below, on the same time axis; clicks work on both). The pre-selected windows are shaded and labelled with their number, the diffusive flux (mmol m⁻² d⁻¹) and Pearson r of each gas and the CH<sub>4</sub> bubbles found (the excluded part of the CH<sub>4</sub> line is drawn in violet). A label is red when the flux would be flagged in the results (see [Quality checks](#quality-checks)). The title shows the progress (e.g. `3 of 12`). Points are paired in time order (1st–2nd, 3rd–4th, ...).
   - **Left click**: add a point. Click on a point and drag it to move a window edge.
   - **Right click**: remove the nearest point.
   - **`d`** (or Delete) with the mouse over a window: delete that window.
   - **`u`** (or Ctrl+Z): undo the last change.
   - **Enter**, middle click or closing the window: save and go to the next file.
   - **`s`**: skip this file (nothing saved).
   - **`q`**: stop: this file is not saved and the remaining files are not processed.
   - Use the zoom and pan tools of the toolbar to look closer; clicks do not add points while one of them is active (click the tool again to switch it off).

   An unpaired last point and windows with fewer than 3 samples are ignored. Files that are not LGR files are skipped.

   A file processed before opens with the windows saved in its `results.csv` instead of the pre-selection, so you only change what needs fixing.

   After saving, a summary of the fluxes of the file (and the ones to check) is printed in the terminal.

   After changing the configuration (e.g. chamber volume, field log, quality limits or units) or updating PyChamberFlux, `--batch` recalculates all the files processed before with their saved windows, without opening the plot: the result files, figures and campaign files are updated. Files not processed before are skipped.

### Field log

Optional. When the air temperature and pressure change during a file (e.g. several locations in one LGR file), give them in a CSV file with one row per location (or per deployment) and set `FieldLog: file` in the configuration (a relative path is relative to the configuration file):

```csv
Start,End,Temp,Pres,Location,Notes
2025-01-11 17:30,2025-01-11 17:50,31.5,1013,Site A,3 chambers
2025-01-11 17:55,,29.8,1014,Site B,
```

- `Start` (required): when the row starts to apply, as `YYYY-MM-DD HH:MM[:SS]`, in the clock of the LGR analyser.
- `End` (optional): when it stops applying. Without `End`, a row applies until the `Start` of the next row, and at most until the end of its day (so a file from another day never takes the last row of the day before).
- `Temp` (°C) and `Pres` (hPa) (optional): empty values (or no column) use `Air` of the configuration.
- Any other column (`Location`, `Chamber`, `Notes`, ...) is copied to the results, after `Flux`.
- Empty rows, and columns without a name and without values (e.g. trailing commas left by Excel), are ignored.

A template for the example file is in [`examples/fieldlog.csv`](examples/fieldlog.csv): copy it, keep the column names (`Start`, `End`, `Temp`, `Pres`) and replace the rows and the extra columns with your own.

If the clock of the analyser differs from the field log (e.g. UTC vs local time), set `FieldLog: time_offset` (s) so that field-log time + `time_offset` = LGR time; a warning is printed when no flux of a file matches a row.

Each flux uses the row that applies at the start of its window; fluxes without a row use `Air` and empty extra columns. The temperature and pressure used are in the results (`Air temp (degC)`, `Air pres (hPa)`), and the labels of the selection plot use them too.

### Quality checks

Each flux of each gas gets a `flag` listing the reasons to check it (empty when it looks fine):

- **`below detection limit`**: |flux| is smaller than the minimum detectable flux, MDF = (A / t<sub>c</sub>) · P V / (R T A<sub>c</sub>) (Christiansen et al., 2015), with A the precision of the analyser, t<sub>c</sub> the duration of the window and A<sub>c</sub> the chamber area. A is `Quality: CH4_precision` / `CO2_precision` (ppm) or, if empty, the sample-to-sample noise of the window. A flux below the MDF is not distinguishable from zero; its low r is expected and not flagged.
- **`|r| < min_r`**: poor linear fit (`Preselect: min_r`).
- **`shorter than min_duration s`** (`Preselect: min_duration`).
- **`nonlinear, saturating`** / **`nonlinear, accelerating`**: a quadratic fit (Wagner et al., 1997) gives an initial slope more than `Quality: max_nonlinearity` (20 %) steeper or flatter than the linear slope. *Saturating*: the concentration levels off (e.g. long deployments), and the linear fit underestimates the flux at closure. *Accelerating*: the concentration rises faster later, often because the chamber was still settling at the start of the window; moving the start later usually fixes it. The quadratic fit is only a check: the reported flux is always the linear one (quadratic fits are unreliable for long floating-chamber deployments, Xiao et al., 2016), and the quadratic flux is in the results for comparison.

The per-flux figures show the quadratic fit (dashed), the MDF and the flags.

### Pre-selection

When the chamber is placed or lifted, the concentration changes abruptly. Each deployment is the steady trend between two of these breaks. The pre-selection uses `gas` (CO<sub>2</sub> by default, since CH<sub>4</sub> bubbles would split a deployment) and:

1. finds the breaks: rate of change larger than `jump_threshold` times the noise of the record;
2. skips `dead_time` seconds after each break (chamber settling) and `end_margin` seconds before the next one;
3. moves the start forward, in 10 s steps, to the earliest start where the fit is good and the concentration change is linear for both gases (quadratic and linear initial slopes within `Quality: max_nonlinearity`; CH<sub>4</sub> only without bubbles), i.e. once the chamber has settled; if there is none, to where the fit is (nearly) the best;
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
  - `File`, `Flux` number, the extra columns of the field log (if any), `Time start`, `Time end`, `Duration (s)`, and the air temperature and pressure used for the flux;
  - CH<sub>4</sub>: diffusive flux and its standard error, ebullitive and total flux (mmol m⁻² d⁻¹), number of bubbles;
  - CO<sub>2</sub>: flux and its standard error (mmol m⁻² d⁻¹);
  - for each gas: slope (ppm s⁻¹) and its standard error, Pearson r, intercept, first and last value, number of samples used, the precision used (ppm), the minimum detectable flux (`MDF`), the flux from the quadratic fit and the `nonlinearity` (quadratic / linear initial slope − 1), and the `flag` (see [Quality checks](#quality-checks));
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

### References

- Christiansen, J. R. et al. (2015). Comparison of CO2, CH4 and N2O soil-atmosphere exchange measured in static chambers with cavity ring-down spectroscopy and gas chromatography. *Agricultural and Forest Meteorology*. https://doi.org/10.1016/j.agrformet.2015.06.004
- Wagner, S. W. et al. (1997). Regression models for calculating gas fluxes measured with a closed chamber. *Agronomy Journal*. https://doi.org/10.2134/agronj1997.00021962008900020021x
- Xiao, S.-B. et al. (2016). Theoretical model for diffusive greenhouse gas fluxes estimation across water-air interfaces measured with the static floating chamber method. *Atmospheric Environment*. https://doi.org/10.1016/j.atmosenv.2016.04.036

## Tests

```sh
uv run pytest       # tests
uv run ruff check   # lint
```

The tests check the fluxes of the example file against reference values, the bubble separation on synthetic data, the configuration and field log checks, the result files, and the selection window (with simulated clicks and keys). They run on GitHub for every push.

## Citation

If you use PyChamberFlux, please cite the version you used (see [CITATION.cff](CITATION.cff), or "Cite this repository" on GitHub). Changes between versions are in [CHANGELOG.md](CHANGELOG.md).

## License

[MIT](LICENSE)
