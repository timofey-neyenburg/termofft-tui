"""`thermofft export <run_uid>` — копирование/перегенерация артефактов."""
from __future__ import annotations

import shutil
from pathlib import Path

import click
from rich.console import Console

from thermofft.storage import repository

console = Console()
DEFAULT_DB = Path("thermofft.db")


@click.command(help="Скопировать артефакты прогона в указанную папку.")
@click.argument("run_uid")
@click.option("--to", "dest", type=click.Path(path_type=Path),
              default=Path("exports"), show_default=True)
@click.option("--db", "db_path", type=click.Path(path_type=Path),
              default=DEFAULT_DB, show_default=True)
def export(run_uid: str, dest: Path, db_path: Path) -> None:
    data = repository.get_run(db_path, run_uid)
    if data is None:
        console.print(f"[red]Run {run_uid} не найден.")
        raise SystemExit(1)

    src = Path(data["artifacts_dir"])
    if not src.exists():
        console.print(f"[red]Каталог артефактов отсутствует: {src}")
        raise SystemExit(1)

    target = dest / run_uid
    target.mkdir(parents=True, exist_ok=True)
    for p in src.rglob("*"):
        if p.is_file():
            rel = p.relative_to(src)
            out = target / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, out)
    console.print(f"[green]Артефакты скопированы в {target}")
