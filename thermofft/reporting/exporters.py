"""Экспорт результатов в CSV / XLSX / PDF."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from thermofft.core.alerts import AlertReport
from thermofft.core.analysis import SpectralResult
from thermofft.core.metrics import MetricsResult


def export_csv(
    clean_df: pd.DataFrame,
    daily_df: pd.DataFrame,
    forecast_df: pd.DataFrame,
    out_dir: Path,
) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    clean_path = out_dir / "clean_series.csv"
    clean_df.to_csv(clean_path, index_label="noted_date")
    paths.append(clean_path)

    if not daily_df.empty:
        daily_path = out_dir / "daily_summary.csv"
        daily_df.to_csv(daily_path, index_label="date")
        paths.append(daily_path)

    if not forecast_df.empty:
        fc_path = out_dir / "forecast.csv"
        forecast_df.to_csv(fc_path, index_label="noted_date")
        paths.append(fc_path)
    return paths


def export_xlsx(
    metrics: MetricsResult,
    spectrum: SpectralResult,
    alerts: AlertReport,
    daily_df: pd.DataFrame,
    out_dir: Path,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "metrics.xlsx"

    amp = metrics.amplitude
    corr = metrics.correlation
    summary = pd.DataFrame(
        [
            ("amp_in_raw", amp.amp_in_raw),
            ("amp_out_raw", amp.amp_out_raw),
            ("amp_in_robust", amp.amp_in_robust),
            ("amp_out_robust", amp.amp_out_robust),
            ("attenuation_raw", amp.attenuation_raw),
            ("attenuation_robust", amp.attenuation_robust),
            ("pearson", corr.pearson),
            ("lag_steps", corr.lag_steps),
            ("lag_hours", corr.lag_hours),
            ("out_of_range_pct", metrics.out_of_range_pct),
            ("event_count", metrics.event_count),
        ],
        columns=["metric", "value"],
    )

    spec_rows = []
    for label, cycles in (("T_in", spectrum.cycles_T_in), ("T_out", spectrum.cycles_T_out)):
        for c in cycles:
            spec_rows.append({
                "channel": label, "rank": c.rank,
                "frequency_hz": c.frequency_hz,
                "period_hours": c.period_hours, "power": c.power,
            })
    spec_df = pd.DataFrame(spec_rows)

    alert_df = pd.DataFrame([a.model_dump() for a in alerts.alerts])
    events_df = pd.DataFrame([e.model_dump() for e in metrics.events])

    with pd.ExcelWriter(path, engine="openpyxl") as w:
        summary.to_excel(w, sheet_name="summary", index=False)
        if not spec_df.empty:
            spec_df.to_excel(w, sheet_name="spectrum", index=False)
        if not alert_df.empty:
            alert_df.to_excel(w, sheet_name="alerts", index=False)
        if not events_df.empty:
            events_df.to_excel(w, sheet_name="events", index=False)
        if not daily_df.empty:
            daily_df.to_excel(w, sheet_name="daily", index_label="date")

    return path


def export_pdf(
    interpretation_text: str,
    plot_paths: list[Path],
    out_dir: Path,
) -> Path:
    """Текстовый отчёт + графики на отдельных страницах (ReportLab)."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        Image as RLImage,
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "report.pdf"
    doc = SimpleDocTemplate(
        str(path), pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=2 * cm, bottomMargin=2 * cm,
    )
    styles = getSampleStyleSheet()
    story: list = [Paragraph("ThermoFFT — отчёт об анализе", styles["Title"]), Spacer(1, 0.5 * cm)]
    for line in interpretation_text.splitlines():
        safe = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        story.append(Paragraph(safe or "&nbsp;", styles["BodyText"]))
    for img_path in plot_paths:
        if img_path is None or not Path(img_path).exists():
            continue
        story.append(PageBreak())
        story.append(Paragraph(Path(img_path).stem, styles["Heading2"]))
        story.append(RLImage(str(img_path), width=17 * cm, height=9 * cm))

    doc.build(story)
    return path
