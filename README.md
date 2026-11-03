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
2. Run `python main.py` (Windows users can also double-click `main.py`).
3. Select the fluxes on the plot:
   - **Left click**: add a point. Points are taken in pairs: start, end, start, end, ...
   - **Right click**: remove the last point.
   - **Middle click** or closing the window: finish.

   An unpaired last point and windows with fewer than 3 samples are ignored.

## Results

- `path_out/<variable>_<site>_<file>.xlsx`: one sheet with the raw data of each flux (`FID_n`) and a `Results` sheet with one row per flux: start/end time and value, slope (ppm s⁻¹) and its standard error, Pearson r, flux (mmol m⁻² d⁻¹), temperature, pressure, intercept and number of samples.
- `path_out/Figures/Figures_<date>/`: one figure per flux with the fitted line, and one figure with all the data and the selected points.

## Method

The slope is fitted by least squares against the real time of each sample. The LGR logs about every 0.995 s, so fitting against the sample number (as in versions before this change) underestimated the fluxes by about 0.5 %. The flux is

$$F = \frac{dC}{dt}\frac{P V}{R T A}$$

with $dC/dt$ the slope of the dry mole fraction, $P$ and $T$ the pressure and temperature in the chamber, $V$ the chamber volume and $A$ its area.
