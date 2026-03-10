import io
import logging
import os
import shutil
import tempfile
from pathlib import Path

import fitz
import openpyxl
from flask import Flask, render_template, request, send_file
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.utils import secure_filename

from extract_fapiaos import process_pdf
from fill_excel import MAX_ROWS, run1, run2

app = Flask(__name__)
app.secret_key = os.environ['SECRET_KEY']
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50 MB

if not app.debug:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(name)s: %(message)s',
    )

DOWNLOAD_FILENAME = 'fapiao_claim_form_filled.xlsx'
XLSX_MIME = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
MAX_PDF_FILES = 100


@app.errorhandler(RequestEntityTooLarge)
def too_large(e):
    return render_template('index.html', error='Upload too large. Maximum total size is 50 MB.'), 413


@app.get('/')
def index():
    return render_template('index.html')


@app.post('/process')
def process():
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
    xlsx_mimes = {XLSX_MIME, 'application/zip', 'application/octet-stream'}
    for f in pdf_files:
        if f.mimetype and f.mimetype not in pdf_mimes:
            return render_template('index.html', error=f'{f.filename!r} does not appear to be a PDF (received MIME type: {f.mimetype}).')
    if excel_file.mimetype and excel_file.mimetype not in xlsx_mimes:
        return render_template('index.html', error=f'The Excel file does not appear to be .xlsx (received MIME type: {excel_file.mimetype}).')

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

        # Fill the Excel template
        try:
            wb = openpyxl.load_workbook(template_path, keep_vba=False)
        except Exception:
            app.logger.exception('Failed to open uploaded Excel template')
            return render_template('index.html', error='Could not open the Excel template. Make sure it is a valid .xlsx file.')

        ws = wb.active
        run1(fapiaos, ws)
        run2(fapiaos, ws)

        # Read result into memory before cleaning up the temp dir
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


if __name__ == '__main__':
    # Development only. In production, run via gunicorn:
    #   .venv/bin/gunicorn --config gunicorn.conf.py app:app
    # For the Werkzeug reloader in dev, use:
    #   FLASK_DEBUG=1 SECRET_KEY=dev .venv/bin/flask run
    app.run(host='127.0.0.1', port=8000, debug=False)
