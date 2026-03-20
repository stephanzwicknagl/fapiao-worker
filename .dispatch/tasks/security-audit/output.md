# Security Audit Report — fapiao-worker

**Audited:** 2026-03-16
**Scope:** fapiao/ package (extract.py, fill.py, web.py), root shims, templates, Dockerfile, gunicorn.conf.py, requirements.txt
**Method:** Static code review + pip-audit

---

## HIGH

### H1 — Dockerfile runs as root
**File:** `Dockerfile` (entire file)
**Description:** The Dockerfile has no `USER` directive and does not create an unprivileged user. All container processes (including gunicorn workers handling untrusted uploads) run as UID 0. The task context states "Docker now runs as non-root appuser" but this has **not** been applied — no `adduser`/`RUN useradd` and no `USER` instruction exist.
**Recommendation:**
```dockerfile
RUN adduser --disabled-password --gecos '' appuser
USER appuser
```
Add these lines before the `CMD` instruction. Ensure PENDING_DIR and any runtime paths are writable by the new user.

---

## MEDIUM

### M1 — Rate limiter state is per-worker; effective limit is 2× configured
**File:** `fapiao/web.py:26`
**Description:** `storage_uri='memory://'` stores rate-limit counters in each worker's process memory. With `workers = 2` (gunicorn.conf.py:2), a single client can make 10 req/min to worker A and 10 req/min to worker B simultaneously — effectively 20/min against `/process`. Under higher worker counts, the protection degrades proportionally.
**Recommendation:** Use a shared backend. Redis is the standard choice:
```python
limiter = Limiter(get_remote_address, app=app, default_limits=[], storage_uri='redis://localhost:6379')
```
Alternatively, use `storage_uri='memcached://...'`. If adding an external dependency is undesirable, document the effective rate (workers × configured limit) and reduce the configured value accordingly.

### M2 — `/categorize` endpoint has no rate limiting
**File:** `fapiao/web.py:294`
**Description:** Only `/process` has a `@limiter.limit('10 per minute')` decorator. `/categorize` is unrestricted. An attacker who obtains a valid UUID token (128-bit, but see M3) can spam this endpoint without restriction, causing repeated writes to `mappings.toml` and consuming server resources.
**Recommendation:** Apply the same or a stricter rate limit to `/categorize`:
```python
@app.post('/categorize')
@limiter.limit('10 per minute')
def categorize():
```

### M3 — Seller names in `/categorize` come from the form body, not the saved session
**File:** `fapiao/web.py:308–313`
**Description:**
```python
seller = request.form[f'seller_{i}']
cat = request.form.get(f'cat_{i}', '').strip()
new_mappings[seller] = cat
_save_new_mappings(new_mappings)
```
Seller names and categories come **entirely from the POST body** and are not cross-referenced against the `fapiaos.json` saved in the pending session directory. Anyone holding a valid UUID (including the legitimate user but also anyone who has obtained the UUID) can inject arbitrary seller→category pairs into `mappings.toml` — including sellers that were never in the uploaded PDFs. The 128-bit UUID token provides strong capability control, but the injection is unbounded once the token is known.
**Recommendation:** Load the canonical seller list from `pending/fapiaos.json` and reject any `seller_N` value not present in that list:
```python
fapiaos = json.loads((pending / 'fapiaos.json').read_text(encoding='utf-8'))
valid_sellers = {row.get('seller') for row in fapiaos if row.get('seller')}
# then: if seller not in valid_sellers: continue
```

### M4 — Category values not validated against the allowed list
**File:** `fapiao/web.py:311`
**Description:** `cat = request.form.get(f'cat_{i}', '').strip()` accepts any string. The HTML `<select>` element limits the UI to predefined values, but a direct POST bypasses this entirely. Arbitrary category strings can be persisted to `mappings.toml`. Combined with M5 (control character escaping), this can also corrupt the TOML file.
**Recommendation:** Validate `cat` against the `CATEGORIES` list server-side before saving:
```python
if cat not in CATEGORIES:
    continue  # or return an error
```

