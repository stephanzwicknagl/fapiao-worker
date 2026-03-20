# Demote CLI — README and Entry Points

- [x] Rewrite README.md: make the web app the primary workflow at the top; move the CLI step-by-step workflow to a later "Advanced / CLI usage" section
- [x] Consolidate extract_fapiaos.py and fill_excel.py into a single fapiao/cli.py module, then delete both root shims
- [x] Update any references to the removed files (Dockerfile, tests, CLAUDE.md, project layout section in README)
  - Dockerfile: no changes needed (never copied the shim files)
  - Tests: no changes needed (imported from fapiao.extract / fapiao.fill directly)
  - CLAUDE.md: updated CLI workflow commands and project layout
  - README: updated project layout table and CLI command examples
  - fapiao/fill.py: updated error message referencing extract_fapiaos.py
