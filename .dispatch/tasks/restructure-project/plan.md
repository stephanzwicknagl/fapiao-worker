# Restructure Project Layout

- [x] Survey the root directory files and their import relationships to decide on the best subdirectory structure — chosen: `fapiao/` package with `extract.py`, `fill.py`, `web.py`; root shims for gunicorn + CLI
- [x] Move files into the chosen subdirectory layout and update all internal imports accordingly — created fapiao/{__init__,extract,fill,web}.py; root shims app.py/extract_fapiaos.py/fill_excel.py; updated tests and Dockerfile
- [x] Verify the app still works: Flask entry point, CLI scripts, and gunicorn config all resolve correctly — 80/80 tests pass, ruff clean
- [x] Update CLAUDE.md and README.md to reflect the new structure and any changed commands — added project layout section to both; CLI commands unchanged (root shims preserve them)