### M5 — `toml_str()` does not escape newlines and other control characters
**File:** `fapiao/web.py:133–135`
**Description:**
```python
def toml_str(s):
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'
```
This escapes backslashes and double-quotes, but not newlines (`\n`), carriage returns (`\r`), tabs (`\t`), or null bytes. PDF-extracted seller names can legitimately contain newlines (multi-line text blocks from `fitz.get_text()`). A seller name with an embedded newline would produce a broken TOML key spanning multiple lines, making `mappings.toml` unparseable and taking down the mapping system entirely on the next request. This is also exploitable via M3.
**Recommendation:** Escape the full set of TOML control characters:
```python
def toml_str(s):
    s = s.replace('\\', '\\\\').replace('"', '\\"')
    s = s.replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
    s = s.replace('\x00', '')  # drop null bytes
    return '"' + s + '"'
```
Or use a proper TOML serialization library (e.g., `tomli-w`).

### M6 — No server-side file content validation (magic bytes)
**File:** `fapiao/web.py:188–195`
**Description:** The code correctly notes that MIME type from the browser is "defence-in-depth only." However, there is no server-side magic byte check to confirm that a file claiming to be a PDF begins with `%PDF`, or that the Excel file is a valid ZIP/OOXML structure. A malformed or adversarial file with a `.pdf` extension will be passed directly to PyMuPDF (`fitz.open()`). PyMuPDF is a large C library with occasional CVEs from processing malformed PDFs; reducing the attack surface here is worthwhile.
**Recommendation:** Read the first 4–8 bytes before saving to disk:
```python
header = f.stream.read(4)
f.stream.seek(0)
if header[:4] != b'%PDF':
    return render_template('index.html', error=f'{f.filename!r} is not a valid PDF.')
```

---

## LOW

### L1 — Pending session files in world-readable `/tmp` (non-Docker deployments)
**File:** `fapiao/web.py:39`
**Description:** `PENDING_DIR = Path(tempfile.gettempdir()) / 'fapiao_pending'`. On Linux, `/tmp` is typically mode 1777 (sticky bit), so subdirectories are user-readable. If the app runs on a shared host (not Docker), other local users could read `fapiaos.json` (which contains fapiao numbers, dates, amounts, seller names — financial PII) and the uploaded Excel templates.
**Recommendation:** Use `tempfile.mkdtemp()` for the pending root itself (creates a mode-0700 directory), or explicitly call `os.chmod(PENDING_DIR, 0o700)` after creation. This is already done for individual processing temp dirs (`tmpdir = Path(tempfile.mkdtemp())`), but PENDING_DIR is created with default permissions via `mkdir(parents=True, exist_ok=True)`.

### L2 — `.env` placeholder value is accepted at runtime
**File:** `.env:4`
**Description:** The `.env` file currently contains `SECRET_KEY=replace-with-a-random-secret`. While the app crashes with a `KeyError` if `SECRET_KEY` is absent (good), it silently accepts a placeholder string. Flask uses the secret key to sign session cookies (though this app does not currently use `flask.session`). If the app is ever extended to use sessions, or if the deployment operator overlooks the placeholder, the secret key will be predictable.
**Recommendation:** Add a startup check that rejects obviously-placeholder values:
```python
secret = os.environ['SECRET_KEY']
if secret in ('', 'replace-with-a-random-secret', 'dev', 'secret', 'changeme'):
    raise RuntimeError('SECRET_KEY is set to a placeholder — generate a real key')
app.secret_key = secret
```

### L3 — `_cleanup_stale_pending` runs synchronously on every `/process` request
**File:** `fapiao/web.py:167`
**Description:** Every `/process` call iterates all entries in `PENDING_DIR` synchronously. With a large number of accumulated pending sessions (e.g., after a high-traffic period), this directory scan delays the response for legitimate users and could be triggered in a loop by spamming `/process`. This is a minor application-layer DoS amplifier.
**Recommendation:** Run cleanup in a background thread, or rate-gate it:
```python
import threading
threading.Thread(target=_cleanup_stale_pending, daemon=True).start()
```
Or only run cleanup on 1-in-N requests: `if random.random() < 0.1: _cleanup_stale_pending()`.

