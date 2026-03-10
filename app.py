import io
import shutil
import tempfile
from pathlib import Path

import fitz
import openpyxl
from flask import Flask, render_template, request, send_file

from extract_fapiaos import process_pdf
from fill_excel import MAX_ROWS, run1, run2

app = Flask(__name__)
app.secret_key = 'dev-only-not-for-production'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50 MB

DOWNLOAD_FILENAME = 'fapiao_claim_form_filled.xlsx'
XLSX_MIME = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


@app.get('/')
def index():
    return render_template('index.html')


@app.post('/process')
def process():
    # ── Validate inputs ───────────────────────────────────────────────────────
    pdf_files = request.files.getlist('pdfs')
    excel_file = request.files.get('excel')

    pdf_files = [f for f in pdf_files if f.filename]  # drop empty slots

    if not pdf_files:
        return render_template('index.html', error='Please select at least one PDF file.')

    if not excel_file or not excel_file.filename:
        return render_template('index.html', error='Please select the Excel template (.xlsx).')

    bad_pdfs = [f.filename for f in pdf_files if not f.filename.lower().endswith('.pdf')]
    if bad_pdfs:
        return render_template('index.html', error=f'Only .pdf files are accepted for fapiaos: {", ".join(bad_pdfs)}')

    if not excel_file.filename.lower().endswith('.xlsx'):
        return render_template('index.html', error='The template must be an .xlsx file.')

    # ── Process in a temp directory ───────────────────────────────────────────
    tmpdir = Path(tempfile.mkdtemp())
    try:
        # Save uploaded PDFs
        pdf_paths = []
        for f in pdf_files:
            dest = tmpdir / Path(f.filename).name
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

        if not fapiaos:
            return render_template(
                'index.html',
                error='No fapiao data could be extracted. Check that the PDFs contain embedded text (not scanned images).',
            )

        truncated = len(fapiaos) > MAX_ROWS
        if truncated:
            fapiaos = fapiaos[:MAX_ROWS]

        # Fill the Excel template
        try:
            wb = openpyxl.load_workbook(template_path, keep_vba=False)
        except Exception:
            return render_template('index.html', error='Could not open the Excel template. Make sure it is a valid .xlsx file.')

        ws = wb.active
        run1(fapiaos, ws)
        run2(fapiaos, ws)

        # Read result into memory so we can clean up temp dir before responding
        out_path = tmpdir / 'filled.xlsx'
        wb.save(out_path)
        buf = io.BytesIO(out_path.read_bytes())

    except Exception as e:
        return render_template('index.html', error=f'Unexpected error: {e}')
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
    app.run(debug=True)
