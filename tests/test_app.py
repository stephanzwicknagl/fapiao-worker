"""Tests for fapiao/web.py Flask routes — upload flow, categorization flow, error cases."""

import io
import json
import os
from unittest.mock import MagicMock, patch

import openpyxl
import pytest

os.environ.setdefault('SECRET_KEY', 'test-secret-key')

import fapiao.web as app_module
from fapiao.web import (
    _build_seller_summary,
    _save_new_mappings,
    _unmapped_sellers,
    app,
)

# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    with app.test_client() as c:
        yield c


def _minimal_xlsx_bytes() -> bytes:
    wb = openpyxl.Workbook()
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _fake_fapiao(**kwargs):
    defaults = {
        'source_file': 'test.pdf',
        'page': 1,
        'fapiao_number': '012345678901234',
        'date': '2024-03-15',
        'amount': '188.50',
        'vat_amount': '12.33',
        'seller': '沃尔玛（湖北）商业零售有限公司',
    }
    defaults.update(kwargs)
    return defaults


# ── GET / ─────────────────────────────────────────────────────────────────────

def test_index_returns_200(client):
    r = client.get('/')
    assert r.status_code == 200


# ── POST /process — validation ────────────────────────────────────────────────

def test_process_no_files_returns_error(client):
    r = client.post('/process', data={})
    assert r.status_code == 200
    assert b'Please select at least one PDF file' in r.data


def test_process_no_excel_returns_error(client):
    r = client.post('/process', data={
        'pdfs': (io.BytesIO(b'%PDF-1'), 'invoice.pdf'),
    }, content_type='multipart/form-data')
    assert b'Please select the Excel template' in r.data


def test_process_non_pdf_extension_rejected(client):
    r = client.post('/process', data={
        'pdfs': (io.BytesIO(b'data'), 'invoice.txt'),
        'excel': (io.BytesIO(_minimal_xlsx_bytes()), 'template.xlsx'),
    }, content_type='multipart/form-data')
    assert b'Only .pdf files are accepted' in r.data


def test_process_non_xlsx_template_rejected(client):
    r = client.post('/process', data={
        'pdfs': (io.BytesIO(b'%PDF-1'), 'invoice.pdf'),
        'excel': (io.BytesIO(b'not-xlsx'), 'template.xls'),
    }, content_type='multipart/form-data')
    assert b'must be an .xlsx file' in r.data


def test_process_too_many_pdfs_rejected(client):
    files = [
        (io.BytesIO(b'%PDF-1'), f'invoice_{i}.pdf')
        for i in range(101)
    ]
    r = client.post('/process', data={
        'pdfs': files,
        'excel': (io.BytesIO(_minimal_xlsx_bytes()), 'template.xlsx'),
    }, content_type='multipart/form-data')
    assert b'Too many files' in r.data


# ── POST /process — processing ────────────────────────────────────────────────

def _mock_fitz():
    """Return a context manager that patches fitz.open to avoid real PDF I/O."""
    fake_doc = MagicMock()
    fake_doc.__enter__ = lambda s: s
    fake_doc.__exit__ = MagicMock(return_value=False)
    fake_doc.__iter__ = lambda s: iter([])
    fake_doc.__len__ = lambda s: 1
    return patch('fapiao.web.fitz.open', return_value=fake_doc)


@patch('fapiao.web.process_pdf')
@patch('fapiao.web._load_mappings')
def test_process_no_fapiaos_extracted_returns_error(mock_mappings, mock_process, client):
    mock_process.return_value = []
    mock_mappings.return_value = {}

    with _mock_fitz():
        r = client.post('/process', data={
            'pdfs': (io.BytesIO(b'%PDF-1.4\n%%EOF'), 'invoice.pdf'),
            'excel': (io.BytesIO(_minimal_xlsx_bytes()), 'template.xlsx'),
        }, content_type='multipart/form-data')
    assert b'No fapiao data could be extracted' in r.data


@patch('fapiao.web.process_pdf')
@patch('fapiao.web._load_mappings')
@patch('fapiao.web.run1')
@patch('fapiao.web.run2')
def test_process_all_mapped_returns_xlsx(mock_run2, mock_run1, mock_mappings, mock_process, client):
    fapiao = _fake_fapiao()
    mock_process.return_value = [fapiao]
    mock_mappings.return_value = {fapiao['seller']: 'Groceries'}

    with _mock_fitz():
        r = client.post('/process', data={
            'pdfs': (io.BytesIO(b'%PDF-1.4\n%%EOF'), 'invoice.pdf'),
            'excel': (io.BytesIO(_minimal_xlsx_bytes()), 'template.xlsx'),
        }, content_type='multipart/form-data')
    assert r.status_code == 200
    assert r.content_type.startswith('application/vnd.openxmlformats')
    assert mock_run1.called
    assert mock_run2.called


