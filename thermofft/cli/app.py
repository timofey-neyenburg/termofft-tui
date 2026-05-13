"""Click CLI: thermofft <command>."""
from __future__ import annotations

import sys
from pathlib import Path

import click


def _force_utf8_stdio() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                pass


_force_utf8_stdio()

from thermofft.cli import analyze_cmd, batch_cmd, export_cmd, history_cmd
from thermofft.config import AppConfig
from thermofft.logging_setup import setup_logging
from thermofft.storage import db


@click.group(help="АИС ThermoFFT — анализ суточных колебаний температуры.")
@click.option("--log-level", default="INFO", show_default=True)
@click.option("--log-file", type=click.Path(dir_okay=False, path_type=Path), default=None)
@click.pass_context
def cli(ctx: click.Context, log_level: str, log_file: Path | None) -> None:
    ctx.ensure_object(dict)
    ctx.obj["logger"] = setup_logging(log_level, log_file)


@cli.command(name="init-db", help="Создать таблицы SQLite (idempotent).")
@click.option("--db", "db_path", type=click.Path(path_type=Path),
              default=AppConfig().db_path, show_default=True)
def init_db_cmd(db_path: Path) -> None:
    db.init_db(db_path)
    click.echo(f"OK: schema initialized at {db_path}")


cli.add_command(analyze_cmd.analyze)
cli.add_command(history_cmd.history)
cli.add_command(history_cmd.show)
cli.add_command(history_cmd.similar)
cli.add_command(export_cmd.export)
cli.add_command(batch_cmd.batch)


@cli.command(name="tui", help="Запустить интерактивный TUI (Textual).")
@click.option("--db", "db_path", type=click.Path(path_type=Path),
              default=AppConfig().db_path, show_default=True)
def tui_cmd(db_path: Path) -> None:
    from thermofft.tui.app import ThermoFFTApp

    db.init_db(db_path)
    ThermoFFTApp(db_path=db_path).run()


if __name__ == "__main__":  # pragma: no cover
    cli()
