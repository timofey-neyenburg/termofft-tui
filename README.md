# АИС ThermoFFT

> Автоматизированная информационная система анализа суточных колебаний температуры микроклимата помещений.
> Учебная разработка по ТЗ КГТУ (ГОСТ 34.602–89), ст. преподаватель Подтопельный В.В., группа 25-ВТ/м.

CLI + TUI приложение на Python: загружает временные ряды температуры из CSV/JSON, выполняет предобработку, спектральный анализ методом FFT, рассчитывает метрики (амплитуда, затухание, корреляция, лаг, out-of-range), строит прогноз, генерирует визуализации/отчёты (PNG, PDF, XLSX, CSV) и оповещения. Все прогоны и метаданные хранятся в SQLite.

## Содержание

- [Возможности](#возможности)
- [Архитектура](#архитектура)
- [Требования](#требования)
- [Установка](#установка)
- [Быстрый старт](#быстрый-старт)
- [Команды CLI](#команды-cli)
- [TUI режим](#tui-режим)
- [Формат входных данных](#формат-входных-данных)
- [Артефакты прогона](#артефакты-прогона)
- [Параметры конфигурации](#параметры-конфигурации)
- [Тестирование](#тестирование)
- [Структура проекта](#структура-проекта)
- [Соответствие ТЗ](#соответствие-тз)
- [Известные ограничения](#известные-ограничения)

## Возможности

- Импорт **CSV / JSON** логов IoT-датчиков, валидация схемы и временных меток.
- Предобработка: ресемплинг (по умолчанию 15 мин), интерполяция разрывов ≤ `max_gap`, маркировка длинных разрывов как недостоверных.
- Спектральный анализ методом FFT/periodogram, выделение top-K циклов с указанием периода (часы) и мощности.
- Метрики: амплитуда (raw + robust Q95–Q05), затухание (`attenuation = amp_in / amp_out`), Pearson, кросс-корреляционный лаг, доля out-of-range, события резких изменений `|ΔT/Δч| ≥ порог`.
- Прогноз температуры: **ExponentialSmoothing**, **SARIMA** (statsmodels), либо наивный (повтор суток).
- Алерты по комбинированным правилам (затухание, OOR%, лаг, частота событий, OOR в прогнозе).
- Визуализация **300 dpi**: temperature timeseries, спектр, дневная тепловая карта.
- Отчёты: CSV (чистый ряд, дневная сводка, прогноз), XLSX (summary/spectrum/alerts/events/daily), PDF (интерпретация + графики).
- Метаданные `experiment_meta.json` + `validation_summary.json` для воспроизводимости.
- SQLite-хранилище прогонов с WAL-режимом, LRU+TTL-кэш результатов, поиск похожих прогонов по L2 на 5 нормализованных метриках.
- Полу­автоматический режим (Click CLI), интерактивный режим (Textual TUI), пакетный режим (APScheduler watch-folder).

## Архитектура

```
┌─────────────┐    ┌──────────────────────────────────────────────┐
│   CLI       │    │                                              │
│  (Click)    │───▶│   thermofft.core.pipeline.run(input, cfg)    │
│             │    │                                              │
│   TUI       │───▶│   ingestion → preprocessing → spectrum →     │
│ (Textual)   │    │   metrics → forecast → alerts →              │
│             │    │   interpretation → reporting → storage       │
│   batch     │───▶│                                              │
│(APScheduler)│    └──────────────────────────────────────────────┘
└─────────────┘                       │
                                      ▼
                        SQLite (WAL) + runs/<ts>_<uid>/
```

Каждая стадия пишет лог в `stage_logs`, ошибка одной стадии не теряет результаты предыдущих. UI-слои UI-агностичны: и CLI, и TUI вызывают одну функцию `pipeline.run`.

## Требования

- Windows 10 / Linux / macOS
- Python **3.10+**
- 8 GB RAM (по ТЗ), свободное место ≥ 500 МБ

Все зависимости — открытые библиотеки: pandas, numpy, scipy, statsmodels, scikit-learn, matplotlib, openpyxl, reportlab, sqlalchemy, pydantic, click, rich, textual, apscheduler.

## Установка

```bash
# 1) Создать виртуальное окружение (рекомендуется)
python -m venv .venv

# Linux / macOS
source .venv/bin/activate
# Windows PowerShell
.venv\Scripts\Activate.ps1
# Windows cmd
.venv\Scripts\activate.bat

# 2) Установить пакет
pip install -e .

# 3) Установить вместе с dev-зависимостями (pytest и т.д.)
pip install -e ".[dev]"

# 4) Инициализировать SQLite-схему
thermofft init-db
```

После установки доступны:
- `thermofft <command>` (entry point)
- `python -m thermofft <command>` (модуль)

## Быстрый старт

```bash
# 1) Сгенерировать тестовый датасет (7 суток, шаг 60с — 20160 строк)
python data/samples/generate.py --out data/samples/demo_7d.csv --days 7 --step 60

# 2) Прогнать полный pipeline
thermofft analyze data/samples/demo_7d.csv

# 3) Посмотреть список прошлых прогонов
thermofft history --limit 10

# 4) Детали по конкретному run-у
thermofft show <run_uid>

# 5) Найти похожие прогоны (L2-расстояние по 5 метрикам)
thermofft similar <run_uid>

# 6) Скопировать артефакты в отдельную папку
thermofft export <run_uid> --to exports/

# 7) Интерактивный TUI
thermofft tui

# 8) Пакетный режим: следить за папкой и обрабатывать новые файлы
thermofft batch data/samples --interval 300 --once
```

После `analyze` смотрим в `runs/<timestamp>_<uid>/`:
- `plots/timeseries.png`, `plots/spectrum.png`, `plots/heatmap.png`
- `clean_series.csv`, `daily_summary.csv`, `forecast.csv`
- `metrics.xlsx`, `report.pdf`, `interpretation.txt`
- `experiment_meta.json`, `validation_summary.json`

## Команды CLI

| Команда | Описание |
|---|---|
| `thermofft init-db` | Создать таблицы SQLite (idempotent) |
| `thermofft analyze <file>` | Запустить полный pipeline на CSV/JSON |
| `thermofft history [--limit N]` | Таблица прошлых прогонов |
| `thermofft show <run_uid>` | Подробности по run-у (метрики, алерты, стадии) |
| `thermofft similar <run_uid> [--top N]` | Топ-N похожих прогонов |
| `thermofft export <run_uid> --to <dir>` | Скопировать артефакты |
| `thermofft batch <dir> [--interval N] [--once]` | Watch-folder режим |
| `thermofft tui` | Запустить интерактивный Textual TUI |

Все команды: `thermofft <cmd> --help` для полного списка опций.

## TUI режим

```bash
thermofft tui
```

Экраны:

- **Main** — путь к CSV/JSON, параметры (resample, max_gap, horizon, модель прогноза, OOR-границы), кнопка Run.
- **Progress** — live-лог стадий pipeline в фоновом потоке.
- **Results** — табы:
  - Metrics — таблица всех числовых метрик
  - Spectrum — top-K циклов по T_in / T_out
  - Alerts — список оповещений
  - Interpretation — текстовая сводка
  - Artifacts — пути ко всем сгенерированным файлам
- **History** — все прогоны из SQLite.

Горячие клавиши: `r` — Run, `h` — History, `p` — открыть папку с графиками, `e` — открыть PDF, `Esc` — назад, `q` — выход.

## Формат входных данных

CSV или JSON с обязательными колонками:

| Колонка | Тип | Описание |
|---|---|---|
| `noted_date` | datetime | метка времени (ISO 8601 или `DD.MM.YYYY HH:MM`) |
| `temp` | float | температура, °C |
| `out/in` | string | `"in"` (внутри помещения) или `"out"` (снаружи) |

JSON может быть либо массивом объектов, либо `{"records": [...]}`.

Пример CSV:
```csv
noted_date,temp,out/in
2025-01-01T00:00:00,22.05,in
2025-01-01T00:00:00,8.12,out
2025-01-01T00:01:00,22.04,in
2025-01-01T00:01:00,8.18,out
```

Битые строки (невалидная дата, нечисловая температура, неизвестный режим) автоматически отбрасываются с предупреждением.

## Артефакты прогона

В каталоге `runs/<YYYYMMDDTHHMMSS>_<run_uid>/`:

```
plots/
  timeseries.png      # T_in / T_out + forecast (300 dpi)
  spectrum.png        # PSD по периодам (часы)
  heatmap.png         # сутки × часы, mean T_in
clean_series.csv      # объединённый ресемплированный ряд
daily_summary.csv     # min/max/mean/amp/attenuation по дням
forecast.csv          # прогноз T_in на заданный горизонт
metrics.xlsx          # листы: summary / spectrum / alerts / events / daily
report.pdf            # интерпретация + графики
interpretation.txt    # текстовая сводка
experiment_meta.json  # сигнатура входа, конфиг, метрики, среда, seed
validation_summary.json  # статус проверок (схема, корреляция, attenuation)
```

## Параметры конфигурации

| Параметр CLI | По умолчанию | Описание |
|---|---|---|
| `--resample` | `15min` | Шаг ресемплинга |
| `--max-gap` | `15min` | Лимит интерполяции; большие разрывы помечаются как недостоверные |
| `--forecast-model` | `expsmooth` | `expsmooth` / `sarima` / `naive` |
| `--horizon` | `24h` | Горизонт прогноза |
| `--oor-low` | `18` | Нижняя граница комфорта, °C |
| `--oor-high` | `27` | Верхняя граница комфорта, °C |
| `--anomaly-rate` | `1.5` | Порог `|ΔT / Δч|` для события, °C/ч |
| `--threshold-attenuation` | `0.7` | Порог слабого затухания |
| `--out-dir` | `runs` | Папка для артефактов |
| `--report-format` | `png,csv,xlsx,pdf` | Какие отчёты генерировать |
| `--db` | `thermofft.db` | Путь к SQLite |
| `--no-cache` | _flag_ | Игнорировать LRU-кэш результатов |
| `--log-level` | `INFO` | Уровень логирования root |
| `--log-file` | _none_ | Путь к файлу логов |

## Тестирование

```bash
# Все тесты, кроме perf-gate
python -m pytest tests/ -m "not perf"

# Полный набор (включая 100k точек ≤ 10 с)
python -m pytest tests/

# Конкретный модуль
python -m pytest tests/test_metrics.py -v
```

Покрытие:
- `test_ingestion.py` — корректные/битые CSV/JSON, отсутствие колонок, drop невалидных строк
- `test_preprocessing.py` — resample, интерполяция, маркировка длинных разрывов
- `test_analysis.py` — синтетический sin(24h) → пик 24h ±1 ч
- `test_metrics.py` — attenuation < 1, лаг ≈ ожидаемый, OOR%
- `test_alerts.py` — пороги срабатывают/не срабатывают
- `test_storage.py` — round-trip run, similar-runs
- `test_pipeline_perf.py` — **100k точек < 10 с** (требование ТЗ)

## Структура проекта

```
thermofft/
  __init__.py
  __main__.py
  config.py                # AppConfig (Pydantic)
  logging_setup.py         # rich logging
  core/
    ingestion.py           # CSV/JSON loader + валидация
    preprocessing.py       # resample + interpolate
    analysis.py            # periodogram + peaks
    metrics.py             # amp, attenuation, corr, lag, OOR
    forecasting.py         # ExpSmoothing / SARIMA / naive
    alerts.py              # rule engine
    interpretation.py      # narrative summary
    pipeline.py            # orchestrator
  storage/
    db.py                  # SQLAlchemy engine, WAL
    models.py              # AnalysisRun / StageLog / AlertEvent / CacheEntry
    repository.py          # CRUD + similar-runs
    cache.py               # LRU + TTL
  reporting/
    plots.py               # matplotlib 300 dpi
    exporters.py           # CSV / XLSX / PDF
    meta.py                # experiment_meta + validation_summary
  cli/                     # Click commands
  tui/                     # Textual App + screens

data/samples/generate.py   # генератор синтетики
tests/                     # pytest
docs/user_guide.md         # руководство пользователя
pyproject.toml
README.md
```

## Соответствие ТЗ

| Требование ТЗ | Реализация |
|---|---|
| Импорт CSV/JSON | `core/ingestion.py` |
| Валидация структуры | Pydantic + `validate_schema` |
| Интерполяция ≤ 15 мин | `core/preprocessing.py` (limit-aware) |
| Очистка и нормализация | `core/preprocessing.py` |
| FFT, амплитуда, частота | `core/analysis.py` + `core/metrics.py` |
| Прогнозирование | `core/forecasting.py` (statsmodels) |
| Графики и спектрограммы 300 dpi | `reporting/plots.py` |
| Оповещения о пиках | `core/alerts.py` |
| Хранение в SQLite | `storage/db.py` (WAL) |
| Экспорт CSV/XLSX/PDF/PNG | `reporting/exporters.py` |
| Пакетный режим | `cli/batch_cmd.py` (APScheduler) |
| Полу­автоматический режим | `cli/analyze_cmd.py` + `tui/` |
| 100k точек ≤ 10 с | `tests/test_pipeline_perf.py` ✅ |
| Логирование ошибок | `logging_setup.py` + таблица `stage_logs` |
| Повторный запуск без потери данных | По-стадийная запись результата в БД |

## Известные ограничения

- Шифрование архивов отчётов в MVP не реализовано (см. ТЗ, раздел «Защита информации»).
- Поддержка прямого подключения к IoT-датчикам (MQTT/HTTP) вне области MVP — приложение работает с файлами CSV/JSON, сформированными внешними средствами.
- Веб-фронтенд из Лаб 15 (FastAPI + Jinja/HTMX) не реализуется — заказчик выбрал вариант CLI/TUI.

## Лицензия

Учебный проект. Калининградский Государственный Технический Университет, кафедра цифровых систем и автоматики, 2025.

Исполнители: Коржавин А.Н., Нейенбург Т.А. (группа 25-ВТ/м).
