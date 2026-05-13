"""Текстовая сводка результатов анализа (для CLI/TUI/PDF)."""
from __future__ import annotations

from thermofft.core.alerts import AlertReport
from thermofft.core.analysis import SpectralResult
from thermofft.core.metrics import MetricsResult


def _format_cycles(cycles, label: str) -> str:
    if not cycles:
        return f"  {label}: значимые циклы не выделены."
    lines = [f"  {label}:"]
    for c in cycles[:3]:
        lines.append(
            f"    #{c.rank} period ~ {c.period_hours:6.2f} h, "
            f"power {c.power:.3g}"
        )
    return "\n".join(lines)


def summarize(
    metrics: MetricsResult,
    spectrum: SpectralResult,
    alerts: AlertReport,
) -> str:
    """Собрать человекочитаемую сводку по результатам прогона."""
    a = metrics.amplitude
    c = metrics.correlation

    parts = ["=== ThermoFFT — сводка анализа ===", ""]
    parts.append("Амплитуды:")
    parts.append(
        f"  T_in:  raw={a.amp_in_raw:.2f} °C, robust(Q95-Q05)={a.amp_in_robust:.2f} °C"
    )
    parts.append(
        f"  T_out: raw={a.amp_out_raw:.2f} °C, robust(Q95-Q05)={a.amp_out_robust:.2f} °C"
    )
    parts.append(
        f"  Затухание (robust): {a.attenuation_robust:.3f}  "
        f"(raw: {a.attenuation_raw:.3f})"
    )
    parts.append("")
    parts.append("Корреляция:")
    parts.append(
        f"  Pearson(T_in,T_out) = {c.pearson:.3f}; "
        f"лаг = {c.lag_hours:+.2f} ч ({c.lag_steps:+d} шагов)"
    )
    parts.append("")
    parts.append(
        f"Out-of-range: {metrics.out_of_range_pct:.1f}% точек; "
        f"событий: {metrics.event_count}"
    )
    parts.append("")
    parts.append("Спектральные пики:")
    parts.append(_format_cycles(spectrum.cycles_T_in, "T_in"))
    parts.append(_format_cycles(spectrum.cycles_T_out, "T_out"))
    parts.append("")
    parts.append(f"Алерты: {alerts.count} (max severity = {alerts.max_severity})")
    for al in alerts.alerts:
        parts.append(f"  [{al.severity.upper():<8}] {al.code}: {al.message}")

    return "\n".join(parts)
