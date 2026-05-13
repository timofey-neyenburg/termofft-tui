"""`thermofft stream` — реал-тайм обработка с генерацией диаграмм."""
from __future__ import annotations

import signal
from pathlib import Path

import click
from rich.console import Console
from rich.live import Live
from rich.table import Table

from thermofft.core.streaming import (
    StreamConfig,
    TickResult,
    run_stream,
    simulate_source,
    tail_csv_source,
)

console = Console()
_STOPPED = {"flag": False}


def _stop_handler(_signum, _frame) -> None:
    _STOPPED["flag"] = True


def _metrics_table(result: TickResult) -> Table:
    t = Table(title=f"Tick #{result.tick}  |  window points: {result.window_points}  "
                   f"|  elapsed: {result.elapsed_seconds*1000:.0f} ms")
    t.add_column("Metric")
    t.add_column("Value", justify="right")
    m = result.metrics
    if not m:
        t.add_row("(buffer warming up)", "—")
        return t
    amp = m["amplitude"]
    corr = m["correlation"]
    t.add_row("amp_in_robust", f"{amp['amp_in_robust']:.3f}")
    t.add_row("amp_out_robust", f"{amp['amp_out_robust']:.3f}")
    t.add_row("attenuation_robust", f"{amp['attenuation_robust']:.3f}")
    t.add_row("pearson(T_in,T_out)", f"{corr['pearson']:.3f}")
    t.add_row("lag_hours", f"{corr['lag_hours']:.2f}")
    t.add_row("out_of_range_pct", f"{m['out_of_range_pct']:.2f}")
    t.add_row("event_count", str(m["event_count"]))

    cycles = result.spectrum.get("cycles_T_in", [])
    if cycles:
        top = cycles[0]
        t.add_row(
            "top cycle T_in (h)",
            f"{top['period_hours']:.2f} (power {top['power']:.2g})",
        )
    return t


@click.command(help="Реал-тайм обработка с обновлением графиков на каждом тике.")
@click.option("--source", type=click.Choice(["simulate", "tail"]),
              default="simulate", show_default=True,
              help="Источник данных")
@click.option("--input", "input_path", type=click.Path(path_type=Path),
              default=None, help="CSV для режима tail")
@click.option("--window", default="24h", show_default=True,
              help="Размер скользящего окна (например 24h, 6h)")
@click.option("--resample", "resample_rule", default="1min", show_default=True)
@click.option("--tick-interval", type=float, default=1.0, show_default=True,
              help="Период перерисовки графиков, секунды")
@click.option("--step", "step_seconds", type=int, default=60, show_default=True,
              help="(simulate) шаг эмулируемого времени, секунды")
@click.option("--speedup", type=float, default=120.0, show_default=True,
              help="(simulate) во сколько раз ускорить эмулируемое время")
@click.option("--max-ticks", type=int, default=None,
              help="Остановиться после N тиков (по умолчанию — Ctrl+C)")
@click.option("--out-dir", type=click.Path(path_type=Path),
              default=Path("runs/live"), show_default=True,
              help="Папка для live_timeseries.png и live_spectrum.png")
@click.option("--top-k", type=int, default=5, show_default=True)
def stream(
    source: str,
    input_path: Path | None,
    window: str,
    resample_rule: str,
    tick_interval: float,
    step_seconds: int,
    speedup: float,
    max_ticks: int | None,
    out_dir: Path,
    top_k: int,
) -> None:
    if source == "tail":
        if input_path is None:
            raise click.UsageError("--input <csv> обязателен при --source tail")
        if not input_path.exists():
            raise click.UsageError(f"Файл не найден: {input_path}")
        gen = tail_csv_source(input_path, poll_interval=tick_interval)
        header = f"[bold]tail[/bold] {input_path}"
    else:
        gen = simulate_source(step_seconds=step_seconds, speedup=speedup)
        header = (
            f"[bold]simulate[/bold] step={step_seconds}s × speedup={speedup:g} "
            f"(эмулируется {step_seconds * speedup:.0f} секунд внутр. времени в секунду)"
        )

    signal.signal(signal.SIGINT, _stop_handler)
    try:
        signal.signal(signal.SIGTERM, _stop_handler)
    except (AttributeError, ValueError):  # SIGTERM может отсутствовать на Windows
        pass

    cfg = StreamConfig(
        window=window,
        resample_rule=resample_rule,
        tick_interval=tick_interval,
        top_k=top_k,
        out_dir=out_dir,
        max_ticks=max_ticks,
    )

    console.print(header)
    console.print(f"window={window}  resample={resample_rule}  "
                  f"tick={tick_interval}s  out_dir={out_dir}")
    console.print("[dim]Ctrl+C — остановить[/dim]\n")

    with Live(_metrics_table(TickResult(0, None, 0, [], {}, {}, 0.0)),  # type: ignore[arg-type]
              refresh_per_second=4, console=console) as live:

        def on_tick(result: TickResult) -> None:
            live.update(_metrics_table(result))

        try:
            run_stream(gen, cfg, on_tick=on_tick, stop_flag=lambda: _STOPPED["flag"])
        except KeyboardInterrupt:
            pass

    console.print(f"\n[green]Stream остановлен. Последние графики: {out_dir}")
