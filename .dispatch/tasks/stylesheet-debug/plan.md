# Debug: Stylesheet Not Applied in index.html

- [x] Read `templates/index.html` to confirm the stylesheet link and check for any obvious issues
- [x] Read `fapiao/web.py` to check for Content Security Policy headers or any response manipulation — **found root cause: CSP blocks cdn.jsdelivr.net**
- [x] Check if there's a `static/` folder or any local CSS override that might interfere — none found
- [x] Check `gunicorn.conf.py` and any middleware for CSP or header settings — no additional headers there
- [x] Write a summary of findings to `.dispatch/tasks/stylesheet-debug/output.md`
