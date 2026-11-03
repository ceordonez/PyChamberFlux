#!/usr/bin/env python3
"""
Interactive SurfFlux slope estimation workflow.

This script allows manual selection of regions on a time series plot,
fits slopes for each selected region, and saves results and figures.
"""

import sys
from pathlib import Path
import pandas as pd
import plotly.graph_objects as go
from dash import Dash, dcc, html, Input, Output, State
import dash_bootstrap_components as dbc

# Allow running directly without installing the package
repo_root = Path(__file__).resolve().parents[1]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from lgr_surfflux.config import load_config, ConfigError
from lgr_surfflux.io import read_timeseries, save_results
from lgr_surfflux.slope import estimate_slope


def run_interactive_selection(cfg_path="config.yml"):
    # --- Load config ---
    try:
        cfg = load_config(cfg_path)
    except ConfigError as e:
        print(f"❌ Config error: {e}")
        sys.exit(1)

    data_cfg = cfg["data"]
    df = read_timeseries(data_cfg["path"],
                         time_col=data_cfg["time_col"],
                         value_col=data_cfg["value_col"])

    print(f"✅ Loaded {len(df)} rows from {data_cfg['path']}")

    time_col = data_cfg["time_col"]
    value_col = data_cfg["value_col"]
    output_cfg = cfg["output"]

    # --- Dash app setup ---
    app = Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
    app.title = "LGR SurfFlux – Interactive Region Selection"

    regions = []  # stores (start, end, slope, intercept, r2)

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df[time_col], y=df[value_col],
                             mode="lines+markers", name="Data"))
    fig.update_layout(title="Select regions with the range selector (Zoom)",
                      xaxis_title=time_col, yaxis_title=value_col,
                      dragmode="zoom")

    app.layout = dbc.Container([
        html.H2("Interactive Region Selection"),
        html.P("Use zoom or pan to focus on a region, then click 'Save current region'."),
        dcc.Graph(id="ts-plot", figure=fig, style={"height": "70vh"}),

        dbc.Row([
            dbc.Col(dbc.Button("Save current region", id="save-region-btn", color="primary")),
            dbc.Col(dbc.Button("Finish & export results", id="finish-btn", color="success")),
        ], className="mt-3 mb-3"),

        html.Div(id="status", style={"marginTop": "10px"}),
        html.Hr(),
        html.H4("Selected Regions"),
        html.Ul(id="region-list"),
        dcc.Store(id="stored-regions", data=[]),
    ], fluid=True)

    # --- Callbacks ---

    @app.callback(
        Output("stored-regions", "data"),
        Output("status", "children"),
        Output("region-list", "children"),
        Input("save-region-btn", "n_clicks"),
        State("ts-plot", "relayoutData"),
        State("stored-regions", "data"),
        prevent_initial_call=True
    )
    def save_region(n_clicks, relayout_data, stored):
        if not relayout_data or "xaxis.range[0]" not in relayout_data:
            return stored, "⚠️ Please zoom in to select a region first.", [html.Li(r) for r in stored]

        start = pd.to_datetime(relayout_data["xaxis.range[0]"])
        end = pd.to_datetime(relayout_data["xaxis.range[1]"])

        # Fit slope
        res = estimate_slope(df, start, end, time_col=time_col, value_col=value_col)
        print(res)
        stored.append({
            "start": str(start),
            "end": str(end),
            "slope": res["slope"],
            "intercept": res["intercept"],
            "r2": res["r_value"]
        })
        msg = f"✅ Region {len(stored)} saved: {start} → {end} (slope={res['slope']:.3g})"
        return stored, msg, [html.Li(f"{r['start']} → {r['end']} | slope={r['slope']:.3g}") for r in stored]

    @app.callback(
        Output("status", "children", allow_duplicate=True),
        Input("finish-btn", "n_clicks"),
        State("stored-regions", "data"),
        prevent_initial_call=True
    )
    def finish(n_clicks, stored):
        if not stored:
            return "⚠️ No regions selected."

        # Save results
        results_df = pd.DataFrame(stored)
        save_results(results_df,
                     out_csv=output_cfg["csv"],
                     out_excel=output_cfg["excel"])
        return f"✅ Saved {len(stored)} regions to {output_cfg['csv'] or output_cfg['excel']}"

    print("🚀 Open your browser to: http://127.0.0.1:8050")
    app.run(debug=True)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Interactive region selection for slope estimation.")
    parser.add_argument(
        "-c", "--config", default="config.yml",
        help="Path to configuration YAML file (default: config.yml)"
    )
    args = parser.parse_args()

    run_interactive_selection(args.config)

