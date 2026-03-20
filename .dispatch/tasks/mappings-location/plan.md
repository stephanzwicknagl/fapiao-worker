# Decide and Move mappings.toml Location

- [x] Read all files that reference `mappings.toml` (web.py, fill.py, cli.py, any tests) to understand how the path is resolved — both fill.py:32 and web.py:72 use `Path(__file__).parent.parent / 'mappings.toml'` (→ project root); tests monkeypatch `_MAPPINGS_FILE` directly so they are path-agnostic
- [x] Decide: root (stay), `fapiao/` (alongside the package), or `data/` (separate config folder) — **Decision: keep in root.** mappings.toml is runtime-mutable (web app writes new entries via _save_new_mappings), making it inappropriate for a Python package directory. Root is the right level — it sits alongside other project-level config (gunicorn.conf.py) and CLAUDE.md explicitly documents it as staying there.
- [x] Move `mappings.toml` to the chosen location and update every path reference so mappings are applied correctly — no move needed; decision is to keep in root, all path references are already correct
- [x] Run the test suite (`pytest`) to confirm nothing is broken — 80 passed, 0 failed
- [x] Write a short summary of the decision and changes to `.dispatch/tasks/mappings-location/output.md`
