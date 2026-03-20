# Add Logo — Summary

## What was done

1. **SVG files copied** from `vector/` to `static/images/` — all 7 variants are now served as static assets by Flask.

2. **Logo added to both templates** (`templates/index.html` and `templates/categorize.html`) in the `<header>` section, above the `<h1>`. A `<picture>` element provides automatic light/dark switching:
   - **Light mode** → `default-monochrome.svg` (475×90, brand gradient colors, horizontal layout)
   - **Dark mode** → `default-monochrome-white.svg` (475×90, all white, horizontal layout)

   The logo is wrapped in an `<a href="/">` link so it acts as a home button on the categorize page.

## Which variant is used where

| Template | Light mode variant | Dark mode variant |
|---|---|---|
| `index.html` | `default-monochrome.svg` | `default-monochrome-white.svg` |
| `categorize.html` | `default-monochrome.svg` | `default-monochrome-white.svg` |

The other variants (`default.svg` — square 300×300; `isolated-*` — icon only without text; `default-monochrome-black.svg` — black text, no gradient) are available in `static/images/` for future use (e.g. email signatures, print, social preview images).

## How to generate a favicon from the SVG files

Use `isolated-monochrome-black.svg` (or `default.svg`) as the source — a square icon works best for favicons.

### Option A — cairosvg + Pillow (pure Python, no system deps)

```bash
pip install cairosvg Pillow

# Generate PNG sizes
cairosvg static/images/isolated-monochrome-black.svg -o /tmp/favicon-512.png -W 512 -H 512
cairosvg static/images/isolated-monochrome-black.svg -o /tmp/favicon-192.png -W 192 -H 192
cairosvg static/images/isolated-monochrome-black.svg -o static/favicon-32x32.png -W 32 -H 32
cairosvg static/images/isolated-monochrome-black.svg -o static/favicon-16x16.png -W 16 -H 16

# Bundle into .ico (includes 16, 32, 48 px layers)
python3 - <<'EOF'
from PIL import Image
sizes = [(16,16),(32,32),(48,48)]
imgs = []
for s in sizes:
    import cairosvg, io
    png = cairosvg.svg2png(url="static/images/isolated-monochrome-black.svg", output_width=s[0], output_height=s[1])
    imgs.append(Image.open(io.BytesIO(png)))
imgs[0].save("static/favicon.ico", format="ICO", append_images=imgs[1:], sizes=sizes)
EOF
```

### Option B — Inkscape (best rendering quality)

```bash
# Requires Inkscape 1.x
inkscape static/images/isolated-monochrome-black.svg \
  --export-type=png --export-width=512 --export-height=512 \
  --export-filename=/tmp/favicon-512.png

inkscape static/images/isolated-monochrome-black.svg \
  --export-type=png --export-width=32 --export-height=32 \
  --export-filename=/tmp/favicon-32.png

inkscape static/images/isolated-monochrome-black.svg \
  --export-type=png --export-width=16 --export-height=16 \
  --export-filename=/tmp/favicon-16.png

# Convert PNG → ICO with ImageMagick
convert /tmp/favicon-16.png /tmp/favicon-32.png static/favicon.ico
```

### Option C — ImageMagick only (if it has SVG/rsvg support)

```bash
# Check if RSVG delegate is available: convert -list delegate | grep rsvg
convert -background none -resize 16x16 \
  static/images/isolated-monochrome-black.svg /tmp/fav16.png
convert -background none -resize 32x32 \
  static/images/isolated-monochrome-black.svg /tmp/fav32.png
convert /tmp/fav16.png /tmp/fav32.png static/favicon.ico
```

### Wiring the favicon into the templates

Add these lines inside `<head>` in both `index.html` and `categorize.html`:

```html
<link rel="icon" type="image/x-icon" href="{{ url_for('static', filename='favicon.ico') }}">
<link rel="icon" type="image/png" sizes="32x32" href="{{ url_for('static', filename='favicon-32x32.png') }}">
<link rel="icon" type="image/png" sizes="16x16" href="{{ url_for('static', filename='favicon-16x16.png') }}">
<!-- For PWA / Android home screen -->
<link rel="apple-touch-icon" sizes="192x192" href="{{ url_for('static', filename='favicon-192.png') }}">
```
