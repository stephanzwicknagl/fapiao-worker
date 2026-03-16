# Epic: Security Hardening – Medium Findings

**Status:** open
**Priority:** MEDIUM
**Source:** Security Audit, 2026-03-13

## Description

Two medium-severity findings represent defense-in-depth gaps: orphaned session data accumulates sensitive financial information on disk, and missing HTTP security headers reduce browser-side protection.

---

## Tickets

### 2.1 – Pending Sessions Have No Expiry / Cleanup

**File:** `app.py`
**Finding:** M1 – Abandoned categorization sessions leave sensitive fapiao data in `/tmp`

**Current Code (app.py:34, 207–212):**
```python
PENDING_DIR = Path(tempfile.gettempdir()) / 'fapiao_pending'

# In /process:
uuid = secrets.token_urlsafe(16)
pending = PENDING_DIR / uuid
pending.mkdir(parents=True, exist_ok=True)
(pending / 'fapiaos.json').write_text(json.dumps(fapiaos), encoding='utf-8')
(pending / 'template.xlsx').write_bytes(template_path.read_bytes())
```

The `pending/` directory is only cleaned up in the `/categorize` `finally` block (app.py:308). If a user navigates away or closes the browser after the categorize page is shown, the files — containing invoice numbers, amounts, and company names — are never deleted.

**Required Changes:**

1. Add a startup cleanup routine that removes pending directories older than a configurable TTL (e.g. 1 hour):
```python
import time

SESSION_TTL_SECONDS = 3600  # 1 hour

def _cleanup_stale_pending() -> None:
    """Remove pending session directories older than SESSION_TTL_SECONDS."""
    if not PENDING_DIR.exists():
        return
    now = time.time()
    for entry in PENDING_DIR.iterdir():
        if entry.is_dir() and (now - entry.stat().st_mtime) > SESSION_TTL_SECONDS:
            shutil.rmtree(entry, ignore_errors=True)
            app.logger.info('Cleaned up stale session: %s', entry.name)
```

2. Call `_cleanup_stale_pending()` at the start of `/process` (or register it as an `@app.before_request` hook with a time-based throttle).

3. Alternatively, store session state in memory (a thread-safe dict) instead of on disk, which avoids any on-disk accumulation.

---

### 2.2 – Missing HTTP Security Headers

**File:** `app.py`
**Finding:** M2 – No `X-Content-Type-Options`, `X-Frame-Options`, `Content-Security-Policy`, or `Referrer-Policy` headers

**Current Code (app.py:20):**
```python
app = Flask(__name__)
app.secret_key = os.environ['SECRET_KEY']
# No after_request hook sets security headers
```

Without these headers, browsers offer no extra protection against MIME-sniffing attacks, clickjacking, or unintended data leakage via the Referer header.

**Required Changes:**

1. Add an `after_request` hook that injects standard security headers:
```python
@app.after_request
def set_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "script-src 'self'; "
        "img-src 'self' data:; "
        "form-action 'self';"
    )
    return response
```

2. Verify with `curl -I http://localhost:8000/` that all four headers are present after the fix.

---

## Acceptance Criteria

- [ ] No `fapiao_pending/` subdirectory older than 1 hour exists after the cleanup runs
- [ ] `curl -I http://localhost:8000/` response includes `X-Content-Type-Options: nosniff`
- [ ] `curl -I http://localhost:8000/` response includes `X-Frame-Options: DENY`
- [ ] `curl -I http://localhost:8000/` response includes a `Content-Security-Policy` header
- [ ] `curl -I http://localhost:8000/` response includes `Referrer-Policy: no-referrer`
