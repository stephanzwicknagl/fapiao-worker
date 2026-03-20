# Fix Security – Medium Findings

- [x] Add `_cleanup_stale_pending()` to app.py and call it at the start of `/process`
- [x] Add `set_security_headers` after_request hook to app.py with the four required headers
- [x] Verify acceptance criteria from the epic are met — cleanup called at top of /process; all four headers present in after_request hook
