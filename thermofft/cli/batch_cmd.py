"""`thermofft batch` — APScheduler-watch для папки."""
from __future__ import annotations

import time
from pathlib import Path

import click
from rich.console import Console

from thermofft.config import AppConfig
from thermofft.core.pipeline import run as run_pipeline

console = Console()


def _scan_and_run(watch_dir: Path, processed: set[str], cfg: AppConfig) -> None:
    for ext in ("*.csv", "*.json"):
        for p in sorted(watch_dir.glob(ext)):
            key = str(p.resolve())
            if key in processed:
                continue
            console.print(f"[cyan]→ analyze {p.name}")
            try:
                result = run_pipeline(p, cfg)
                console.print(f"  [green]OK {result.run_uid} in {result.duration_seconds:.2f}s")
            except Exception as exc:  # noqa: BLE001
                console.print(f"  [red]ERROR: {exc}")
            processed.add(key)


@click.command(help="Сканировать папку и обрабатывать новые CSV/JSON.")
@click.argument("watch_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--interval", "interval_seconds", type=int, default=300, show_default=True,
              help="Период опроса в секундах")
@click.option("--once", is_flag=True, default=False, help="Один проход и выход")
@click.option("--db", "db_path", type=click.Path(path_type=Path),
              default=Path("thermofft.db"), show_default=True)
@click.option("--out-dir", type=click.Path(path_type=Path), default=Path("runs"),
              show_default=True)
def batch(
    watch_dir: Path, interval_seconds: int, once: bool,
    db_path: Path, out_dir: Path,
) -> None:
    cfg = AppConfig(db_path=db_path, out_dir=out_dir)
    processed: set[str] = set()
    console.print(f"[bold]Watching {watch_dir}, interval {interval_seconds}s")

    if once:
        _scan_and_run(watch_dir, processed, cfg)
        return

    try:
        while True:
            _scan_and_run(watch_dir, processed, cfg)
            time.sleep(interval_seconds)
    except KeyboardInterrupt:
        console.print("[yellow]Stopped.")
