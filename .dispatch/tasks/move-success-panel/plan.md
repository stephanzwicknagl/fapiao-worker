# Move Success Panel to categorize.html

- [x] Read `templates/index.html`, `templates/categorize.html`, and `fapiao/web.py` to understand both flows and where the download actually happens after categorizing
- [x] Remove the success panel, its CSS, and its JS from `templates/index.html`, restoring it to the state before the `success-screen` job (the form should simply restore itself after the timeout as before)
- [x] Add the success panel, its CSS, and its JS to `templates/categorize.html` — revealed after the download fires following form submission
