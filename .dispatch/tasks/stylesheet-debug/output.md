# Stylesheet Debug Report

## Root Cause

**The Content Security Policy (CSP) set in `fapiao/web.py` blocks the CDN stylesheet.**

In `fapiao/web.py` lines 149–161, the `@app.after_request` hook `set_security_headers` sets:

```
Content-Security-Policy: default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; img-src 'self' data:; form-action 'self';
```

The `style-src` directive only allows:
- `'self'` — stylesheets from the same origin (the Flask server itself)
- `'unsafe-inline'` — inline `<style>` blocks

`https://cdn.jsdelivr.net` is not listed, so the browser will **refuse to load** the Pico CSS link in `templates/index.html` line 7:

```html
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@picocss/pico@2/css/pico.min.css">
```

The browser console will show a CSP violation error like:
> Refused to load stylesheet 'https://cdn.jsdelivr.net/...' because it violates the following Content Security Policy directive: "style-src 'self' 'unsafe-inline'"

## What Still Works

The inline `<style>` block in `index.html` (lines 8–38) **does load** because `'unsafe-inline'` permits it. However, since the Pico CSS framework never loads, all CSS custom properties prefixed with `--pico-*` (e.g. `--pico-muted-color`, `--pico-del-color`, `--pico-border-radius`) resolve to nothing, and Pico's base styles (typography, form inputs, buttons) are absent.

## Other Findings

- **No static/ directory** — there is no local CSS that could override or substitute for Pico CSS.
- **`gunicorn.conf.py`** — sets only worker/binding/logging config; no headers added there.
- **No middleware** — no Nginx/reverse-proxy config in the repo; CSP is set solely by the Flask `after_request` hook.
- **The `<link>` tag itself is correct** — the URL and attribute syntax in `index.html` are fine; the problem is purely the CSP.

## Fix

Add `https://cdn.jsdelivr.net` to the `style-src` directive in `web.py`:

```python
"style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
```
