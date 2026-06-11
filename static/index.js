'use strict';

const form = document.querySelector('form');
const overlay = document.getElementById('processing-overlay');
const main = document.querySelector('main');
const header = document.querySelector('header');

async function handleFormSubmit(targetForm, e) {
  e.preventDefault();

  // Show loading state
  targetForm.classList.add('loading');
  const label = targetForm.querySelector('.label');
  const originalText = label ? label.textContent : '';
  if (label) label.textContent = 'Processing…';

  // Show overlay
  overlay.classList.add('active');

  // Force browser to paint the overlay before starting fetch
  await new Promise(resolve => requestAnimationFrame(resolve));

  const formData = new FormData(targetForm);

  try {
    const response = await fetch(targetForm.action, {
      method: 'POST',
      body: formData,
      redirect: 'follow'
    });

    const responseUrl = response.url;
    const html = await response.text();
    const parser = new DOMParser();
    const doc = parser.parseFromString(html, 'text/html');

    // Check if it's a redirect to download page
    if (responseUrl.includes('/download/')) {
      // Navigate to download page
      window.location.href = responseUrl;
      return;
    }

    // Check if it's categorize page (has the categorize form)
    const categorizeForm = doc.querySelector('form[action="/categorize"]');
    if (categorizeForm) {
      // Extract and inject main content
      const newMain = doc.querySelector('main');
      const newHeader = doc.querySelector('header');

      if (newMain && main) {
        main.innerHTML = newMain.innerHTML;
      }
      if (newHeader && header) {
        header.innerHTML = newHeader.innerHTML;
      }

      // Update title
      const newTitle = doc.querySelector('title');
      if (newTitle) {
        document.title = newTitle.textContent;
      }

      // Fade out overlay
      overlay.classList.remove('active');
      return;
    }

    // Check if it's an error on index page (error box present)
    const errorBox = doc.querySelector('.error-box');
    if (errorBox) {
      // Remove existing error box
      const existingError = main.querySelector('.error-box');
      if (existingError) {
        existingError.remove();
      }

      // Insert new error box at the start of main
      main.insertBefore(errorBox, main.firstChild);

      // Reset form
      targetForm.classList.remove('loading');
      if (label) label.textContent = originalText;

      // Fade out overlay
      overlay.classList.remove('active');
      return;
    }

    // Fallback: unexpected response, navigate to show it
    window.location.href = responseUrl;

  } catch (err) {
    // Network or other error
    console.error('Error submitting form:', err);

    // Remove existing error box
    const existingError = main.querySelector('.error-box');
    if (existingError) {
      existingError.remove();
    }

    // Show error message
    const errorDiv = document.createElement('div');
    errorDiv.className = 'error-box';
    errorDiv.setAttribute('role', 'alert');
    errorDiv.innerHTML = '<strong>Error:</strong> Failed to submit form. Please try again.';
    main.insertBefore(errorDiv, main.firstChild);

    // Reset form
    targetForm.classList.remove('loading');
    if (label) label.textContent = originalText;

    // Fade out overlay
    overlay.classList.remove('active');
  }
}

// Handle main form submission
form.addEventListener('submit', (e) => handleFormSubmit(form, e));

// Handle dynamic form submissions (categorize form injected later)
main.addEventListener('submit', (e) => {
  const targetForm = e.target.closest('form');
  if (targetForm && targetForm !== form) {
    handleFormSubmit(targetForm, e);
  }
});
