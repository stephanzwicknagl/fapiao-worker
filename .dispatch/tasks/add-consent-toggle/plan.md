# Add Consent Toggle to Categorize Page

- [x] Read `templates/categorize.html` and `fapiao/web.py` to understand the current categorize flow
- [x] Add a consent checkbox/toggle to `categorize.html` with text explaining that categorizations will be saved to improve the program for others; if unchecked, mappings are used only for this session's download
- [x] Update the POST `/categorize` route in `fapiao/web.py` so that new mappings are only written to `mappings.toml` when the consent field is present and true; without consent, still apply the mappings in-memory for the user's Excel download — done by adding optional `mappings` param to `run1` in `fill.py` and merging persisted + new mappings before passing to `run1`
