# Add Success Screen After Download

- [x] Read `templates/index.html` and `fapiao/web.py` to understand the current download flow and how the page behaves post-download
- [x] Add a hidden success panel to `templates/index.html` that is revealed after the download completes (the existing JS already detects this via a timeout); the panel should confirm success, offer a "Go back home" / "Process another file" button to reset the form, and include a "Share with friends" button using the Web Share API (with a fallback copy-to-clipboard link)
