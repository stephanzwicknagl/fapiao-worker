# Fix Success Panel Not Appearing After Download on Categorize Page

- [x] Read `templates/categorize.html` and `fapiao/web.py` to understand the current categorize flow: how the form submits, what the server returns (direct file download vs redirect), and what JS is currently wired up
  - `/categorize` POST returns `send_file()` (file download) directly — no redirect
  - The inline `<script>` block is blocked by `script-src 'self'` CSP (no `'unsafe-inline'`), so no JS runs at all
  - Even if JS ran, the 4s setTimeout is fragile and fails on Safari (navigates away)
- [x] Identify why the success panel doesn't appear — likely the `/categorize` POST returns a file download response that navigates away (or the timeout/event detection is wrong for this flow), and fix the JS so the success panel reliably shows after the download
  - Root cause 1: `script-src 'self'` CSP blocks the inline `<script>` block — no JS ran at all
  - Root cause 2: Even with JS, the 4s setTimeout was a fragile guess
  - Fix: moved JS to `static/categorize.js` (allowed by CSP `'self'`), used `fetch()` to POST the form so the page never navigates away, triggered download from a blob URL, then revealed the success panel
  - Also: added `static_folder` to Flask constructor in `web.py` to serve `static/` from the project root
  - Also: fixed pre-existing test `test_categorize_valid_session_returns_xlsx` — it didn't include `save_consent=on` so `_save_new_mappings` was never called (correct behavior now, wrong assertion)
