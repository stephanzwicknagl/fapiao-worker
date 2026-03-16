# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**fapiao-worker** processes Chinese VAT invoices (发票, fāpiào): it extracts financial data from PDF invoices and fills Excel VAT reimbursement claim forms. It works entirely offline with no AI/API dependencies — pure regex pattern matching on embedded PDF text.

## Development Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Running the App

**Web app (development):**
```bash
FLASK_DEBUG=1 SECRET_KEY=dev .venv/bin/flask run
```

**CLI workflow:**
```bash
# 1. Extract data from PDFs in data/
.venv/bin/python extract_fapiaos.py

# 2. Fill Excel form (two passes required)
.venv/bin/python fill_excel.py 1   # date, number, quantity, category
.venv/bin/python fill_excel.py 2   # amounts and VAT
```

**Docker (production):**
```bash
echo "SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')" > .env
docker compose up -d
# App at http://127.0.0.1:8000
```

**Run tests:**
```bash
.venv/bin/pytest
```

**Run linter:**
```bash
.venv/bin/ruff check .
```

## Project Layout

```
fapiao/           # main package
  extract.py      # PDF extraction logic (importable + CLI via root shim)
  fill.py         # Excel filling logic (importable + CLI via root shim)
  web.py          # Flask web app
app.py            # WSGI shim — re-exports app from fapiao.web for gunicorn (app:app)
extract_fapiaos.py  # CLI shim — delegates to fapiao.extract.main()
fill_excel.py       # CLI shim — delegates to fapiao.fill.main()
gunicorn.conf.py  # gunicorn config (stays in root)
mappings.toml     # seller→category mappings (stays in root)
templates/        # Jinja2 templates for the web app
tests/            # pytest test suite
```

## Architecture

The project has three layers sharing a common processing pipeline:

**CLI tools** (`extract_fapiaos.py`, `fill_excel.py`) — thin root shims that delegate to `fapiao.extract` and `fapiao.fill`. PDFs go in `data/`, outputs are `fapiaos.csv` and a filled Excel file.

**Web app** (`fapiao/web.py`, exposed via root `app.py`) — Flask interface wrapping the same extraction/filling logic. Uses temporary directories with UUID tokens for session state. Key workflow branch: if all sellers in the uploaded PDFs are already in `mappings.toml`, the Excel is filled and returned immediately; if new sellers are found, the user is redirected to `categorize.html` to assign categories before filling.

**Shared modules** — `fapiao/extract.py` and `fapiao/fill.py` are both importable as modules and runnable as CLI scripts.

### PDF Extraction Logic (`fapiao/extract.py`)

The extractor uses 6+ regex strategies per field (amount, VAT, seller name) to handle format variations across fapiao types: Walmart/Sam's Club receipts, e-commerce (Taobao, JD), restaurants, food delivery, hotels, DiDi, metro/Makro wholesale. Pages that fail heuristic checks (airline/train tickets, continuation pages) are skipped. Extraction accuracy is ~90%.

### Excel Filling (`fapiao/fill.py`)

The form has rows 12–51 (max 40 entries). Run 1 writes date (mm/dd/yyyy), fapiao number, quantity (always 1), and category (from `mappings.toml`). Run 2 writes fapiao amount (column I) and VAT amount (column J). Excel formulas in description and VAT rate columns are never touched.

### Seller→Category Mappings (`mappings.toml`)

Maps seller names (名称 from the fapiao) to VAT claim form categories. Supports 60+ categories. The web app appends new mappings here when users categorize unknown sellers — this is additive only, never overwrites existing entries. The CLI tools read this file directly.

## Key Constraints

- Excel form maximum: 40 rows (rows 12–51)
- Web app limits: 50 MB max upload, 100 PDF files max
- `SECRET_KEY` env var is required in production (see `.env.example`)
- The `.env` file is gitignored — never commit it
