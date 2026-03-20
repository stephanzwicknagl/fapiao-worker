import contextlib
import io
import json
import logging
import os
import secrets
import shutil
import stat
import tempfile
import time
import tomllib
from pathlib import Path

import tomli_w

import fitz
import openpyxl
from flask import Flask, render_template, request, send_file
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.utils import secure_filename

from fapiao.extract import process_pdf
from fapiao.fill import MAX_ROWS, _load_mappings, run1, run2

app = Flask(
    __name__,
    template_folder=str(Path(__file__).parent.parent / 'templates'),
    static_folder=str(Path(__file__).parent.parent / 'static'),
)
app.secret_key = os.environ['SECRET_KEY']
csrf = CSRFProtect(app)
limiter = Limiter(get_remote_address, app=app, default_limits=[], storage_uri='memory://')
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50 MB

if not app.debug:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(name)s: %(message)s',
    )

DOWNLOAD_FILENAME = 'fapiao_claim_form_filled.xlsx'
XLSX_MIME = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
MAX_PDF_FILES = 100

PENDING_DIR = Path(tempfile.gettempdir()) / 'fapiao_pending'
SESSION_TTL_SECONDS = 3600  # 1 hour


def _check_magic(file_obj, expected_bytes: bytes) -> bool:
    """Check that file_obj starts with expected_bytes; resets stream position afterwards."""
    file_obj.seek(0)
    header = file_obj.read(len(expected_bytes))
    file_obj.seek(0)
    return header == expected_bytes


def _cleanup_stale_pending() -> None:
    """Remove pending session directories older than SESSION_TTL_SECONDS."""
    if not PENDING_DIR.exists():
        return
    now = time.time()
    try:
        entries = list(PENDING_DIR.iterdir())
    except OSError:
        return
    for entry in entries:
        try:
            st = entry.stat(follow_symlinks=False)
            if (st.st_mode & 0o170000) != 0o040000:
                continue  # not a real directory (e.g. symlink)
            if (now - st.st_mtime) > SESSION_TTL_SECONDS:
                shutil.rmtree(entry)
                app.logger.info('Cleaned up stale session: %s', entry.name)
        except (OSError, FileNotFoundError):
            pass

CATEGORIES = [
    'Accommodation / Lodging', 'Audio / Video Equipment', 'Auto Parts ',
    'Automobile', 'Bag / Purse', 'Beer/Wine', 'Beauty & Hairdressing',
    'Bicycle', 'Bicycle Parts', 'Book / Newspaper', 'Camera', 'Carpet',
    'Ceramics', 'Cleaning Service', 'Clothes', 'Computer ',
    'Computer Accessories', 'Consulting Fee', 'Cosmetics',
    'Cultural Service (Entry tickets for tourist attractions)', 'DVD / CD ',
    'Eyeglasses', 'Fitness fee', 'Flowers / Plants', 'Fruits', 'Furniture',
    'Gasoline', 'Groceries', 'Handicrafts', 'Health care fee',
    'Home Decorations', 'Household Electrical Appliances', 'Household Items',
    'Jewelry', 'Laundry fee', 'Maintenance Service Parts', 'Medicine',
    'Mobile Phone', 'Mobile Phone Accessories', 'Motor vehicle insurance',
    'Musical Instruments', 'Office Supplies', 'Other',
    'Paint / Paint Supplies', 'Pet medical fees', 'Pet Supplies', 'Picture',
    'Picture Frames', 'Property Service', 'Restaurant', 'Scooter', 'Shoes',
    'Sporting Goods', 'Tea', 'Toys', 'Transportation fee', 'Tuition Fee',
    'TV', 'Watch', 'Wellness & Livelihood (Spa, Massages, Acupuncture, etc.)',
]

_MAPPINGS_FILE = Path(__file__).parent.parent / 'mappings.toml'


def _unmapped_sellers(fapiaos, mappings):
    """Return set of seller names with no non-empty mapping."""
    unmapped = set()
    for row in fapiaos:
        seller = row.get('seller') or ''
        if seller and not mappings.get(seller, ''):
            unmapped.add(seller)
    return unmapped


def _build_seller_summary(fapiaos, sellers):
    """Return list of {seller, count, total, fapiao_numbers} dicts for the given seller set."""
    counts = {}
    totals = {}
    numbers = {}
    for row in fapiaos:
        seller = row.get('seller') or ''
        if seller in sellers:
            counts[seller] = counts.get(seller, 0) + 1
            with contextlib.suppress(ValueError):
                totals[seller] = totals.get(seller, 0.0) + float(row.get('amount') or 0)
            num = row.get('fapiao_number') or ''
            if num:
                numbers.setdefault(seller, []).append(num)
    return [
        {'seller': s, 'count': counts[s], 'total': totals.get(s, 0.0),
         'fapiao_numbers': numbers.get(s, [])}
        for s in sellers
    ]


