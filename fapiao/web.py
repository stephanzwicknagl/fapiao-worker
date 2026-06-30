import contextlib
import io
import json
import logging
import os
import secrets
import shutil
import tempfile
import time
import tomllib
from pathlib import Path

import fitz
import openpyxl
import tomli_w
from flask import Flask, redirect, render_template, request, send_file
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.utils import secure_filename

from fapiao.ai_categorizer import categorize_sellers
from fapiao.categories import CATEGORY_ENGLISH_NAMES
from fapiao.extract import process_pdf_with_skipped
from fapiao.fill import MAX_ROWS, _load_mappings, run1, run2

app = Flask(
    __name__,
    template_folder=str(Path(__file__).parent.parent / "templates"),
    static_folder=str(Path(__file__).parent.parent / "static"),
)
app.secret_key = os.environ["SECRET_KEY"]
csrf = CSRFProtect(app)
limiter = Limiter(get_remote_address, app=app, default_limits=[], storage_uri="memory://")
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB

if not app.debug:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

DOWNLOAD_FILENAME = "fapiao_claim_form_filled.xlsx"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MAX_PDF_FILES = 100

PENDING_DIR = Path(tempfile.gettempdir()) / "fapiao_pending"
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
                app.logger.info("Cleaned up stale session: %s", entry.name)
        except (OSError, FileNotFoundError):
            pass


CATEGORIES = CATEGORY_ENGLISH_NAMES

_MAPPINGS_FILE = Path(__file__).parent.parent / "mappings.toml"


def _unmapped_sellers(fapiaos, mappings):
    """Return set of seller names with no non-empty mapping."""
    unmapped = set()
    for row in fapiaos:
        seller = row.get("seller") or ""
        if seller and not mappings.get(seller, ""):
            unmapped.add(seller)
    return unmapped


def _build_seller_summary(fapiaos, sellers):
    """Return list of {seller, count, total, fapiao_numbers} dicts for the given seller set."""
    counts = {}
    totals = {}
    numbers = {}
    for row in fapiaos:
        seller = row.get("seller") or ""
        if seller in sellers:
            counts[seller] = counts.get(seller, 0) + 1
            with contextlib.suppress(ValueError):
                totals[seller] = totals.get(seller, 0.0) + float(row.get("amount") or 0)
            num = row.get("fapiao_number") or ""
            if num:
                numbers.setdefault(seller, []).append(num)
    return [
        {"seller": s, "count": counts[s], "total": totals.get(s, 0.0), "fapiao_numbers": numbers.get(s, [])}
        for s in sellers
    ]


def _save_new_mappings(new: dict) -> None:
    """Persist new seller→category entries to mappings.toml (additive only)."""
    if not new:
        return
    if _MAPPINGS_FILE.exists():
        with open(_MAPPINGS_FILE, "rb") as f:
            data = tomllib.load(f)
    else:
        data = {}
    existing = data.get("mappings", {})
    changed = False
    for seller, category in new.items():
        if not category:
            continue
        if seller not in existing or not existing[seller]:
            existing[seller] = category
            changed = True
    if not changed:
        return
    data["mappings"] = existing
    _MAPPINGS_FILE.write_bytes(tomli_w.dumps(data).encode("utf-8"))


@app.errorhandler(RequestEntityTooLarge)
def too_large(_):
    return render_template("index.html", error="Upload too large. Maximum total size is 50 MB."), 413


@app.get("/")
def index():
    return render_template("index.html")


@app.after_request
def set_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "style-src 'self' 'unsafe-inline' https://unpkg.com; "
        "script-src 'self'; "
        "img-src 'self' data:; "
        "form-action 'self';"
    )
    return response


