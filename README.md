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
   - `Preselect` and `Bubbles`: see below. Remove a line to use its default.
2. Run:

   ```sh
   uv run main.py                        # choose the LGR files in a dialog
   uv run main.py gga_2025-01-21_f0001.txt
   uv run main.py path/to/LGR/2025-01-21  # all .txt files in the folder, one after the other
   uv run main.py -c other_site.yml FILE  # another configuration file
   ```

   Windows users can also double-click `main.py` to get the dialog, if `.venv` is the Python that opens `.py` files (otherwise use `uv run main.py`).
3. Check the flux windows on the plot of each file (CH<sub>4</sub> on the left axis, CO<sub>2</sub> on the right). The pre-selected windows are shaded and labelled with their number, the Pearson r of each gas and the CH<sub>4</sub> bubbles found (marked in orange). Points are paired in time order (1st–2nd, 3rd–4th, ...).
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

Check the per-flux figures: the excluded samples are orange and the fitted line is drawn on each part between bubbles. Set `enabled: false` to fit CH<sub>4</sub> as a plain line.

## Results

For each LGR file:

- `path_out/<site>_<file>.xlsx`:
  - `Results`: one row per flux and gas (`FID`, `Gas`): start/end time and value, slope (ppm s⁻¹) and its standard error, Pearson r, diffusive flux (mmol m⁻² d⁻¹), for CH<sub>4</sub> the number of bubbles and the total and ebullitive fluxes, temperature, pressure, intercept, number of samples used, and the means of the LGR cell temperature (`GasT_C`), the temperature inside the analyser (`AmbT_C`) and the cell pressure (`GasP_torr`). The LGR temperatures and pressure are only to check the analyser (e.g. the cell pressure should stay at ~140 torr); they are not the chamber conditions and are not used for the flux.
  - `FID_n`: the samples of each flux (both gases and the LGR diagnostics) and whether each CH<sub>4</sub> sample was used in the fit.
- `path_out/Figures/Figures_<date>/`: one figure per flux (CH<sub>4</sub> and CO<sub>2</sub> with the fitted lines) and one figure with the whole file and the selected windows.

## Method

The slopes are fitted by least squares against the real time of each sample (the LGR logs about every 0.995 s). The flux is

$$F = \frac{dC}{dt}\frac{P V}{R T A}$$

with $dC/dt$ the slope of the dry mole fraction, $P$ and $T$ the pressure and temperature in the chamber (`Air` in `config.yml`), $V$ the chamber volume and $A$ its area.
