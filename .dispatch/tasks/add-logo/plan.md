# Add Logo to Website

- [x] Explore the vector/ directory and the project's static file structure to understand where logo assets should live
  - 7 SVG variants in vector/; static/ exists with only categorize.js; created static/images/
- [x] Copy the SVG logo files to the correct static assets location (e.g. static/images/ or similar)
  - All 7 SVGs copied to static/images/
- [x] Identify all HTML templates in templates/ and determine where the logo should appear (header, navbar, etc.)
  - Two templates: index.html and categorize.html; logo goes in <header> above <h1>
- [x] Add the logo to the HTML templates with appropriate img tags or inline SVG
  - Used <picture> with default-monochrome.svg (light) / default-monochrome-white.svg (dark); wrapped in <a href="/"> link
- [x] Write a summary to .dispatch/tasks/add-logo/output.md explaining what was done and how to create a favicon from the SVG files
  - Written with 3 favicon generation options (cairosvg, Inkscape, ImageMagick)
