'use strict';

const PDF_DOWNLOAD_FILENAME = 'fapiaos_combined.pdf';
const SKIPPED_DOWNLOAD_FILENAME = 'fapiaos_skipped.pdf';

const UUID_PATTERN = /^[A-Za-z0-9_-]+$/;
/**
 * Get UUID from any download button on the page.
 */
function getUuid() {
  const btn = document.getElementById('btn-download-pdf') || document.getElementById('btn-download-skipped');
  const uuid = btn?.dataset.uuid;

  if (!uuid || !UUID_PATTERN.test(uuid)) {
    console.error('Invalid UUID format');
    return null;
  }
  return uuid;
}

/**
 * Trigger a file download from the given URL.
 */
async function downloadFile(url, filename) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Download failed: ${response.status}`);
  }

  const blob = await response.blob();
  const downloadUrl = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = downloadUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(downloadUrl);
}

/**
 * Auto-download the Excel file on page load.
 */
async function autoDownloadExcel() {
  const uuid = getUuid();
  if (!uuid) return;

  try {
    await downloadFile(`/download/${uuid}/excel`, 'fapiao_claim_form_filled.xlsx');
  } catch (err) {
    console.error('Auto-download failed:', err);
    // Don't show error - user can still use the manual download
  }
}

/**
 * Handle PDF download button click.
 */
function setupPdfDownload() {
  const btn = document.getElementById('btn-download-pdf');
  const status = document.getElementById('pdf-status');

  if (!btn) return;

  btn.addEventListener('click', async () => {
    const uuid = btn.dataset.uuid;
    if (!uuid) return;

    btn.classList.add('loading');
    btn.disabled = true;
    status.textContent = 'Downloading...';

    try {
      await downloadFile(`/download/${uuid}/combined`, PDF_DOWNLOAD_FILENAME);
      status.textContent = 'Downloaded!';
      status.style.color = '#28a745';
    } catch (err) {
      console.error('PDF download failed:', err);
      status.textContent = 'Download failed. Please try again.';
      status.style.color = '#c0392b';
      btn.disabled = false;
    } finally {
      btn.classList.remove('loading');
    }
  });
}

/**
 * Handle skipped pages download button click.
 */
function setupSkippedDownload() {
  const btn = document.getElementById('btn-download-skipped');
  const status = document.getElementById('skipped-status');

  if (!btn) return;

  btn.addEventListener('click', async () => {
    const uuid = btn.dataset.uuid;
    if (!uuid) return;

    btn.classList.add('loading');
    btn.disabled = true;
    status.textContent = 'Downloading...';

    try {
      await downloadFile(`/download/${uuid}/skipped`, SKIPPED_DOWNLOAD_FILENAME);
      status.textContent = 'Downloaded!';
      status.style.color = '#28a745';
    } catch (err) {
      console.error('Skipped PDF download failed:', err);
      status.textContent = 'Download failed. Please try again.';
      status.style.color = '#c0392b';
      btn.disabled = false;
    } finally {
      btn.classList.remove('loading');
    }
  });
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
  setupPdfDownload();
  setupSkippedDownload();
  // Auto-download Excel after a short delay to ensure page is rendered
  setTimeout(autoDownloadExcel, 100);
});
