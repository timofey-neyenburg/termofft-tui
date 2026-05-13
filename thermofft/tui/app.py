"""Textual TUI: главный класс приложения."""
from __future__ import annotations

from pathlib import Path

from textual.app import App
from textual.binding import Binding

from thermofft.tui.screens.history import HistoryScreen
from thermofft.tui.screens.main import MainScreen


class ThermoFFTApp(App):
    CSS = """
    Screen { layout: vertical; }
    #title { height: 1; padding: 0 1; background: $primary; color: $background; }
    #footer-hint { height: 1; color: $text-muted; padding: 0 1; }
    .panel { border: round $primary; padding: 1 1; margin: 1 0; }
    DataTable { height: auto; }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("h", "open_history", "History"),
        Binding("m", "open_main", "Main"),
    ]

    def __init__(self, db_path: Path) -> None:
        super().__init__()
        self.db_path = Path(db_path)
        self.last_run_uid: str | None = None

    def on_mount(self) -> None:
        self.push_screen(MainScreen(db_path=self.db_path))

    def action_open_history(self) -> None:
        self.push_screen(HistoryScreen(db_path=self.db_path))

    def action_open_main(self) -> None:
        self.pop_screen()
        self.push_screen(MainScreen(db_path=self.db_path))
