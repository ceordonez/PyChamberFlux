import plotly.graph_objects as go

def select_regions(df, time_col="time", value_col="value"):
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df[time_col],
        y=df[value_col],
        mode="lines",
        name="Time Series"
    ))
    fig.update_layout(
        title="Select regions to estimate slopes",
        dragmode="select",
        hovermode="x unified"
    )
    fig.show()
    print("Use the selection tool in Plotly (drag to highlight regions).")
    # Future: integrate callbacks or export selected x-ranges.