@app.post("/process")
@limiter.limit("10 per minute")
def process():
    _cleanup_stale_pending()
    # ── Validate inputs ───────────────────────────────────────────────────────
    pdf_files = [f for f in request.files.getlist("pdfs") if f.filename]
    excel_file = request.files.get("excel")

    if not pdf_files:
        return render_template("index.html", error="Please select at least one PDF file.")

    if not excel_file or not excel_file.filename:
        return render_template("index.html", error="Please select the Excel template (.xlsx).")

    if len(pdf_files) > MAX_PDF_FILES:
        return render_template("index.html", error=f"Too many files — maximum is {MAX_PDF_FILES} PDFs per request.")

    bad_pdfs = [(f.filename or "") for f in pdf_files if not (f.filename or "").lower().endswith(".pdf")]
    if bad_pdfs:
        return render_template("index.html", error=f"Only .pdf files are accepted: {', '.join(bad_pdfs)}")

    if not (excel_file.filename or "").lower().endswith(".xlsx"):
        return render_template("index.html", error="The template must be an .xlsx file.")

    # MIME type checks (browser-supplied, so defence-in-depth only)
    pdf_mimes = {"application/pdf", "application/x-pdf"}
    xlsx_mimes = {XLSX_MIME}
    for f in pdf_files:
        if f.mimetype and f.mimetype not in pdf_mimes:
            return render_template(
                "index.html", error=f"{f.filename!r} does not appear to be a PDF (received MIME type: {f.mimetype})."
            )
        if not _check_magic(f.stream, b"%PDF"):
            return render_template("index.html", error=f"{f.filename!r} is not a valid PDF file.")
    if excel_file.mimetype and excel_file.mimetype not in xlsx_mimes:
        return render_template(
            "index.html",
            error=f"The Excel file does not appear to be .xlsx (received MIME type: {excel_file.mimetype}).",
        )
    if not _check_magic(excel_file.stream, b"PK\x03\x04"):
        return render_template("index.html", error="The Excel file is not a valid .xlsx file.")

    # ── Process in an isolated temp directory ─────────────────────────────────
    tmpdir = Path(tempfile.mkdtemp())
    try:
        # Save uploaded PDFs with sanitised filenames
        pdf_paths = []
        for i, f in enumerate(pdf_files):
            safe_name = secure_filename(f.filename or "") or f"upload_{i}.pdf"
            dest = tmpdir / safe_name
            f.save(dest)
            pdf_paths.append(dest)

        # Save uploaded Excel template
        template_path = tmpdir / "template.xlsx"
        excel_file.save(template_path)

        # Combine all PDFs into one
        combined = fitz.open()
        for path in pdf_paths:
            with fitz.open(str(path)) as doc:
                combined.insert_pdf(doc)
        combined_path = str(tmpdir / "combined.pdf")
        combined.save(combined_path)

        # Extract fapiao data and track skipped pages
        fapiaos, skipped_pages = process_pdf_with_skipped(combined_path)
        app.logger.info(
            "Extracted %d fapiaos from %d PDF(s), %d skipped pages", len(fapiaos), len(pdf_paths), len(skipped_pages)
        )

        if not fapiaos:
            combined.close()
            return render_template(
                "index.html",
                error="No fapiao data could be extracted. Check that the PDFs contain embedded text (not scanned images).",
            )

        # Sort by date (oldest first), then by amount (largest first) as secondary sort
        fapiaos.sort(key=lambda r: (r.get("date") or "", -float(r.get("amount") or 0)))

        if len(fapiaos) > MAX_ROWS:
            app.logger.warning("Truncating %d fapiaos to form limit of %d", len(fapiaos), MAX_ROWS)
            fapiaos = fapiaos[:MAX_ROWS]

        # Create valid PDF with only successfully extracted pages
        valid_pdf = fitz.open()
        for fapiao in fapiaos:
            beg_page = fapiao["page"] - fapiao["pages_amount"]  # indexed by last page
            end_page = fapiao["page"] - 1  # Convert from 1-indexed to 0-indexed
            valid_pdf.insert_pdf(combined, from_page=beg_page, to_page=end_page)
        # Save valid PDF to bytes
        valid_buf = io.BytesIO()
        valid_pdf.save(valid_buf)
        valid_pdf_bytes = valid_buf.getvalue()
        valid_pdf.close()

        # Create skipped PDF with pages skipped due to garbled text (if any)
        skipped_pdf_bytes = None
        if skipped_pages:
            skipped_pdf = fitz.open()
            for page_num in skipped_pages:
                skipped_pdf.insert_pdf(combined, from_page=page_num - 1, to_page=page_num - 1)
            skipped_buf = io.BytesIO()
            skipped_pdf.save(skipped_buf)
            skipped_pdf_bytes = skipped_buf.getvalue()
            skipped_pdf.close()

        combined.close()

        mappings = _load_mappings()
        use_stored_mappings = os.environ.get("USE_STORED_VENDOR_MAPPINGS", "True").lower() in ("true", "1")
        if use_stored_mappings:
            unmapped = _unmapped_sellers(fapiaos, mappings)
        else:
            unmapped = {row.get("seller", "") for row in fapiaos}

        if unmapped:
            # Try AI categorization for unmapped sellers
            ai_mappings, still_unmapped = categorize_sellers(unmapped, CATEGORIES)

            # Save successful AI mappings immediately (fully automated)
            if ai_mappings:
                # Persist selections to mappings.toml only if environment variable set
                if use_stored_mappings:
                    _save_new_mappings(ai_mappings)
                app.logger.info("AI categorized %d sellers automatically", len(ai_mappings))
                # Update in-memory mappings for run1
                mappings = {**mappings, **ai_mappings}

            # If any sellers still unmapped after AI, show manual categorization form
            if still_unmapped:
                uuid = secrets.token_urlsafe(16)
                pending = PENDING_DIR / uuid
                pending.mkdir(parents=True, exist_ok=True)
                (pending / "fapiaos.json").write_text(json.dumps(fapiaos), encoding="utf-8")
                (pending / "template.xlsx").write_bytes(template_path.read_bytes())
                # Save valid PDF for later download (only successfully extracted pages)
                (pending / "combined.pdf").write_bytes(valid_pdf_bytes)
                # Save skipped PDF if there are skipped pages
                if skipped_pdf_bytes:
                    (pending / "skipped.pdf").write_bytes(skipped_pdf_bytes)

                all_sellers = {row.get("seller") or "" for row in fapiaos if row.get("seller")}
                # Include AI-mapped sellers as "already mapped" in the UI
                ai_mapped_sellers = set(ai_mappings.keys())
                persisted_mapped = all_sellers - still_unmapped - ai_mapped_sellers
                unmapped_summary = _build_seller_summary(fapiaos, still_unmapped)
                mapped_summary = [
                    {**s, "category": mappings[s["seller"]]}
                    for s in _build_seller_summary(fapiaos, persisted_mapped)
                    if mappings.get(s["seller"])
                ]
                # Add AI-mapped sellers to the mapped section
                ai_mapped_summary = [
                    {**s, "category": ai_mappings[s["seller"]]}
                    for s in _build_seller_summary(fapiaos, ai_mapped_sellers)
                    if s["seller"] in ai_mappings
                ]
                mapped_summary.extend(ai_mapped_summary)
                return render_template(
                    "categorize.html",
                    uuid=uuid,
                    unmapped_sellers=unmapped_summary,
                    mapped_sellers=mapped_summary,
                    categories=CATEGORIES,
                )

            # All sellers now mapped via AI - proceed to fill form
            # (fall through to the "All sellers mapped" logic below)
            unmapped = set()  # Reset unmapped since AI categorized all

        # All sellers mapped — create session and redirect to download page
        uuid = secrets.token_urlsafe(16)
        pending = PENDING_DIR / uuid
        pending.mkdir(parents=True, exist_ok=True)

        try:
            # Save state for download page
            (pending / "fapiaos.json").write_text(json.dumps(fapiaos), encoding="utf-8")
            (pending / "template.xlsx").write_bytes(template_path.read_bytes())
            # Save valid PDF for later download (only successfully extracted pages)
            (pending / "combined.pdf").write_bytes(valid_pdf_bytes)
            # Save skipped PDF if there are skipped pages
            if skipped_pdf_bytes:
                (pending / "skipped.pdf").write_bytes(skipped_pdf_bytes)

            # Fill the Excel
            try:
                wb = openpyxl.load_workbook(template_path, keep_vba=False)
            except Exception:
                app.logger.exception("Failed to open uploaded Excel template")
                shutil.rmtree(pending, ignore_errors=True)
                return render_template(
                    "index.html", error="Could not open the Excel template. Make sure it is a valid .xlsx file."
                )

            ws = wb.active
            run1(fapiaos, ws, mappings=mappings)
            run2(fapiaos, ws)

            # Save filled Excel to pending directory for download
            filled_path = pending / "filled.xlsx"
            wb.save(filled_path)

            # Create flags file to track download status
            has_skipped = (pending / "skipped.pdf").exists()
            (pending / "downloads.json").write_text(
                json.dumps({"excel": False, "pdf": False, "skipped": False, "has_skipped": has_skipped}),
                encoding="utf-8",
            )

        except RequestEntityTooLarge:
            shutil.rmtree(pending, ignore_errors=True)
            raise  # let the registered error handler deal with it
        except Exception:
            app.logger.exception("Unhandled error in /process")
            shutil.rmtree(pending, ignore_errors=True)
            return render_template(
                "index.html",
                error="An unexpected error occurred while processing the files. Check the server logs for details.",
            )

    except RequestEntityTooLarge:
        raise  # let the registered error handler deal with it
    except Exception:
        app.logger.exception("Unhandled error in /process")
        return render_template(
            "index.html",
            error="An unexpected error occurred while processing the files. Check the server logs for details.",
        )
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    # Redirect to download page (files remain in pending dir for download)
    return redirect(f"/download/{uuid}")


