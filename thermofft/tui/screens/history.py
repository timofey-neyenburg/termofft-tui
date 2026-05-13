"""TUI: список прошлых прогонов."""
from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Static

from thermofft.storage import repository


class HistoryScreen(Screen):
    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("r", "refresh", "Refresh"),
    ]

    def __init__(self, db_path: Path) -> None:
        super().__init__()
        self.db_path = Path(db_path)

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static("История прогонов", id="title")
        with Vertical(classes="panel"):
            yield DataTable(id="runs", zebra_stripes=True)
        yield Footer()

    def on_mount(self) -> None:
        self.action_refresh()

    def action_refresh(self) -> None:
        t = self.query_one("#runs", DataTable)
        t.clear(columns=True)
        t.add_columns("UID", "Date", "Status", "Pts", "Atten.", "ρ", "Lag,h", "OOR%", "Ev", "File")
        rows = repository.list_runs(self.db_path, limit=200)
        if not rows:
            t.add_row("—", "(no runs yet)", "", "", "", "", "", "", "", "")
            return
        for r in rows:
            t.add_row(
                r.run_uid, r.created_at, r.status, str(r.clean_points),
                f"{r.attenuation_robust:.3f}", f"{r.pearson:.3f}",
                f"{r.lag_hours:.2f}", f"{r.out_of_range_pct:.1f}",
                str(r.event_count), r.input_path,
            )

    def action_back(self) -> None:
        self.app.pop_screen()
