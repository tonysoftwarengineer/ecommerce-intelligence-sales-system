# Ecommerce Intelligence Sales System

A sales analytics pipeline over the [Olist Brazilian E-Commerce dataset](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) (2016–2018). Ingests 9 relational CSVs, cleans and joins them, and computes revenue analytics — with a console report and a matplotlib dashboard.

Currency throughout is Brazilian Real (`R$`), not USD — Olist is a Brazilian marketplace.

## What it does

- **Ingest → Clean → Join → Analyze → Report/Visualize**, one function per stage.
- Auto-skips re-downloading via `kagglehub` if `data/` is already populated.
- Computes: total revenue, revenue by month, average order value, top categories by revenue, top customers by spend, revenue by state.
- Validates joins (raises a clear error on duplicate join keys or unexpected row-count changes) rather than silently producing wrong numbers.

## Architecture

```
ingest()  ->  clean_all()  ->  join_all()  ->  run_analysis()  ->  generate_report() / generate_dashboard()
```

| Module | Responsibility |
|---|---|
| `config.py` | Path/filename/dataset constants (single source of truth) |
| `src/ingest.py` | Downloads (via kagglehub) and loads the 9 raw CSVs |
| `src/stages/clean.py` | Per-table cleaning (dates, status filtering, missing values) |
| `src/stages/join.py` | Merges tables into one analysis-ready DataFrame, with validation |
| `src/stages/analyze.py` | The six business-question functions |
| `src/stages/report.py` | Console report formatting (currency, state names, category labels) |
| `src/stages/visualize.py` | Matplotlib dashboard (2×2 chart grid) |
| `src/pipeline.py` | Wires the stages together (`run_pipeline()`) |

## Setup

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

Requires [Kaggle API credentials](https://www.kaggle.com/docs/api) (`~/.kaggle/kaggle.json`) — `kagglehub` uses these to download the dataset on first run. `data/` is gitignored; it's populated automatically.

## Usage

```bash
python3 -m main
```

Prints the full console report. For the interactive dashboard:

```bash
python3 -m src.stages.visualize
```

## Dashboard

![Dashboard](docs/dashboard-screenshot.png)

*(screenshot pending)*

## Project structure

```
config.py
main.py
src/
├── ingest.py
├── pipeline.py
└── stages/
    ├── clean.py
    ├── join.py
    ├── analyze.py
    ├── report.py
    └── visualize.py
tests/
```

## Running tests

```bash
pytest -q
```

## Roadmap

- **V3** — Revenue forecasting + RFM customer segmentation
- **V4** — FastAPI backend
- **V5** — React/TypeScript dashboard

## Data & license

Dataset: ["Brazilian E-Commerce Public Dataset by Olist"](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) on Kaggle. See the Kaggle page for license terms.
