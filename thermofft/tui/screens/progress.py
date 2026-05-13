"""TUI: экран прогона pipeline в фоне с live-логом стадий."""
from __future__ import annotations

import threading
from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, Log, Static

from thermofft.config import AppConfig
from thermofft.core.pipeline import PipelineResult, run as run_pipeline


class ProgressScreen(Screen):
    BINDINGS = [
        Binding("escape", "back", "Back"),
    ]

    def __init__(self, input_path: Path, config: AppConfig) -> None:
        super().__init__()
        self.input_path = input_path
        self.config = config
        self.result: PipelineResult | None = None
        self.error: Exception | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static(f"Анализ: {self.input_path}", id="title")
        with Vertical(classes="panel"):
            yield Log(id="log", highlight=True, max_lines=400)
        yield Footer()

    def on_mount(self) -> None:
        self.run_worker(self._run_pipeline, exclusive=True, thread=True, name="pipeline")

    def _progress(self, stage: str, status: str) -> None:
        log = self.query_one("#log", Log)
        self.app.call_from_thread(log.write_line, f"[{status:<6}] {stage}")

    def _run_pipeline(self) -> None:
        try:
            self.result = run_pipeline(self.input_path, self.config, progress=self._progress)
        except Exception as exc:  # noqa: BLE001
            self.error = exc

    def on_worker_state_changed(self, _event) -> None:
        worker = next((w for w in self.app.workers if w.name == "pipeline"), None)
        if worker is None or not worker.is_finished:
            return
        log = self.query_one("#log", Log)
        if self.error is not None:
            log.write_line(f"[ERROR ] {self.error}")
            return
        if self.result is not None:
            from thermofft.tui.screens.results import ResultsScreen

            log.write_line("")
            log.write_line(f"Готово. Run UID: {self.result.run_uid}")
            log.write_line(f"Артефакты: {self.result.out_dir}")
            self.app.last_run_uid = self.result.run_uid
            self.app.push_screen(ResultsScreen(result=self.result))

    def action_back(self) -> None:
        self.app.pop_screen()
