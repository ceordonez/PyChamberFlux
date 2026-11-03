import click
from .config import load_config
from .io import read_timeseries, save_results
from .slope import estimate_slope

@click.group()
def cli():
    """LGR SurfFlux command-line tool"""

@cli.command()
@click.option("--config", "-c", required=True, help="Path to config.yml")
def run(config):
    cfg = load_config(config)
    df = read_timeseries(cfg["data"]["path"])
    results = []
    for region in cfg["regions"]:
        results.append(estimate_slope(df, **region))
    save_results(pd.DataFrame(results), cfg["output"]["csv"], cfg["output"]["excel"])
    print("Finished! Results saved.")

