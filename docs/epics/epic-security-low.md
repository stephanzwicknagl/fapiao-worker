# Epic: Security Hardening – Low Findings

**Status:** open
**Priority:** LOW
**Source:** Security Audit, 2026-03-13
**Re-evaluated:** 2026-03-19

## Description

L2 (rate limiting on `/process`) was resolved in the package restructure. L1 (Docker root user) and L3 (no CI/CD) remain open. Five new low-severity findings were added in the 2026-03-19 review.

---

## Tickets

### 3.1 – Docker Container Runs as Root

**File:** `Dockerfile`
**Finding:** L1 – No `USER` directive; application runs as root inside the container

**Current Code (Dockerfile):**
```dockerfile
FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py gunicorn.conf.py ./
COPY fapiao/ fapiao/
COPY templates/ templates/
ENV PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["gunicorn", "--config", "gunicorn.conf.py", "app:app"]
```

No `USER` instruction is present. Any vulnerability exploited inside the container runs with root-level OS access.

**Required Changes:**

```dockerfile
# Add before CMD:
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser
USER appuser
```

---

### 3.2 – No Application-Level Rate Limiting on /process ✓ RESOLVED

**File:** `fapiao/web.py`
**Finding:** L2 – The `/process` endpoint performed expensive PDF merging with no request throttling

**Resolution:** `flask-limiter` was added and `/process` decorated with `@limiter.limit('10 per minute')` in commit `3a74946`.

**Acceptance Criteria:**
- [x] `/process` returns HTTP 429 after 10 requests per minute from the same IP

---

### 3.3 – No CI/CD Pipeline for Automated Security Scanning

**File:** N/A (infrastructure gap)
**Finding:** L3 – No `.github/workflows/` or equivalent; no automated dependency or SAST scanning

**Required Changes:**

Create `.github/workflows/security.yml`:
```yaml
name: Security Scan
on: [push, pull_request]
jobs:
  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.13'
      - run: pip install pip-audit bandit
      - run: pip-audit -r requirements.txt
      - run: bandit -r fapiao/ -ll
```

---

### 3.4 – SESSION_COOKIE_SAMESITE Not Explicitly Configured

**File:** `fapiao/web.py`
**Finding:** L4 – Flask session cookie `SameSite` attribute relies on Flask defaults; should be explicit

**Re-evaluation (2026-03-19):** New finding.

**Required Changes:**
```python
app.config['SESSION_COOKIE_SAMESITE'] = 'Strict'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SECURE'] = True  # Only in production (behind HTTPS)
```

---

### 3.5 – `unsafe-inline` for Styles in Content-Security-Policy

**File:** `fapiao/web.py`
**Finding:** L5 – CSP `style-src` permits `'unsafe-inline'`, weakening XSS protection

**Re-evaluation (2026-03-19):** New finding.

**Current Code:**
```python
"style-src 'self' 'unsafe-inline' https://unpkg.com; "
```

**Required Changes:**
Replace inline styles in templates with a stylesheet, then remove `'unsafe-inline'`:
```python
"style-src 'self' https://unpkg.com; "
```

---

### 3.6 – Full Exception Tracebacks Logged in All Environments

**File:** `fapiao/web.py`
**Finding:** L6 – `app.logger.exception()` emits full tracebacks regardless of `DEBUG` mode

**Re-evaluation (2026-03-19):** New finding.

**Required Changes:**
```python
if app.debug:
    app.logger.exception('Failed to open Excel template')
else:
    app.logger.error('Failed to open Excel template — likely invalid file')
```

---

### 3.7 – No Bounds Checking on Parsed Invoice Amounts ✓ RESOLVED

**File:** `fapiao/extract.py`
**Finding:** L7 – Parsed currency amounts are not validated for reasonable magnitude

**Resolution:** Bounds check added before storing `amount` and `vat_amount` in `parse_fapiao()`: any value ≤ 0 or > 1,000,000 is set to `None` and skipped.

---

### 3.8 – No Length Limit on Extracted Seller Names ✓ RESOLVED

**File:** `fapiao/extract.py`
**Finding:** L8 – Seller name extraction has no maximum length; excessively long strings can propagate to TOML and Excel

**Resolution:** Length check (`> 255`) added in `_extract_seller()` before the `_BUYER_NAMES` exclusion check in both pattern 1 and pattern 2.

---

## Acceptance Criteria

- [ ] 3.1: `docker run --rm fapiao-worker id` returns a non-root user
- [x] 3.2: `/process` returns HTTP 429 after 10 requests/minute
- [ ] 3.3: CI pipeline runs and passes on every push to `main`
- [ ] 3.4: Session cookie includes `SameSite=Strict` attribute
- [ ] 3.5: CSP header contains no `unsafe-inline` for `style-src`
- [ ] 3.6: No stack traces in production logs for known-bad input
- [x] 3.7: Amounts > 1,000,000 CNY are skipped during extraction
- [x] 3.8: Seller names longer than 255 chars are discarded
