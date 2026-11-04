# Changelog

All notable changes to PyChamberFlux. Versions follow [semantic versioning](https://semver.org/).

## [Unreleased]

### Added

- Window to check (and edit) the settings that change between campaigns before processing; changes apply to the run and are saved to the configuration file only on request, keeping its comments. `--no-confirm` skips it.
- On Linux, *Browse…* in the settings window uses the system file dialog (zenity, if installed), which can create folders; it opens at the folder already entered.
- Template field log for the example file: `examples/fieldlog.csv`.

### Changed

- `--batch`: the message for a skipped file says in which folder the saved windows were looked for.
- Field log: a warning when the `Temp` or `Pres` column is missing (with a hint for similar names such as `Press`), since the values of the configuration are then used.
- pyghgaq is installed from PyPI (0.1.5) instead of its GitHub repository.
- Field log: empty rows and unnamed empty columns (e.g. trailing commas from a spreadsheet) are ignored instead of being copied to the results.

## [0.2.0] - 2026-11-03

First release as PyChamberFlux (formerly LGR_SurfFlux).

### Method

- Slopes are fitted against the real time of each sample and converted to fluxes with [pyghgaq](https://github.com/ceordonez/PyGHGaq) (`chamber_slope`, `chamber_flux`), with the exact gas constant R = 8.314462618 J mol⁻¹ K⁻¹.
- CH<sub>4</sub> and CO<sub>2</sub> are processed together from one selection of the chamber deployments.
- CH<sub>4</sub> bubbles are detected and their jumps removed: diffusive, ebullitive and total CH<sub>4</sub> fluxes.
- Automatic pre-selection of the deployments, with window starts moved until the chamber has settled (linear concentration change).
- Quality checks for each flux: minimum detectable flux (Christiansen et al., 2015), Pearson r, window duration and non-linearity (quadratic fit, Wagner et al., 1997).
- Optional field log with the air temperature and pressure (and notes, e.g. location) of each location or deployment, with a clock offset.

### Selection window

- CH<sub>4</sub> and CO<sub>2</sub> in two panels; window labels with the flux, r, bubbles and quality flags.
- Add, remove and drag window edges, delete windows, undo; Enter saves, `s` skips a file, `q` stops.
- Files processed before open with their saved windows.

### Results

- CSV files per LGR file (results, bubbles, samples, settings) and per campaign (`<site>_fluxes.csv`, `<site>_bubbles.csv`); optional Excel file; optional extra flux units.
- `--new-only` to process only new files and `--batch` to recalculate all processed files without the selection window.

### Project

- Managed with uv; configuration checked before processing; personal settings in `config.local.yml`.
- Tests (pytest) and linting (ruff) on GitHub Actions; MIT licence.
