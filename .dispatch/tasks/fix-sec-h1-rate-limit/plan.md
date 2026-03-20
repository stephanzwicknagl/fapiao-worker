# Fix SEC-H.1: Add Rate Limit to /categorize Endpoint

- [x] Add `@limiter.limit('10 per minute')` decorator to the `/categorize` POST handler in `fapiao/web.py`, matching the existing limit on `/process`
- [x] Mark ticket SEC-H.1 as resolved in `docs/epics/epic-security-high.md`