@app.post("/categorize")
@limiter.limit("10 per minute")
def categorize():
    uuid = request.form.get("uuid", "")
    # Basic validation: only allow safe characters in uuid
    if not uuid or not all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_" for c in uuid):
        return render_template("index.html", error="Invalid session ID.")

    pending = PENDING_DIR / uuid
    if not pending.exists():
        return render_template("index.html", error="Session expired. Please re-upload.")

    try:
        # Parse seller→category selections from form
        new_mappings = {}
        i = 0
        while f"seller_{i}" in request.form:
            seller = request.form[f"seller_{i}"]
            cat = request.form.get(f"cat_{i}", "").strip()
            if seller and cat:
                new_mappings[seller] = cat
            i += 1

        # Persist selections to mappings.toml only if the user consented
        consent = request.form.get("save_consent") == "on"
        if consent:
            _save_new_mappings(new_mappings)
            run1_mappings = None  # run1 will reload from file and see the new entries
        else:
            # Merge new selections over the persisted mappings in memory only
            persisted = _load_mappings()
            run1_mappings = {**persisted, **{k: v for k, v in new_mappings.items() if v}}

        # Load saved state and fill Excel
        fapiaos = json.loads((pending / "fapiaos.json").read_text(encoding="utf-8"))
        # Ensure chronological order (oldest first), then by amount (largest first)
        fapiaos.sort(key=lambda r: (r.get("date") or "", -float(r.get("amount") or 0)))
        template = pending / "template.xlsx"

        try:
            wb = openpyxl.load_workbook(template, keep_vba=False)
        except Exception:
            app.logger.exception("Failed to open saved Excel template")
            return render_template("index.html", error="Could not open the saved Excel template. Please re-upload.")

        ws = wb.active
        run1(fapiaos, ws, mappings=run1_mappings)
        run2(fapiaos, ws)

        # Save filled Excel to pending directory for download
        filled_path = pending / "filled.xlsx"
        wb.save(filled_path)

        # Create flags file to track download status
        # Note: skipped is optional, cleanup happens when excel + pdf are downloaded
        has_skipped = (pending / "skipped.pdf").exists()
        (pending / "downloads.json").write_text(
            json.dumps({"excel": False, "pdf": False, "skipped": False, "has_skipped": has_skipped}), encoding="utf-8"
        )

    except Exception:
        app.logger.exception("Unhandled error in /categorize")
        shutil.rmtree(pending, ignore_errors=True)
        return render_template("index.html", error="An unexpected error occurred. Check the server logs for details.")

    # Redirect to download page (files remain in pending dir for download)
    return redirect(f"/download/{uuid}")


