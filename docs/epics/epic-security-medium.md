# Epic: Security Hardening – Medium Findings

**Status:** open
**Priority:** MEDIUM
**Source:** Security Audit, 2026-03-13
**Re-evaluated:** 2026-03-19

## Description

Previous medium findings (M1 session cleanup, M2 security headers) were resolved in the package restructure commit. Four new medium findings were added in the 2026-03-19 review: MIME type validation gaps, unsafe TOML serialization, missing CSRF protection, and a TOCTOU race in cleanup.

---

## Tickets

### 2.1 – Pending Sessions Have No Expiry / Cleanup ✓ RESOLVED

**File:** `fapiao/web.py`
**Finding:** M1 – Abandoned categorization sessions leave sensitive fapiao data in `/tmp`

**Resolution:** `SESSION_TTL_SECONDS = 3600` and `_cleanup_stale_pending()` were added in commit `3a74946`. The cleanup runs at the start of each `/process` request, removing any pending directory older than 1 hour.

**Acceptance Criteria:**
- [x] No `fapiao_pending/` subdirectory older than 1 hour exists after the cleanup runs

---

### 2.2 – Missing HTTP Security Headers ✓ RESOLVED

**File:** `fapiao/web.py`
**Finding:** M2 – No `X-Content-Type-Options`, `X-Frame-Options`, `Content-Security-Policy`, or `Referrer-Policy` headers

**Resolution:** An `@app.after_request` hook was added in commit `3a74946`, injecting `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, and a strict `Content-Security-Policy` on all responses.

**Acceptance Criteria:**
- [x] `curl -I http://localhost:8000/` response includes `X-Content-Type-Options: nosniff`
- [x] `curl -I http://localhost:8000/` response includes `X-Frame-Options: DENY`
- [x] `curl -I http://localhost:8000/` response includes a `Content-Security-Policy` header
- [x] `curl -I http://localhost:8000/` response includes `Referrer-Policy: no-referrer`

---

### 2.3 – Overly Permissive MIME Type Validation ✓ RESOLVED

**File:** `fapiao/web.py`
**Finding:** M3 – MIME allowlist includes `application/zip` and `application/octet-stream`; `None` MIME bypasses the check entirely

**Re-evaluation (2026-03-19):** New finding.

**Resolution:** Removed `application/zip` and `application/octet-stream` from the XLSX allowlist (now `{XLSX_MIME}` only). Added `_check_magic()` helper that reads the first bytes of the stream and seeks back. Applied unconditionally to all PDF uploads (`%PDF`) and the XLSX upload (`PK\x03\x04`) — magic byte checks are not gated on `f.mimetype`, so a `None` MIME can no longer bypass file-content validation.

**Current Code (fapiao/web.py, ~line 192):**
```python
pdf_mimes = {'application/pdf', 'application/x-pdf'}
xlsx_mimes = {XLSX_MIME, 'application/zip', 'application/octet-stream'}
for f in pdf_files:
    if f.mimetype and f.mimetype not in pdf_mimes:
        return render_template('index.html', error=...)
if excel_file.mimetype and excel_file.mimetype not in xlsx_mimes:
    return render_template('index.html', error=...)
```

**Required Changes:**

1. Remove overly broad MIME types from the XLSX allowlist:
```python
xlsx_mimes = {XLSX_MIME}
```

2. Add magic byte validation as a second layer:
```python
def _check_magic(file_obj, expected: bytes) -> bool:
    file_obj.seek(0)
    magic = file_obj.read(len(expected))
    file_obj.seek(0)
    return magic == expected

# In process():
for f in pdf_files:
    if not _check_magic(f.stream, b'%PDF'):
        return render_template('index.html', error=f'{f.filename!r} is not a valid PDF.')
if not _check_magic(excel_file.stream, b'PK\x03\x04'):
    return render_template('index.html', error='The Excel file is not a valid .xlsx.')
```

