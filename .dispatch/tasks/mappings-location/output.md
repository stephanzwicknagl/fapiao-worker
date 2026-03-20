# mappings.toml Location Decision

## Decision: Keep in project root (no move)

### Reasoning

Three options were evaluated:

| Location | Verdict |
|----------|---------|
| Project root (current) | **Chosen** |
| `fapiao/` (package dir) | Rejected |
| `config/` or `data/` folder | Rejected |

**Why not `fapiao/`:** The web app writes new entries to `mappings.toml` at runtime via `_save_new_mappings` in `web.py`. Runtime-mutable state does not belong inside a Python package directory — packages should contain code and static resources, not files that are modified by running the application.

**Why not a separate `config/` or `data/` folder:** Adds a new directory solely for one file. The project is small and adding structural complexity is not justified.

**Why root:** `mappings.toml` is project-level configuration, parallel to `gunicorn.conf.py` which also lives in root. It is easily discoverable, easily edited by hand, and CLAUDE.md already documents it as staying there. The existing path resolution (`Path(__file__).parent.parent / 'mappings.toml'` in both `fill.py` and `web.py`) is correct and clear.

### Changes made

None. The file stays where it is and all references are already correct.

### Test results

80 passed, 0 failed (`pytest`).
