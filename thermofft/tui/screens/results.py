"""TUI: экран с результатами одного прогона."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Static, TabbedContent, TabPane

from thermofft.core.pipeline import PipelineResult


def _open_file(path: Path) -> None:
    if not path.exists():
        return
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception:  # noqa: BLE001
        pass


class ResultsScreen(Screen):
    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("p", "open_plots", "Open plots"),
        Binding("e", "open_report", "Open PDF"),
    ]

    def __init__(self, result: PipelineResult) -> None:
        super().__init__()
        self.result = result

    def compose(self) -> ComposeResult:
        r = self.result
        yield Header(show_clock=True)
        yield Static(f"Run {r.run_uid}  |  {r.duration_seconds:.2f} s  |  {r.out_dir}",
                     id="title")
        with TabbedContent(initial="metrics"):
            with TabPane("Metrics", id="metrics"):
                yield self._metrics_table()
            with TabPane("Spectrum", id="spectrum"):
                yield self._spectrum_table()
            with TabPane("Alerts", id="alerts"):
                yield self._alerts_table()
            with TabPane("Interpretation", id="interp"):
                with Vertical():
                    yield Static(r.interpretation or "(пусто)")
            with TabPane("Artifacts", id="artifacts"):
                yield self._artifacts_table()
        yield Footer()

    def _metrics_table(self) -> DataTable:
        t = DataTable(zebra_stripes=True)
        t.add_columns("Metric", "Value")
        m = self.result.metrics
        amp = m["amplitude"]
        corr = m["correlation"]
        rows = [
            ("amp_in_raw", f"{amp['amp_in_raw']:.3f}"),
            ("amp_out_raw", f"{amp['amp_out_raw']:.3f}"),
            ("amp_in_robust", f"{amp['amp_in_robust']:.3f}"),
            ("amp_out_robust", f"{amp['amp_out_robust']:.3f}"),
            ("attenuation_robust", f"{amp['attenuation_robust']:.3f}"),
            ("pearson", f"{corr['pearson']:.3f}"),
            ("lag_hours", f"{corr['lag_hours']:.3f}"),
            ("out_of_range_pct", f"{m['out_of_range_pct']:.2f}"),
            ("event_count", str(m["event_count"])),
        ]
        for k, v in rows:
            t.add_row(k, v)
        return t

    def _spectrum_table(self) -> DataTable:
        t = DataTable(zebra_stripes=True)
        t.add_columns("Channel", "Rank", "Period, h", "Power")
        for ch in ("cycles_T_in", "cycles_T_out"):
            for c in self.result.spectrum.get(ch, []):
                t.add_row(
                    "T_in" if ch == "cycles_T_in" else "T_out",
                    str(c["rank"]), f"{c['period_hours']:.2f}", f"{c['power']:.3g}",
                )
        return t

    def _alerts_table(self) -> DataTable:
        t = DataTable(zebra_stripes=True)
        t.add_columns("Severity", "Code", "Message")
        if not self.result.alerts:
            t.add_row("info", "—", "Алертов нет.")
        else:
            for a in self.result.alerts:
                t.add_row(a["severity"], a["code"], a["message"])
        return t

    def _artifacts_table(self) -> DataTable:
        t = DataTable(zebra_stripes=True)
        t.add_columns("File")
        for p in self.result.artifacts:
            t.add_row(str(p))
        return t

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_open_plots(self) -> None:
        plot_dir = self.result.out_dir / "plots"
        if plot_dir.exists():
            _open_file(plot_dir)

    def action_open_report(self) -> None:
        for p in self.result.artifacts:
            if p.suffix == ".pdf":
                _open_file(p)
                return
