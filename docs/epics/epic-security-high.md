# Epic: Security Hardening – High Findings

**Status:** resolved
**Priority:** HIGH
**Source:** Security Audit, 2026-03-19

## Description

One high-severity finding was identified: the `/categorize` endpoint lacks rate limiting, exposing the server to resource exhaustion attacks via unbounded file I/O and temporary directory creation.

---

## Tickets

### SEC-H.1 – Missing Rate Limit on /categorize Endpoint ✓ RESOLVED

**File:** `fapiao/web.py`
**Finding:** H1 – No rate limiting on `/categorize` POST handler

**Current Code (fapiao/web.py):**
```python
@app.post('/categorize')
def categorize():
    ...
    # No @limiter.limit() decorator
```

**Required Changes:**

1. Add the `@limiter.limit` decorator to `/categorize`, matching the limit already applied to `/process`:

```python
@app.post('/categorize')
@limiter.limit('10 per minute')
def categorize():
    ...
```

2. Consider stricter limits (e.g. `5 per minute`) since each request performs file I/O and spawns openpyxl processing.

---

## Acceptance Criteria

- [x] `POST /categorize` returns HTTP 429 after 10 requests/minute from the same IP
- [x] Rate limit headers (`X-RateLimit-*`) are present in responses
- [x] Legitimate users are not affected under normal usage

**Resolution:** Added `@limiter.limit('10 per minute')` decorator to `/categorize` POST handler in `fapiao/web.py`, matching the limit already applied to `/process`.
