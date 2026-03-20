# Respect User's Dark Mode Preference in Templates

- [x] Check Pico CSS v2 docs / source for the correct attribute to respect `prefers-color-scheme` (likely `data-theme="auto"` on `<html>`) — NOTE: templates actually use MVP.css, not Pico. Correct attribute is `color-mode="user"` on `<html>`. MVP.css custom props: `--color-secondary` (muted text), `--border-radius`. No `--del-color` equivalent; error box uses hardcoded red with `prefers-color-scheme` adaptation.
- [x] Update all HTML templates (`templates/index.html`, `templates/categorize.html`) to add the appropriate attribute — added `color-mode="user"` to both `<html>` tags
- [x] Verify the inline `<style>` overrides (muted color, error box, etc.) still look correct in both light and dark mode by reviewing the CSS custom properties used — replaced `--pico-muted-color` → `--color-secondary`, `--pico-border-radius` → `--border-radius`, `--pico-del-color` → hardcoded `#c0392b` (red visible in both modes, white text on top)
