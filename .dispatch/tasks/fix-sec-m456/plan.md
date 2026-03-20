# Fix SEC-M.4, M.5, M.6: TOML Writer, CSRF, and Cleanup Race

- [x] Fix 2.4: Replace the hand-rolled `toml_str()`/`_save_new_mappings()` in `fapiao/web.py` with `tomli_w`; add `tomli-w` to `requirements.txt`
- [x] Fix 2.5: Add CSRF protection — install `flask-wtf`, initialise `CSRFProtect(app)` in `fapiao/web.py`, add `{{ csrf_token() }}` to `templates/categorize.html`; FormData(form) in fetch() picks up the hidden input automatically, so no JS changes needed; WTF_CSRF_ENABLED=False added to test fixture
- [x] Fix 2.6: Harden `_cleanup_stale_pending()` in `fapiao/web.py` to use `follow_symlinks=False` in stat, check it is a real directory (not a symlink), and wrap each entry in a try/except instead of `ignore_errors=True`
- [x] Mark tickets 2.4, 2.5, and 2.6 as resolved in `docs/epics/epic-security-medium.md`
