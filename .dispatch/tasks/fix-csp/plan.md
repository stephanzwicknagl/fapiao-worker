# Fix CSP to Allow CDN Stylesheet

- [x] In `fapiao/web.py` line 156, remove the single quotes around `https://cdn.jsdelivr.net` in the `style-src` directive (single quotes are only valid for CSP keywords like `'self'`, not URLs)
