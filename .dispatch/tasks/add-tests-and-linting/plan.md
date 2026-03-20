# Add Test Suite and Linting Configuration

- [x] Survey the codebase: read extract_fapiaos.py, fill_excel.py, and app.py to understand what's testable
- [x] Configure ruff for linting (pyproject.toml) and fix any existing lint issues
- [x] Write pytest tests for extract_fapiaos.py — focus on the regex extraction helpers and edge cases (34 tests)
- [x] Write pytest tests for fill_excel.py — cover the two-pass filling logic and mappings lookup (21 tests)
- [x] Write pytest tests for app.py Flask routes — upload flow, categorization flow, error cases (25 tests)
- [x] Add pytest and ruff to requirements.txt (or a new requirements-dev.txt)
- [x] Update CLAUDE.md with commands to run tests and linter