3. Remove the `if f.mimetype and ...` guard to prevent `None` bypass.

---

### 2.4 – Hand-Rolled TOML Writer Missing Control Character Escaping ✓ RESOLVED

**File:** `fapiao/web.py`
**Finding:** M4 – Custom TOML serialization skips control characters, risking malformed `mappings.toml`

**Re-evaluation (2026-03-19):** New finding.

**Current Code (fapiao/web.py, ~line 137):**
```python
def toml_str(s):
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'
lines.append(f'{toml_str(seller)} = {toml_str(category)}\n')
```

**Required Changes:**

1. Add `tomli-w` to `requirements.txt`:
```
tomli-w>=1.0
```

2. Replace hand-rolled writer with the library:
```python
import tomli_w

def _save_new_mappings(new_mappings: dict[str, str]) -> None:
    with open(_MAPPINGS_FILE, 'rb') as f:
        data = tomllib.load(f)
    mappings = data.get('mappings', {})
    mappings.update(new_mappings)
    data['mappings'] = mappings
    with open(_MAPPINGS_FILE, 'wb') as f:
        tomli_w.dump(data, f)
```

---

### 2.5 – No CSRF Protection on Forms ✓ RESOLVED

**File:** `templates/categorize.html`, `static/categorize.js`
**Finding:** M5 – POST forms submit without CSRF tokens; forged cross-site requests are possible

**Re-evaluation (2026-03-19):** New finding.

**Current Code (templates/categorize.html, ~line 53):**
```html
<form method="POST" action="/categorize">
  <input type="hidden" name="uuid" value="{{ uuid }}">
  <!-- No CSRF token -->
```

**Required Changes:**

1. Add `flask-wtf` to `requirements.txt`.
2. Initialise CSRF in `web.py`: `csrf = CSRFProtect(app)`
3. Add token to form: `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">`
4. Include `X-CSRFToken` header in the `fetch()` call in `static/categorize.js`.

---

### 2.6 – TOCTOU Race Condition in Temporary Directory Cleanup ✓ RESOLVED

**File:** `fapiao/web.py`
**Finding:** M6 – `_cleanup_stale_pending()` has check-then-act race; `shutil.rmtree` follows symlinks

**Re-evaluation (2026-03-19):** New finding (introduced by the fix for M1).

**Current Code (fapiao/web.py, ~line 47):**
```python
def _cleanup_stale_pending() -> None:
    if not PENDING_DIR.exists():
        return
    now = time.time()
    for entry in PENDING_DIR.iterdir():
        if entry.is_dir() and (now - entry.stat().st_mtime) > SESSION_TTL_SECONDS:
            shutil.rmtree(entry, ignore_errors=True)
```

**Required Changes:**
```python
def _cleanup_stale_pending() -> None:
    if not PENDING_DIR.exists():
        return
    now = time.time()
    try:
        for entry in PENDING_DIR.iterdir():
            try:
                stat = entry.stat(follow_symlinks=False)
                if stat.st_mode & 0o170000 == 0o040000:  # real dir, not symlink
                    if (now - stat.st_mtime) > SESSION_TTL_SECONDS:
                        shutil.rmtree(entry)
            except (OSError, FileNotFoundError):
                continue
    except (OSError, FileNotFoundError):
        pass
```

---

## Acceptance Criteria

- [x] 2.1: No `fapiao_pending/` subdirectory older than 1 hour exists after the cleanup runs
- [x] 2.2: Security headers present on all responses
- [x] 2.3: Uploading a ZIP renamed to `.xlsx` is rejected at the MIME/magic-byte check
- [x] 2.3: Files with `None` MIME type are validated via magic bytes only
- [x] 2.4: `mappings.toml` contains valid TOML after writing a seller name with control characters
- [x] 2.5: POST to `/categorize` without a valid CSRF token returns HTTP 400
- [x] 2.6: Cleanup function handles directories deleted mid-iteration without crashing
