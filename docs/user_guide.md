# Руководство пользователя АИС ThermoFFT

## Назначение

Анализ суточных колебаний температуры микроклимата помещений: импорт логов из CSV/JSON, спектральный анализ (FFT), метрики (амплитуда, затухание, корреляция, лаг, out-of-range), прогноз температуры, формирование отчётов и оповещений.

## Установка

```bash
# Linux/macOS
python -m venv .venv && source .venv/bin/activate
# Windows
python -m venv .venv && .venv\Scripts\activate

pip install -e .
thermofft init-db
```

## Формат входных данных

CSV или JSON с обязательными колонками:

| Колонка | Тип | Описание |
|---|---|---|
| `noted_date` | datetime | метка времени, ISO или `DD.MM.YYYY HH:MM` |
| `temp` | float | температура, °C |
| `out/in` | string | `"in"` (помещение) или `"out"` (улица) |

JSON может быть либо списком объектов, либо `{"records": [...]}`.

## Базовый сценарий (CLI)

```bash
# 1) Сгенерировать тестовый датасет (7 суток, шаг 60с)
python data/samples/generate.py --out data/samples/sample.csv --days 7 --step 60

# 2) Прогнать анализ — pipeline пишет в SQLite и в runs/
thermofft analyze data/samples/sample.csv --out-dir runs

# 3) Посмотреть историю прогонов
thermofft history --limit 10

# 4) Детали по конкретному прогону
thermofft show <run_uid>
```

После `analyze` создаётся каталог `runs/<timestamp>_<uid>/` с графиками, таблицами, PDF-отчётом и `experiment_meta.json`.

## Интерактивный режим (TUI)

```bash
thermofft tui
```

- На главном экране ввести путь к файлу, при необходимости поправить параметры.
- `r` — Run; `h` — открыть историю; `q` — выйти.
- Экран Progress отображает live-лог стадий pipeline.
- Экран Results: вкладки Metrics / Spectrum / Alerts / Interpretation / Artifacts; клавиша `p` — открыть папку графиков, `e` — открыть PDF.

## Пакетный режим

```bash
thermofft batch data/samples --interval 300
```
Сканирует папку каждые 5 минут, прогоняет новые `*.csv` / `*.json`. `--once` — один проход и выход.

## Параметры (config)

Полный список — `thermofft analyze --help`. Ключевые:

- `--resample 15min` — частота передискретизации (1s..1h)
- `--max-gap 15min` — лимит интерполяции (большие разрывы помечаются как недостоверные)
- `--forecast-model expsmooth|sarima|naive`
- `--horizon 24h` — горизонт прогноза
- `--oor-low 18 --oor-high 27` — границы коридора температуры
- `--anomaly-rate 1.5` — порог `|ΔT/Δh|` для события
- `--threshold-attenuation 0.7` — порог затухания для алерта

## Интерпретация результатов

- **Attenuation (robust)** = (Q95-Q05)_in / (Q95-Q05)_out. Чем ближе к 0 — тем лучше изоляция помещения.
- **Pearson(T_in, T_out)** — насколько внутренняя температура отслеживает внешнюю.
- **lag_hours** — фазовый сдвиг (положительный — внутренний ряд отстаёт от внешнего).
- **Out-of-range %** — доля точек T_in вне коридора.
- **Спектральные пики** — основные периоды (часы), 24ч пик ≈ суточный цикл.

## Тестирование

```bash
pip install -e ".[dev]"
pytest tests/                # все тесты
pytest tests/ -m "not perf"  # без perf-gate
```

## Резервное копирование

Папка `runs/` + файл `thermofft.db` — самодостаточный комплект. Достаточно копировать раз в неделю.

## Возможные ошибки

| Сообщение | Причина | Решение |
|---|---|---|
| `Missing required columns` | нет одной из обязательных колонок | проверить заголовок CSV/JSON |
| `Unsupported file extension` | расширение не `.csv` / `.json` | конвертировать или переименовать |
| `After validation no rows remain` | все строки невалидны | проверить формат `noted_date`, типы `temp`, значения `out/in` |
| `After alignment in/out series have no overlap` | in и out не пересекаются по времени | проверить временные диапазоны датчиков |
| `Series too short for expsmooth` (warning) | мало данных для модели | передать `--forecast-model naive` или загрузить больше истории |
