"""`thermofft history` / `show` / `similar`."""
from __future__ import annotations

import json
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from thermofft.storage import repository

console = Console()
DEFAULT_DB = Path("thermofft.db")


def _runs_table(rows) -> Table:
    t = Table(title="Прошлые прогоны ThermoFFT")
    t.add_column("UID", style="cyan")
    t.add_column("Дата", style="white")
    t.add_column("Файл", overflow="fold")
    t.add_column("Status")
    t.add_column("Pts", justify="right")
    t.add_column("Atten.", justify="right")
    t.add_column("ρ", justify="right")
    t.add_column("Lag,h", justify="right")
    t.add_column("OOR%", justify="right")
    t.add_column("Ev", justify="right")
    for r in rows:
        t.add_row(
            r.run_uid, r.created_at, r.input_path, r.status,
            str(r.clean_points),
            f"{r.attenuation_robust:.3f}",
            f"{r.pearson:.3f}",
            f"{r.lag_hours:.2f}",
            f"{r.out_of_range_pct:.1f}",
            str(r.event_count),
        )
    return t


@click.command(help="Список прошлых прогонов.")
@click.option("--limit", type=int, default=20, show_default=True)
@click.option("--db", "db_path", type=click.Path(path_type=Path),
              default=DEFAULT_DB, show_default=True)
def history(limit: int, db_path: Path) -> None:
    rows = repository.list_runs(db_path, limit=limit)
    if not rows:
        console.print("[yellow]Прогонов пока нет.")
        return
    console.print(_runs_table(rows))


@click.command(help="Детальная информация по run-у.")
@click.argument("run_uid")
@click.option("--db", "db_path", type=click.Path(path_type=Path),
              default=DEFAULT_DB, show_default=True)
def show(run_uid: str, db_path: Path) -> None:
    data = repository.get_run(db_path, run_uid)
    if data is None:
        console.print(f"[red]Run {run_uid} не найден.")
        raise SystemExit(1)
    console.rule(f"Run {run_uid}")
    console.print(f"Создан: {data['created_at']}  |  длительность: {data['duration_seconds']:.2f} с")
    console.print(f"Файл: {data['input_path']}")
    console.print(f"Артефакты: {data['artifacts_dir']}")
    console.rule("Интерпретация")
    console.print(data["interpretation"] or "(нет)")
    console.rule("Алерты")
    if not data["alerts"]:
        console.print("(нет)")
    else:
        for a in data["alerts"]:
            console.print(f"  [{a['severity'].upper()}] {a['code']}: {a['message']}")
    console.rule("Стадии")
    for s in data["stages"]:
        console.print(f"  {s['stage']:<14} {s['status']:<8} {s['duration_seconds']:.3f} s  {s['message']}")
    console.rule("Метрики (JSON)")
    console.print_json(json.dumps(data["metrics"], default=str))


@click.command(help="Топ-3 похожих прогона (L2 по 5 метрикам).")
@click.argument("run_uid")
@click.option("--top", type=int, default=3, show_default=True)
@click.option("--db", "db_path", type=click.Path(path_type=Path),
              default=DEFAULT_DB, show_default=True)
def similar(run_uid: str, top: int, db_path: Path) -> None:
    pairs = repository.similar_runs(db_path, run_uid, top_k=top)
    if not pairs:
        console.print("[yellow]Нет других прогонов для сравнения.")
        return
    t = Table(title=f"Похожие прогоны для {run_uid}")
    t.add_column("UID", style="cyan")
    t.add_column("Дата")
    t.add_column("Distance", justify="right")
    t.add_column("Atten.", justify="right")
    t.add_column("ρ", justify="right")
    t.add_column("Lag,h", justify="right")
    for r, d in pairs:
        t.add_row(
            r.run_uid, r.created_at, f"{d:.3f}",
            f"{r.attenuation_robust:.3f}", f"{r.pearson:.3f}", f"{r.lag_hours:.2f}",
        )
    console.print(t)
