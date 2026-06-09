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

    // Check if we were redirected to the download page
    if (resp.url && resp.url.includes('/download/')) {
      window.location.href = resp.url;
      return;
    }

    if (!resp.ok) {
      throw new Error('Server returned ' + resp.status);
    }

    // Unexpected response - fall back to normal form submission
    throw new Error('Unexpected response');
  } catch (err) {
    // JS failed — fall back to a normal form POST.
    // The server will redirect to the download page.
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
