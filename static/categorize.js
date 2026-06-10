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
    // Submit via fetch - the browser will follow redirects automatically
    const resp = await fetch('/categorize', {
      method: 'POST',
      body: new FormData(form),
      // Let the browser follow redirects automatically (default behavior)
    });

    // After fetch completes, check if we ended up at the download page
    // resp.url will be the final URL after all redirects
    if (resp.url && resp.url.includes('/download/')) {
      window.location.href = resp.url;
      return;
    }

    // If not at download page but response is OK, something unexpected happened
    if (resp.ok) {
      // Try to parse as JSON or text to see what we got
      const text = await resp.text();
      if (text.includes('/download/')) {
        // Extract UUID from response and redirect
        const match = text.match(/\/download\/([^"\s]+)/);
        if (match) {
          window.location.href = '/download/' + match[1];
          return;
        }
      }
    }

    // If we get here, something went wrong
    throw new Error('Server returned ' + resp.status);
  } catch (err) {
    // JS fetch failed — fall back to a normal form POST.
    // The server will redirect to the download page via 302.
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
