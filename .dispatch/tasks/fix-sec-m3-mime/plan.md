# Fix SEC-M.3: Tighten MIME Type Validation with Magic Byte Checks

- [x] Read `fapiao/web.py` to understand the current upload validation flow
- [x] Remove `'application/zip'` and `'application/octet-stream'` from the XLSX MIME allowlist; add a `_check_magic()` helper that validates file signatures (PDF: `%PDF`, XLSX: `PK\x03\x04`); apply it to both PDF and XLSX uploads; ensure `None` MIME type no longer bypasses the check
- [x] Mark ticket 2.3 as resolved in `docs/epics/epic-security-medium.md`
