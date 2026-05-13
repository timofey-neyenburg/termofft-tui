"""`thermofft analyze` — запуск pipeline на одном файле."""
from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from thermofft.config import AppConfig
from thermofft.core.pipeline import run as run_pipeline

console = Console()


STAGES = (
    "ingestion", "preprocessing", "spectrum", "metrics",
    "forecast", "alerts", "interpretation", "reporting",
)


def _build_config(**kw) -> AppConfig:
    cfg = AppConfig(**{k: v for k, v in kw.items() if v is not None})
    return cfg


@click.command(help="Прогон pipeline на указанном CSV/JSON файле.")
@click.argument("input_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--resample", "resample_rule", default="15min", show_default=True)
@click.option("--max-gap", "max_interp_gap", default="15min", show_default=True)
@click.option("--forecast-model", type=click.Choice(["expsmooth", "sarima", "naive"]),
              default="expsmooth", show_default=True)
@click.option("--horizon", "forecast_horizon", default="24h", show_default=True)
@click.option("--oor-low", type=float, default=18.0, show_default=True)
@click.option("--oor-high", type=float, default=27.0, show_default=True)
@click.option("--anomaly-rate", "anomaly_rate_thr_per_hour", type=float,
              default=1.5, show_default=True)
@click.option("--threshold-attenuation", "attenuation_warn", type=float,
              default=0.7, show_default=True)
@click.option("--out-dir", type=click.Path(path_type=Path), default=Path("runs"),
              show_default=True)
@click.option("--report-format", "report_formats", default="png,csv,xlsx,pdf",
              show_default=True, help="Comma-separated: png,csv,xlsx,pdf")
@click.option("--db", "db_path", type=click.Path(path_type=Path),
              default=Path("thermofft.db"), show_default=True)
@click.option("--no-cache", is_flag=True, default=False)
def analyze(
    input_path: Path,
    resample_rule: str,
    max_interp_gap: str,
    forecast_model: str,
    forecast_horizon: str,
    oor_low: float,
    oor_high: float,
    anomaly_rate_thr_per_hour: float,
    attenuation_warn: float,
    out_dir: Path,
    report_formats: str,
    db_path: Path,
    no_cache: bool,
) -> None:
    cfg = _build_config(
        resample_rule=resample_rule,
        max_interp_gap=max_interp_gap,
        forecast_model=forecast_model,
        forecast_horizon=forecast_horizon,
        oor_low=oor_low, oor_high=oor_high,
        anomaly_rate_thr_per_hour=anomaly_rate_thr_per_hour,
        attenuation_warn=attenuation_warn,
        out_dir=out_dir,
        report_formats=report_formats,
        db_path=db_path,
    )

    table = Table(title="ThermoFFT — стадии pipeline")
    table.add_column("Stage")
    table.add_column("Status", justify="right")
    rows: dict[str, str] = {s: "…" for s in STAGES}

    def progress(stage: str, status: str) -> None:
        rows[stage] = {"start": "running", "ok": "OK", "error": "ERROR"}.get(status, status)

    with console.status(f"[bold green]Анализ {input_path.name}…", spinner="dots"):
        result = run_pipeline(input_path, cfg, progress=progress, use_cache=not no_cache)

    for stage in STAGES:
        table.add_row(stage, rows.get(stage, "skip"))
    console.print(table)
    console.print()
    console.print(f"[bold]Run UID:[/bold] {result.run_uid}")
    console.print(f"[bold]Длительность:[/bold] {result.duration_seconds:.2f} с")
    console.print(f"[bold]Артефакты:[/bold] {result.out_dir}")
    console.print()
    console.print(result.interpretation)
