"""TUI: live-экран с потоковой обработкой (simulate / tail)."""
from __future__ import annotations

import threading
from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Label, Select, Static

from thermofft.core.streaming import (
    StreamConfig,
    TickResult,
    run_stream,
    simulate_source,
    tail_csv_source,
)
from thermofft.tui.widgets.sparkline import Sparkline


class LiveScreen(Screen):
    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("s", "start", "Start"),
        Binding("x", "stop", "Stop"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._t_in_hist: list[float] = []
        self._t_out_hist: list[float] = []
        self._max_hist = 240
        self._last_result: TickResult | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static("ThermoFFT — Live stream", id="title")
        with Vertical(classes="panel"):
            with Horizontal():
                with Vertical():
                    yield Label("Source:")
                    yield Select(
                        options=[("simulate", "simulate"), ("tail", "tail")],
                        value="simulate", id="src", allow_blank=False,
                    )
                with Vertical():
                    yield Label("File (для tail):")
                    yield Input(placeholder="path/to/data.csv", id="input")
                with Vertical():
                    yield Label("Window:")
                    yield Input(value="24h", id="window")
                with Vertical():
                    yield Label("Tick (s):")
                    yield Input(value="1.0", id="tick")
                with Vertical():
                    yield Label("Speedup:")
                    yield Input(value="120", id="speedup")
            with Horizontal():
                yield Button("Start (s)", id="btn_start", variant="primary")
                yield Button("Stop (x)", id="btn_stop")
        with Vertical(classes="panel"):
            yield Sparkline(title="T_in ", id="spark_in", width=70)
            yield Sparkline(title="T_out", id="spark_out", width=70)
            yield Static("", id="metrics_line")
            yield Static("", id="status_line")
        yield Footer()

    def action_back(self) -> None:
        self.action_stop()
        self.app.pop_screen()

    def action_start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            self.notify("Уже запущено")
            return
        src = str(self.query_one("#src", Select).value)
        window = self.query_one("#window", Input).value or "24h"
        tick = float(self.query_one("#tick", Input).value or 1.0)
        speedup = float(self.query_one("#speedup", Input).value or 120.0)

        if src == "tail":
            path = Path(self.query_one("#input", Input).value or "")
            if not path.exists():
                self.notify(f"Файл не найден: {path}", severity="error")
                return
            gen = tail_csv_source(path, poll_interval=max(0.2, tick))
        else:
            gen = simulate_source(step_seconds=60, speedup=speedup)

        cfg = StreamConfig(
            window=window, resample_rule="1min",
            tick_interval=tick, out_dir=Path("runs/live"),
        )
        self._stop.clear()

        def worker() -> None:
            try:
                run_stream(gen, cfg, on_tick=self._on_tick, stop_flag=self._stop.is_set)
            except Exception as exc:  # noqa: BLE001
                self.app.call_from_thread(self._update_status, f"[red]{exc}")

        self._thread = threading.Thread(target=worker, daemon=True)
        self._thread.start()
        self._update_status("[green]running")

    def action_stop(self) -> None:
        self._stop.set()
        self._update_status("[yellow]stopped")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_start":
            self.action_start()
        elif event.button.id == "btn_stop":
            self.action_stop()

    def _on_tick(self, result: TickResult) -> None:
        m = result.metrics
        if m:
            self._t_in_hist.append(m["amplitude"]["amp_in_robust"])
            self._t_out_hist.append(m["amplitude"]["amp_out_robust"])
            self._t_in_hist = self._t_in_hist[-self._max_hist:]
            self._t_out_hist = self._t_out_hist[-self._max_hist:]
        self.app.call_from_thread(self._render, result)

    def _render(self, result: TickResult) -> None:
        self.query_one("#spark_in", Sparkline).update_values(self._t_in_hist, " °C")
        self.query_one("#spark_out", Sparkline).update_values(self._t_out_hist, " °C")
        if result.metrics:
            amp = result.metrics["amplitude"]
            corr = result.metrics["correlation"]
            self.query_one("#metrics_line", Static).update(
                f"attenuation={amp['attenuation_robust']:.3f}  "
                f"ρ={corr['pearson']:.3f}  lag={corr['lag_hours']:+.2f}h  "
                f"OOR={result.metrics['out_of_range_pct']:.1f}%"
            )
        ts = result.timestamp.strftime("%H:%M:%S") if result.timestamp else "—"
        self._update_status(
            f"tick #{result.tick}  ts={ts}  pts={result.window_points}  "
            f"elapsed={result.elapsed_seconds*1000:.0f} ms"
        )

    def _update_status(self, msg: str) -> None:
        try:
            self.query_one("#status_line", Static).update(msg)
        except Exception:  # noqa: BLE001
            pass
