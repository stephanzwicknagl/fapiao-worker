# Security Audit

- [x] Review file upload handling: validate extension, MIME type, size limits, and filename sanitisation in the /process route — M6: no server-side magic byte check; extension+MIME validation confirmed; secure_filename() applied; 50MB limit confirmed
- [x] Audit session/token handling: SECRET_KEY usage, UUID token entropy, session data exposure — L2: placeholder SECRET_KEY silently accepted; UUID entropy 128-bit (adequate); pending dir world-readable in non-Docker (L1)
- [x] Review the fapiao/ package for injection risks: shell injection, path traversal, unsafe use of user-supplied data — M3: seller names from form body not validated against session; M4: category not validated; M5: toml_str() missing control char escaping; no shell injection; no path traversal
- [x] Check dependency security: scan requirements.txt for known CVEs using pip-audit — No known vulnerabilities found (all deps pinned)
- [x] Review Docker and deployment config: non-root user, exposed ports, secrets handling — H1: Dockerfile runs as root (no USER directive, contradicts stated hardening); L4: mappings.toml not in image; M1: rate limiter per-worker memory storage
- [x] Write findings report to .dispatch/tasks/security-audit/output.md — severity (HIGH/MEDIUM/LOW/INFO), file:line, description, recommendation — Written: 1 HIGH, 6 MEDIUM, 4 LOW, 8 INFO items