def _save_new_mappings(new: dict) -> None:
    """Persist new seller→category entries to mappings.toml (additive only)."""
    if not new:
        return
    if _MAPPINGS_FILE.exists():
        with open(_MAPPINGS_FILE, 'rb') as f:
            data = tomllib.load(f)
    else:
        data = {}
    existing = data.get('mappings', {})
    changed = False
    for seller, category in new.items():
        if not category:
            continue
        if seller not in existing or not existing[seller]:
            existing[seller] = category
            changed = True
    if not changed:
        return
    data['mappings'] = existing
    _MAPPINGS_FILE.write_bytes(tomli_w.dumps(data).encode('utf-8'))


@app.errorhandler(RequestEntityTooLarge)
def too_large(e):
    return render_template('index.html', error='Upload too large. Maximum total size is 50 MB.'), 413


@app.get('/')
def index():
    return render_template('index.html')


@app.after_request
def set_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "style-src 'self' 'unsafe-inline' https://unpkg.com; "
        "script-src 'self'; "
        "img-src 'self' data:; "
        "form-action 'self';"
    )
    return response


@app.post('/process')
@limiter.limit('10 per minute')
def process():
    _cleanup_stale_pending()
    # ── Validate inputs ───────────────────────────────────────────────────────
    pdf_files = [f for f in request.files.getlist('pdfs') if f.filename]
    excel_file = request.files.get('excel')

    if not pdf_files:
        return render_template('index.html', error='Please select at least one PDF file.')

    if not excel_file or not excel_file.filename:
        return render_template('index.html', error='Please select the Excel template (.xlsx).')

    if len(pdf_files) > MAX_PDF_FILES:
        return render_template('index.html', error=f'Too many files — maximum is {MAX_PDF_FILES} PDFs per request.')

    bad_pdfs = [f.filename for f in pdf_files if not f.filename.lower().endswith('.pdf')]
    if bad_pdfs:
        return render_template('index.html', error=f'Only .pdf files are accepted: {", ".join(bad_pdfs)}')

    if not excel_file.filename.lower().endswith('.xlsx'):
        return render_template('index.html', error='The template must be an .xlsx file.')

    # MIME type checks (browser-supplied, so defence-in-depth only)
    pdf_mimes = {'application/pdf', 'application/x-pdf'}
    xlsx_mimes = {XLSX_MIME}
    for f in pdf_files:
        if f.mimetype and f.mimetype not in pdf_mimes:
            return render_template('index.html', error=f'{f.filename!r} does not appear to be a PDF (received MIME type: {f.mimetype}).')
        if not _check_magic(f.stream, b'%PDF'):
            return render_template('index.html', error=f'{f.filename!r} is not a valid PDF file.')
    if excel_file.mimetype and excel_file.mimetype not in xlsx_mimes:
        return render_template('index.html', error=f'The Excel file does not appear to be .xlsx (received MIME type: {excel_file.mimetype}).')
    if not _check_magic(excel_file.stream, b'PK\x03\x04'):
        return render_template('index.html', error='The Excel file is not a valid .xlsx file.')

    # ── Process in an isolated temp directory ─────────────────────────────────
    tmpdir = Path(tempfile.mkdtemp())
    try:
        # Save uploaded PDFs with sanitised filenames
        pdf_paths = []
        for i, f in enumerate(pdf_files):
            safe_name = secure_filename(f.filename) or f'upload_{i}.pdf'
            dest = tmpdir / safe_name
            f.save(dest)
            pdf_paths.append(dest)

        # Save uploaded Excel template
        template_path = tmpdir / 'template.xlsx'
        excel_file.save(template_path)

        # Combine all PDFs into one
        combined = fitz.open()
        for path in pdf_paths:
            with fitz.open(str(path)) as doc:
                combined.insert_pdf(doc)
        combined_path = str(tmpdir / 'combined.pdf')
        combined.save(combined_path)
        combined.close()

        # Extract fapiao data
        fapiaos = process_pdf(combined_path)
        app.logger.info('Extracted %d fapiaos from %d PDF(s)', len(fapiaos), len(pdf_paths))

        if not fapiaos:
            return render_template(
                'index.html',
                error='No fapiao data could be extracted. Check that the PDFs contain embedded text (not scanned images).',
            )

        if len(fapiaos) > MAX_ROWS:
            app.logger.warning('Truncating %d fapiaos to form limit of %d', len(fapiaos), MAX_ROWS)
            fapiaos = fapiaos[:MAX_ROWS]

        mappings = _load_mappings()
        unmapped = _unmapped_sellers(fapiaos, mappings)

        if unmapped:
            # Save state for the categorize step
            uuid = secrets.token_urlsafe(16)
            pending = PENDING_DIR / uuid
            pending.mkdir(parents=True, exist_ok=True)
            (pending / 'fapiaos.json').write_text(json.dumps(fapiaos), encoding='utf-8')
            (pending / 'template.xlsx').write_bytes(template_path.read_bytes())

            all_sellers = {row.get('seller') or '' for row in fapiaos if row.get('seller')}
            mapped_sellers_set = all_sellers - unmapped
            unmapped_summary = _build_seller_summary(fapiaos, unmapped)
            mapped_summary = [
                {**s, 'category': mappings[s['seller']]}
                for s in _build_seller_summary(fapiaos, mapped_sellers_set)
                if mappings.get(s['seller'])
            ]
            return render_template(
                'categorize.html',
                uuid=uuid,
                unmapped_sellers=unmapped_summary,
                mapped_sellers=mapped_summary,
                categories=CATEGORIES,
            )

        # All sellers mapped — fill and return immediately
        try:
            wb = openpyxl.load_workbook(template_path, keep_vba=False)
        except Exception:
            app.logger.exception('Failed to open uploaded Excel template')
            return render_template('index.html', error='Could not open the Excel template. Make sure it is a valid .xlsx file.')

        ws = wb.active
        run1(fapiaos, ws)
        run2(fapiaos, ws)

        out_path = tmpdir / 'filled.xlsx'
        wb.save(out_path)
        buf = io.BytesIO(out_path.read_bytes())

    except RequestEntityTooLarge:
        raise  # let the registered error handler deal with it
    except Exception:
        app.logger.exception('Unhandled error in /process')
        return render_template('index.html', error='An unexpected error occurred while processing the files. Check the server logs for details.')
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    buf.seek(0)
    return send_file(
        buf,
        as_attachment=True,
        download_name=DOWNLOAD_FILENAME,
        mimetype=XLSX_MIME,
    )


