"""Простой sparkline-виджет на блочных символах Юникода."""
from __future__ import annotations

from textual.widgets import Static

_BLOCKS = " ▁▂▃▄▅▆▇█"


def sparkline(values: list[float], width: int = 60) -> str:
    if not values:
        return ""
    if len(values) > width:
        step = len(values) / width
        sampled = [values[int(i * step)] for i in range(width)]
    else:
        sampled = values
    vmin, vmax = min(sampled), max(sampled)
    span = (vmax - vmin) or 1.0
    out = []
    for v in sampled:
        idx = int(round(((v - vmin) / span) * (len(_BLOCKS) - 1)))
        out.append(_BLOCKS[max(0, min(idx, len(_BLOCKS) - 1))])
    return "".join(out)


class Sparkline(Static):
    """Static-виджет, который отображает sparkline + диапазон [min,max]."""

    def __init__(self, title: str = "", width: int = 60, **kw) -> None:
        super().__init__("", **kw)
        self.title = title
        self.width = width

    def update_values(self, values: list[float], suffix: str = "") -> None:
        if not values:
            self.update(f"[bold]{self.title}[/bold]  (нет данных)")
            return
        line = sparkline(values, width=self.width)
        vmin, vmax = min(values), max(values)
        last = values[-1]
        self.update(
            f"[bold]{self.title}[/bold]  {line}  "
            f"min={vmin:.2f}  max={vmax:.2f}  last={last:.2f}{suffix}"
        )
