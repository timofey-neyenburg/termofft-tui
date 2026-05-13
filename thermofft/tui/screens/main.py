"""TUI: главный экран — ввод параметров + запуск анализа."""
from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Label, Select, Static

from thermofft.config import AppConfig
from thermofft.tui.screens.progress import ProgressScreen


class MainScreen(Screen):
    BINDINGS = [
        Binding("r", "run", "Run"),
        Binding("h", "history", "History"),
    ]

    def __init__(self, db_path: Path) -> None:
        super().__init__()
        self.db_path = Path(db_path)

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static("ThermoFFT — анализ температурных временных рядов", id="title")
        with Vertical(classes="panel"):
            yield Label("Файл CSV/JSON:")
            yield Input(placeholder="path/to/data.csv", id="input_path")
            with Horizontal():
                with Vertical():
                    yield Label("Resample:")
                    yield Input(value="15min", id="resample")
                with Vertical():
                    yield Label("Max gap:")
                    yield Input(value="15min", id="max_gap")
                with Vertical():
                    yield Label("Horizon:")
                    yield Input(value="24h", id="horizon")
            with Horizontal():
                with Vertical():
                    yield Label("Forecast model:")
                    yield Select(
                        options=[("expsmooth", "expsmooth"), ("sarima", "sarima"), ("naive", "naive")],
                        value="expsmooth", id="model", allow_blank=False,
                    )
                with Vertical():
                    yield Label("OOR low:")
                    yield Input(value="18", id="oor_low")
                with Vertical():
                    yield Label("OOR high:")
                    yield Input(value="27", id="oor_high")
            with Horizontal():
                yield Button("Run analysis", variant="primary", id="btn_run")
                yield Button("History", id="btn_history")
        yield Static("[bold]r[/bold] — запустить, [bold]h[/bold] — история, [bold]q[/bold] — выход",
                     id="footer-hint")
        yield Footer()

    def _gather_config(self) -> tuple[Path, AppConfig] | None:
        input_path = (self.query_one("#input_path", Input).value or "").strip()
        if not input_path:
            self.notify("Укажи путь к CSV/JSON", severity="error")
            return None
        p = Path(input_path)
        if not p.exists():
            self.notify(f"Файл не найден: {p}", severity="error")
            return None

        try:
            cfg = AppConfig(
                resample_rule=self.query_one("#resample", Input).value or "15min",
                max_interp_gap=self.query_one("#max_gap", Input).value or "15min",
                forecast_horizon=self.query_one("#horizon", Input).value or "24h",
                forecast_model=str(self.query_one("#model", Select).value),
                oor_low=float(self.query_one("#oor_low", Input).value or 18),
                oor_high=float(self.query_one("#oor_high", Input).value or 27),
                db_path=self.db_path,
            )
        except Exception as exc:  # noqa: BLE001
            self.notify(f"Ошибка конфигурации: {exc}", severity="error")
            return None
        return p, cfg

    def action_run(self) -> None:
        bundle = self._gather_config()
        if bundle is None:
            return
        path, cfg = bundle
        self.app.push_screen(ProgressScreen(input_path=path, config=cfg))

    def action_history(self) -> None:
        from thermofft.tui.screens.history import HistoryScreen
        self.app.push_screen(HistoryScreen(db_path=self.db_path))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_run":
            self.action_run()
        elif event.button.id == "btn_history":
            self.action_history()
