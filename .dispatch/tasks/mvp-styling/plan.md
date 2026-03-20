# Style Templates for MVP.css

- [x] Read all templates (`templates/index.html`, `templates/categorize.html`) to understand current structure and inline styles
- [x] Fetch the MVP.css docs/demo to understand what semantic HTML elements and classes it provides out of the box — MVP.css is classless, styles semantic HTML, has --color-secondary/--color-text-secondary/--border-radius vars, constrains form width as a card, styles header/main/footer with max-width: var(--width-content)
- [x] Rework `index.html`: moved h1/subtitle to `<header>`, removed body/h1/label/footer CSS overrides, replaced .note/.subtitle classes with semantic `<small>`, kept only .error-box and loading spinner CSS
- [x] Rework `categorize.html`: moved h1/subtitle to `<header>`, removed redundant CSS overrides, replaced var(--color-secondary) with var(--color-text-secondary) for text, added form max-width:100% override for full-width table layout, removed role="grid" (Pico-specific)
- [x] Removed all Pico CSS remnants: role="grid" on tables, var(--color-secondary) used as text color (replaced with --color-text-secondary), body max-width overrides, redundant label/th/footer CSS rules