### L4 — `mappings.toml` not included in Docker image — ephemeral
**File:** `Dockerfile`
**Description:** `mappings.toml` is not copied into the image. Seller→category mappings saved via `/categorize` are written to `/app/mappings.toml` inside the container at runtime but are lost when the container restarts. This is not a security vulnerability but means the "save mappings for future use" feature is silently non-functional in the default Docker deployment.
**Recommendation:** Mount a persistent volume:
```yaml
# docker-compose.yml
volumes:
  - ./mappings.toml:/app/mappings.toml
```
And document this requirement.

---

## INFO (verified as correctly implemented)

### I1 — HTTP security headers: correctly applied ✓
**File:** `fapiao/web.py:149–161`
`X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, and a restrictive `Content-Security-Policy` (with `unsafe-inline` limited to `style-src`) are set on every response via `@app.after_request`. The `form-action 'self'` directive also provides partial CSRF protection.

### I2 — Session token entropy: adequate ✓
**File:** `fapiao/web.py:240`
`secrets.token_urlsafe(16)` produces 128 bits of cryptographic randomness. Brute-forcing within a 1-hour TTL window is not feasible.

### I3 — UUID allowlist validation in `/categorize`: correct ✓
**File:** `fapiao/web.py:298`
The character allowlist `[A-Za-z0-9\-_]` correctly matches the base64url alphabet used by `token_urlsafe`. Path traversal via the UUID is not possible.

### I4 — Filename sanitization: applied ✓
**File:** `fapiao/web.py:203`
`secure_filename()` from Werkzeug strips path components and unsafe characters before writing uploaded PDFs to disk.

### I5 — No shell injection risk ✓
No `subprocess`, `os.system`, or `os.popen` calls anywhere in the codebase. File paths are passed to Python library functions (PyMuPDF, openpyxl) as objects, not shell strings.

### I6 — Stale session cleanup: correctly implemented ✓
**File:** `fapiao/web.py:43–51`
Sessions older than `SESSION_TTL_SECONDS` (3600 s) are removed. `shutil.rmtree(entry, ignore_errors=True)` handles race conditions safely.

### I7 — Dependency audit: no known CVEs ✓
`pip-audit -r requirements.txt` returned "No known vulnerabilities found" against all pinned dependencies (Flask 3.1.3, Werkzeug 3.1.6, PyMuPDF 1.27.1, openpyxl 3.1.5, gunicorn 25.1.0, flask-limiter 3.9.0).

### I8 — Financial data logged to stdout
**File:** `fapiao/extract.py:269–275`, `fapiao/fill.py:83,97`
`print()` statements emit fapiao numbers, dates, and amounts to stdout. In Docker these flow into `docker logs` / the gunicorn access log. This is informational: the data is not written to persistent storage, but operators should be aware that log retention policies apply to financial PII.

---

## Summary Table

| ID | Severity | Title |
|----|----------|-------|
| H1 | HIGH | Dockerfile runs as root — no USER directive |
| M1 | MEDIUM | Rate limiter per-worker; effective limit 2× with 2 workers |
| M2 | MEDIUM | `/categorize` has no rate limiting |
| M3 | MEDIUM | Seller names in `/categorize` from form body, not session |
| M4 | MEDIUM | Category values not validated against allowed list |
| M5 | MEDIUM | `toml_str()` missing control character escaping |
| M6 | MEDIUM | No server-side magic byte validation for uploaded PDFs |
| L1 | LOW | Pending session dir world-readable in non-Docker deployments |
| L2 | LOW | Placeholder SECRET_KEY silently accepted at runtime |
| L3 | LOW | `_cleanup_stale_pending` synchronous on every /process request |
| L4 | LOW | `mappings.toml` not in Docker image — ephemeral |
| I1–I8 | INFO | Confirmed-correct controls (see above) |
