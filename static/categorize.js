'use strict';

const form = document.querySelector('form');
const successPanel = document.getElementById('success-panel');
const btnShare = document.getElementById('btn-share');

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  form.classList.add('loading');
  const label = form.querySelector('.label');
  label.textContent = 'Processing\u2026';

  try {
    const resp = await fetch('/categorize', {
      method: 'POST',
      body: new FormData(form),
    });

    if (!resp.ok) {
      throw new Error('Server returned ' + resp.status);
    }

    // Derive filename from Content-Disposition if present, else use default
    const disposition = resp.headers.get('Content-Disposition') || '';
    const match = disposition.match(/filename[^;=\n]*=["']?([^"';\n]+)["']?/i);
    const filename = match ? match[1] : 'fapiao_claim_form_filled.xlsx';

    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    form.classList.remove('loading');
    form.hidden = true;
    successPanel.hidden = false;
  } catch (err) {
    // JS failed — fall back to a normal form POST so the download still works.
    // form.submit() bypasses submit event listeners, so no infinite loop.
    form.classList.remove('loading');
    label.textContent = 'Download filled form';
    form.submit();
  }
});

// Share this page via Web Share API, falling back to clipboard copy.
btnShare.addEventListener('click', async () => {
  const url = location.origin;
  const shareData = { title: 'Fapiao Claim Form Processor', url };
  if (navigator.share && navigator.canShare && navigator.canShare(shareData)) {
    try {
      await navigator.share(shareData);
    } catch (e) {
      if (e.name !== 'AbortError') {
        await copyToClipboard(url);
      }
    }
  } else {
    await copyToClipboard(url);
  }
});

async function copyToClipboard(text) {
  try {
    await navigator.clipboard.writeText(text);
    const orig = btnShare.textContent;
    btnShare.textContent = 'Link copied!';
    setTimeout(() => { btnShare.textContent = orig; }, 2000);
  } catch (e) {
    // Clipboard API unavailable — do nothing silently
  }
}