@app.post('/categorize')
@limiter.limit('10 per minute')
def categorize():
    uuid = request.form.get('uuid', '')
    # Basic validation: only allow safe characters in uuid
    if not uuid or not all(c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_' for c in uuid):
        return render_template('index.html', error='Invalid session ID.')

    pending = PENDING_DIR / uuid
    if not pending.exists():
        return render_template('index.html', error='Session expired. Please re-upload.')

    try:
        # Parse seller→category selections from form
        new_mappings = {}
        i = 0
        while f'seller_{i}' in request.form:
            seller = request.form[f'seller_{i}']
            cat = request.form.get(f'cat_{i}', '').strip()
            if seller and cat:
                new_mappings[seller] = cat
            i += 1

        # Persist selections to mappings.toml only if the user consented
        consent = request.form.get('save_consent') == 'on'
        if consent:
            _save_new_mappings(new_mappings)
            run1_mappings = None  # run1 will reload from file and see the new entries
        else:
            # Merge new selections over the persisted mappings in memory only
            persisted = _load_mappings()
            run1_mappings = {**persisted, **{k: v for k, v in new_mappings.items() if v}}

        # Load saved state and fill Excel
        fapiaos = json.loads((pending / 'fapiaos.json').read_text(encoding='utf-8'))
        template = pending / 'template.xlsx'

        try:
            wb = openpyxl.load_workbook(template, keep_vba=False)
        except Exception:
            app.logger.exception('Failed to open saved Excel template')
            return render_template('index.html', error='Could not open the saved Excel template. Please re-upload.')

        ws = wb.active
        run1(fapiaos, ws, mappings=run1_mappings)
        run2(fapiaos, ws)

        buf = io.BytesIO()
        wb.save(buf)

    except Exception:
        app.logger.exception('Unhandled error in /categorize')
        return render_template('index.html', error='An unexpected error occurred. Check the server logs for details.')
    finally:
        shutil.rmtree(pending, ignore_errors=True)

    buf.seek(0)
    return send_file(
        buf,
        as_attachment=True,
        download_name=DOWNLOAD_FILENAME,
        mimetype=XLSX_MIME,
    )


if __name__ == '__main__':
    # Development only. In production, run via gunicorn:
    #   .venv/bin/gunicorn --config gunicorn.conf.py app:app
    # For the Werkzeug reloader in dev, use:
    #   FLASK_DEBUG=1 SECRET_KEY=dev .venv/bin/flask run
    app.run(host='127.0.0.1', port=8000, debug=False)