@patch('fapiao.web.process_pdf')
@patch('fapiao.web._load_mappings')
def test_process_unmapped_redirects_to_categorize(mock_mappings, mock_process, client):
    fapiao = _fake_fapiao(seller='未知公司有限公司')
    mock_process.return_value = [fapiao]
    mock_mappings.return_value = {}  # no mappings → seller is unmapped

    with _mock_fitz():
        r = client.post('/process', data={
            'pdfs': (io.BytesIO(b'%PDF-1.4\n%%EOF'), 'invoice.pdf'),
            'excel': (io.BytesIO(_minimal_xlsx_bytes()), 'template.xlsx'),
        }, content_type='multipart/form-data')
    assert r.status_code == 200
    assert '未知公司有限公司'.encode() in r.data  # shown in categorize page


@patch('fapiao.web.process_pdf')
@patch('fapiao.web._load_mappings')
@patch('fapiao.web.run1')
@patch('fapiao.web.run2')
def test_process_truncates_over_40_fapiaos(mock_run2, mock_run1, mock_mappings, mock_process, client):
    fapiao = _fake_fapiao()
    mock_process.return_value = [fapiao] * 50  # 50 > MAX_ROWS=40
    mock_mappings.return_value = {fapiao['seller']: 'Groceries'}

    with _mock_fitz():
        client.post('/process', data={
            'pdfs': (io.BytesIO(b'%PDF-1.4\n%%EOF'), 'invoice.pdf'),
            'excel': (io.BytesIO(_minimal_xlsx_bytes()), 'template.xlsx'),
        }, content_type='multipart/form-data')

    # run1 should have been called with 40-entry list
    called_fapiaos = mock_run1.call_args[0][0]
    assert len(called_fapiaos) == 40


# ── POST /categorize ──────────────────────────────────────────────────────────

def _make_pending_session(fapiaos, tmp_path):
    """Write a fake pending session and monkeypatch PENDING_DIR."""
    uuid = 'testtoken123'
    pending = tmp_path / uuid
    pending.mkdir(parents=True)
    (pending / 'fapiaos.json').write_text(json.dumps(fapiaos), encoding='utf-8')
    wb = openpyxl.Workbook()
    buf = io.BytesIO()
    wb.save(buf)
    (pending / 'template.xlsx').write_bytes(buf.getvalue())
    return uuid, tmp_path


@patch('fapiao.web.run1')
@patch('fapiao.web.run2')
@patch('fapiao.web._save_new_mappings')
def test_categorize_invalid_uuid_rejected(mock_save, mock_run2, mock_run1, client):
    r = client.post('/categorize', data={'uuid': '../../../etc/passwd'})
    assert b'Invalid session ID' in r.data


@patch('fapiao.web.run1')
@patch('fapiao.web.run2')
@patch('fapiao.web._save_new_mappings')
def test_categorize_expired_session_rejected(mock_save, mock_run2, mock_run1, client, tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, 'PENDING_DIR', tmp_path)
    r = client.post('/categorize', data={'uuid': 'nonexistenttoken'})
    assert b'Session expired' in r.data


@patch('fapiao.web.run1')
@patch('fapiao.web.run2')
@patch('fapiao.web._save_new_mappings')
def test_categorize_valid_session_returns_xlsx(mock_save, mock_run2, mock_run1, client, tmp_path, monkeypatch):
    fapiaos = [_fake_fapiao()]
    uuid, pending_dir = _make_pending_session(fapiaos, tmp_path)
    monkeypatch.setattr(app_module, 'PENDING_DIR', pending_dir)

    r = client.post('/categorize', data={
        'uuid': uuid,
        'seller_0': '沃尔玛（湖北）商业零售有限公司',
        'cat_0': 'Groceries',
        'save_consent': 'on',
    })
    assert r.status_code == 200
    assert r.content_type.startswith('application/vnd.openxmlformats')
    mock_save.assert_called_once()
    saved_mappings = mock_save.call_args[0][0]
    assert saved_mappings.get('沃尔玛（湖北）商业零售有限公司') == 'Groceries'


