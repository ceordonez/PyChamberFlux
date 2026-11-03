#!/usr/bin/env python3
"""
Run SurfFlux slope estimation workflow.

This script provides a command-line interface to process time series data
and estimate slopes in user-defined regions (via config.yml).
"""

import sys
from pathlib import Path
import pandas as pd
import plotly.graph_objects as go

# Allow running the script directly without installing the package
repo_root = Path(__file__).resolve().parents[1]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from lgr_surfflux.config import load_config, ConfigError
from lgr_surfflux.io import read_timeseries, save_results
from lgr_surfflux.slope import estimate_slope


def plot_region(df, start, end, time_col, value_col, slope_result, outdir):
    """Create and save a plot for one fitted region."""
    subset = df[(df[time_col] >= start) & (df[time_col] <= end)]
    if len(subset) == 0:
        return

    # Compute fitted line
    x = (subset[time_col] - subset[time_col].iloc[0]).dt.total_seconds()
    fitted = slope_result["intercept"] + slope_result["slope"] * x

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=subset[time_col],
        y=subset[value_col],
        mode="lines+markers",
        name="Observed"
    ))
    fig.add_trace(go.Scatter(
        x=subset[time_col],
        y=fitted,
        mode="lines",
        name=f"Fit (slope={slope_result['slope']:.3g})"
    ))
    fig.update_layout(
        title=f"Slope from {start} to {end}",
        xaxis_title=time_col,
        yaxis_title=value_col
    )

    # Save to HTML
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    outfile = outdir / f"slope_{start.strftime('%Y%m%d_%H%M')}_{end.strftime('%Y%m%d_%H%M')}.html"
    fig.write_html(outfile)
    print(f"Saved plot: {outfile}")


def main(config_path="config.yml"):
    """Main entry point for running slope estimation."""
    try:
        cfg = load_config(config_path)
    except ConfigError as e:
        print(f"❌ Config error: {e}")
        sys.exit(1)

    # --- Load data ---
    data_cfg = cfg["data"]
    df = read_timeseries(
        data_cfg["path"],
        time_col=data_cfg["time_col"],
        value_col=data_cfg["value_col"],
    )
    print(f"✅ Loaded data: {len(df)} rows from {data_cfg['path']}")

    # --- Process regions ---
    results = []
    for region in cfg["regions"]:
        start, end = pd.to_datetime(region["start"]), pd.to_datetime(region["end"])
        try:
            res = estimate_slope(df, start, end,
                                 time_col=data_cfg["time_col"],
                                 value_col=data_cfg["value_col"])
            results.append(res)
            plot_region(df, start, end, data_cfg["time_col"], data_cfg["value_col"],
                        res, cfg["output"]["plots_dir"])
            print(f"📈 Estimated slope from {start} to {end}: {res['slope']:.4g}")
        except Exception as e:
            print(f"⚠️  Failed to estimate slope for {start}–{end}: {e}")

    if not results:
        print("No valid regions processed. Exiting.")
        sys.exit(1)

    # --- Save results ---
    results_df = pd.DataFrame(results)
    save_results(results_df,
                 out_csv=cfg["output"]["csv"],
                 out_excel=cfg["output"]["excel"])
    print("✅ All done! Results saved.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Estimate slopes from time series regions defined in a config.yml file."
    )
    parser.add_argument(
        "-c", "--config",
        default="config.yml",
        help="Path to configuration YAML file (default: config.yml)"
    )
    args = parser.parse_args()

    main(args.config)

