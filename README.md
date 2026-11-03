# LGR surface Fluxes

Interactive tool to calculate floating chamber fluxes of CH<sub>4</sub> and CO<sub>2</sub> from LGR (Los Gatos Research) analyser files. The slope and flux calculations use [PyGHGaq](https://github.com/ceordonez/PyGHGaq) (`chamber_slope` and `chamber_flux`).

## Installation

```sh
pip install -r requirements.txt
```

Requires `pyghgaq>=0.1.5`.

## Usage

1. Set up `config.yml`:
   - `path_in`, `date`, `file`: the LGR file is read from `path_in/date/file.txt`.
   - `path_out`: folder for the results.
   - `site`, `variable` (`CH4` or `CO2`).
   - `Air`: air temperature (°C) and pressure (hPa) in the chamber.
   - `Chamber`: volume (L, including tubing and analyser) and area (m²).
   - `Plot`: optional y limits for the selection plot.
   - `Preselect`: settings of the automatic pre-selection (see below).
2. Run `python main.py` (Windows users can also double-click `main.py`).
3. Check the flux windows on the plot. The pre-selected windows are shaded, numbered and labelled with their Pearson r. Points are paired in time order (1st–2nd, 3rd–4th, ...).
   - **Left click**: add a point.
   - **Right click**: remove the nearest point. To move the edge of a window, right-click the edge and then left-click the new position.
   - **`d`** (or Delete) with the mouse over a window: delete that window.
   - **Middle click** or closing the window: finish.

   An unpaired last point and windows with fewer than 3 samples are ignored.

### Pre-selection

When the chamber is placed or lifted, the concentration changes abruptly. Each deployment is the steady trend between two of these breaks. The pre-selection:

1. finds the breaks: rate of change larger than `jump_threshold` times the noise of the record;
2. skips `dead_time` seconds after each break (chamber settling) and `end_margin` seconds before the next one;
3. moves the start forward, in 10 s steps, to where the fit is (nearly) the best;
4. keeps the windows longer than `min_duration` with |r| ≥ `min_r`.

It only suggests windows: always check them. It can miss deployments with a flux close to zero (low r), split a CH<sub>4</sub> deployment at an ebullition event, and suggest windows when the chamber is not deployed. Set `enabled: false` to select everything by hand.

## Results

- `path_out/<variable>_<site>_<file>.xlsx`: one sheet with the raw data of each flux (`FID_n`) and a `Results` sheet with one row per flux: start/end time and value, slope (ppm s⁻¹) and its standard error, Pearson r, flux (mmol m⁻² d⁻¹), temperature, pressure, intercept, number of samples, and the means of the LGR cell temperature (`GasT_C`), the temperature inside the analyser (`AmbT_C`) and the cell pressure (`GasP_torr`). The LGR temperatures and pressure are only to check the analyser (e.g. the cell pressure should stay at ~140 torr); they are not the chamber conditions and are not used for the flux. The `FID_n` sheets include them for each sample.
- `path_out/Figures/Figures_<date>/`: one figure per flux with the fitted line, and one figure with all the data and the selected points.

## Method

The slope is fitted by least squares against the real time of each sample. The LGR logs about every 0.995 s, so fitting against the sample number (as in versions before this change) underestimated the fluxes by about 0.5 %. The flux is

$$F = \frac{dC}{dt}\frac{P V}{R T A}$$

with $dC/dt$ the slope of the dry mole fraction, $P$ and $T$ the pressure and temperature in the chamber (`Air` in `config.yml`), $V$ the chamber volume and $A$ its area.