@patch('fapiao.web.run1')
@patch('fapiao.web.run2')
@patch('fapiao.web._save_new_mappings')
def test_categorize_cleans_up_pending_dir(mock_save, mock_run2, mock_run1, client, tmp_path, monkeypatch):
    fapiaos = [_fake_fapiao()]
    uuid, pending_dir = _make_pending_session(fapiaos, tmp_path)
    monkeypatch.setattr(app_module, 'PENDING_DIR', pending_dir)

    client.post('/categorize', data={'uuid': uuid})

    assert not (pending_dir / uuid).exists()


# ── _unmapped_sellers ─────────────────────────────────────────────────────────

def test_unmapped_sellers_all_mapped():
    fapiaos = [_fake_fapiao(seller='CompanyA'), _fake_fapiao(seller='CompanyB')]
    mappings = {'CompanyA': 'Groceries', 'CompanyB': 'Restaurant'}
    assert _unmapped_sellers(fapiaos, mappings) == set()


def test_unmapped_sellers_empty_mapping_counts_as_unmapped():
    fapiaos = [_fake_fapiao(seller='CompanyA')]
    mappings = {'CompanyA': ''}  # empty string = unmapped
    assert _unmapped_sellers(fapiaos, mappings) == {'CompanyA'}


def test_unmapped_sellers_missing_seller_ignored():
    fapiaos = [_fake_fapiao(seller='')]
    assert _unmapped_sellers(fapiaos, {}) == set()


def test_unmapped_sellers_none_seller_ignored():
    fapiaos = [_fake_fapiao(seller=None)]
    assert _unmapped_sellers(fapiaos, {}) == set()


# ── _build_seller_summary ─────────────────────────────────────────────────────

def test_build_seller_summary_counts_and_totals():
    fapiaos = [
        _fake_fapiao(seller='CompanyA', amount='100.00', fapiao_number='001'),
        _fake_fapiao(seller='CompanyA', amount='50.00', fapiao_number='002'),
    ]
    result = _build_seller_summary(fapiaos, {'CompanyA'})
    assert len(result) == 1
    item = result[0]
    assert item['seller'] == 'CompanyA'
    assert item['count'] == 2
    assert item['total'] == pytest.approx(150.0)
    assert set(item['fapiao_numbers']) == {'001', '002'}


def test_build_seller_summary_excludes_non_matching_sellers():
    fapiaos = [_fake_fapiao(seller='CompanyA'), _fake_fapiao(seller='CompanyB')]
    result = _build_seller_summary(fapiaos, {'CompanyA'})
    assert all(r['seller'] == 'CompanyA' for r in result)


# ── _save_new_mappings ────────────────────────────────────────────────────────

def test_save_new_mappings_writes_toml(tmp_path, monkeypatch):
    mappings_file = tmp_path / 'mappings.toml'
    monkeypatch.setattr(app_module, '_MAPPINGS_FILE', mappings_file)

    _save_new_mappings({'TestSeller': 'Groceries'})

    assert mappings_file.exists()
    import tomllib
    data = tomllib.loads(mappings_file.read_text(encoding='utf-8'))
    assert data['mappings']['TestSeller'] == 'Groceries'


def test_save_new_mappings_additive_no_overwrite(tmp_path, monkeypatch):
    mappings_file = tmp_path / 'mappings.toml'
    mappings_file.write_text('[mappings]\n"ExistingSeller" = "Restaurant"\n', encoding='utf-8')
    monkeypatch.setattr(app_module, '_MAPPINGS_FILE', mappings_file)

    _save_new_mappings({'ExistingSeller': 'Groceries'})  # should NOT overwrite

    import tomllib
    data = tomllib.loads(mappings_file.read_text(encoding='utf-8'))
    assert data['mappings']['ExistingSeller'] == 'Restaurant'


def test_save_new_mappings_skips_empty_category(tmp_path, monkeypatch):
    mappings_file = tmp_path / 'mappings.toml'
    monkeypatch.setattr(app_module, '_MAPPINGS_FILE', mappings_file)

    _save_new_mappings({'SkippedSeller': ''})

    assert not mappings_file.exists()


def test_save_new_mappings_noop_on_empty_dict(tmp_path, monkeypatch):
    mappings_file = tmp_path / 'mappings.toml'
    monkeypatch.setattr(app_module, '_MAPPINGS_FILE', mappings_file)

    _save_new_mappings({})

    assert not mappings_file.exists()


# ── security headers ──────────────────────────────────────────────────────────

def test_security_headers_present(client):
    r = client.get('/')
    assert r.headers.get('X-Content-Type-Options') == 'nosniff'
    assert r.headers.get('X-Frame-Options') == 'DENY'