@app.get("/download/<uuid>")
def download_page(uuid: str):
    """Render the download page with auto-download for Excel."""
    # Validate UUID format
    if not uuid or not all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_" for c in uuid):
        return render_template("index.html", error="Invalid session ID.")

    pending = PENDING_DIR / uuid
    if not pending.exists():
        return render_template("index.html", error="Session expired. Please re-upload.")

    # Check if PDFs exist
    has_pdf = (pending / "combined.pdf").exists()
    has_skipped = (pending / "skipped.pdf").exists()

    return render_template("download.html", uuid=uuid, has_pdf=has_pdf, has_skipped=has_skipped)


@app.get("/download/<uuid>/<filetype>")
def download_file(uuid: str, filetype: str):
    """Serve the filled Excel, combined PDF, or skipped pages PDF, tracking download status."""
    # Validate UUID format
    if not uuid or not all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_" for c in uuid):
        return render_template("index.html", error="Invalid session ID."), 400

    if filetype not in ("excel", "combined", "skipped"):
        return render_template("index.html", error="Invalid file type."), 400

    pending = PENDING_DIR / uuid
    if not pending.exists():
        return render_template("index.html", error="Session expired. Please re-upload."), 404

    # Determine which file to serve
    if filetype == "excel":
        file_path = pending / "filled.xlsx"
        download_name = DOWNLOAD_FILENAME
        mimetype = XLSX_MIME
    elif filetype == "combined":
        file_path = pending / "combined.pdf"
        download_name = "fapiaos_combined.pdf"
        mimetype = "application/pdf"
    else:  # skipped
        file_path = pending / "skipped.pdf"
        download_name = "fapiaos_skipped.pdf"
        mimetype = "application/pdf"

    if not file_path.exists():
        return render_template("index.html", error="File not found."), 404

    # Read file into memory before potentially cleaning up
    buf = io.BytesIO(file_path.read_bytes())

    # Track download status
    try:
        downloads_file = pending / "downloads.json"
        if downloads_file.exists():
            downloads = json.loads(downloads_file.read_text(encoding="utf-8"))
            downloads[filetype] = True
            downloads_file.write_text(json.dumps(downloads), encoding="utf-8")

            # Clean up when excel + combined + skipped are downloaded
            excel_downloaded = downloads.get("excel")
            pdf_downloaded = downloads.get("combined") or not (pending / "combined.pdf").exists()
            skipped_downloaded = downloads.get("skipped") or not (pending / "skipped.pdf").exists()
            if excel_downloaded and pdf_downloaded and skipped_downloaded:
                shutil.rmtree(pending, ignore_errors=True)
                app.logger.info("Cleaned up session after required downloads: %s", uuid)
    except Exception:
        # Don't fail the download if tracking fails
        app.logger.exception("Failed to track download status for %s", uuid)

    buf.seek(0)
    return send_file(
        buf,
        as_attachment=True,
        download_name=download_name,
        mimetype=mimetype,
    )


if __name__ == "__main__":
    # Development only. In production, run via gunicorn:
    #   .venv/bin/gunicorn --config gunicorn.conf.py app:app
    # For the Werkzeug reloader in dev, use:
    #   FLASK_DEBUG=1 SECRET_KEY=dev .venv/bin/flask run
    app.run(host="127.0.0.1", port=8000, debug=False)
