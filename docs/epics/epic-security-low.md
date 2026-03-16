# Epic: Security Hardening – Low Findings

**Status:** open
**Priority:** LOW
**Source:** Security Audit, 2026-03-13

## Description

Three low-severity hardening gaps: the Docker container runs as root (no `USER` directive), the `/process` endpoint has no application-level rate limiting, and there is no CI/CD pipeline for automated security scanning.

---

## Tickets

### 3.1 – Docker Container Runs as Root

**File:** `Dockerfile`
**Finding:** L1 – No `USER` directive; application runs as root inside the container

**Current Code (Dockerfile:1–18):**
```dockerfile
FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py extract_fapiaos.py fill_excel.py gunicorn.conf.py ./
COPY templates/ templates/

ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["gunicorn", "--config", "gunicorn.conf.py", "app:app"]
```

No `USER` instruction is present. Any file written inside the container (e.g. to `/tmp`) or any exploited vulnerability will have root-level OS access within the container. The systemd deployment correctly uses an unprivileged `fapiao` user, but Docker deployments do not benefit from this hardening.

**Required Changes:**

1. Add a non-root user before the `CMD`, and adjust the working directory ownership:
```dockerfile
FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py extract_fapiaos.py fill_excel.py gunicorn.conf.py ./
COPY templates/ templates/

ENV PYTHONUNBUFFERED=1

# Run as non-root user
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser
USER appuser

EXPOSE 8000

CMD ["gunicorn", "--config", "gunicorn.conf.py", "app:app"]
```

2. Verify with `docker run --rm fapiao-worker id` that the output shows `appuser`, not `root`.

---

### 3.2 – No Application-Level Rate Limiting on /process

**File:** `app.py`
**Finding:** L2 – The `/process` endpoint performs expensive PDF merging and extraction with no request throttling

**Current Code (app.py:134):**
```python
@app.post('/process')
def process():
    # No rate limiting — any client can submit unlimited requests
    pdf_files = [f for f in request.files.getlist('pdfs') if f.filename]
    ...
```

A single client can flood the endpoint with 100 × 50 MB uploads, exhausting CPU and memory. While nginx-level rate limiting is the primary defence, defence-in-depth recommends application-layer protection as well.

**Required Changes:**

1. Add `Flask-Limiter` to `requirements.txt`:
```
flask-limiter==3.9.0
```

2. Configure rate limiting in `app.py`:
```python
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri='memory://',
)

@app.post('/process')
@limiter.limit('10 per minute')
def process():
    ...
```

3. Alternatively, handle this exclusively at the nginx reverse-proxy level with `limit_req_zone` and `limit_req` directives — acceptable if the app is never exposed without nginx.

---

### 3.3 – No CI/CD Pipeline for Automated Security Scanning

**File:** N/A (infrastructure gap)
**Finding:** L3 – No `.github/workflows/` or equivalent pipeline; no automated dependency scanning or SAST

**Current State:**
No CI/CD configuration exists in the repository. Dependency vulnerabilities (e.g. future CVEs in PyMuPDF or Flask) would only be discovered manually.

**Required Changes:**

1. Create `.github/workflows/security.yml` with:
   - `pip-audit` for Python dependency vulnerability scanning
   - `bandit` for Python static security analysis
   - Triggered on every push and pull request

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
      - run: bandit -r app.py extract_fapiaos.py fill_excel.py -ll
```

2. Consider adding Dependabot (`dependabot.yml`) to automatically open PRs for outdated dependencies.

---

## Acceptance Criteria

- [ ] `docker run --rm fapiao-worker id` returns a non-root user
- [ ] `docker inspect fapiao-worker` shows the process is not running as UID 0
- [ ] `/process` returns HTTP 429 after 10 requests per minute from the same IP (if Flask-Limiter is chosen)
- [ ] CI pipeline runs and passes on every push to `main`
- [ ] `pip-audit` reports no known vulnerabilities
- [ ] `bandit` reports no high-severity findings
