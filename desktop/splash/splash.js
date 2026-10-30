'use strict';
// Loading screen bundled into the shell. Rust calls horizonSplash.fail(...) when the
// project core cannot start; on success the window navigates to the editor instead.
(function () {
  const lang = (navigator.language || 'en').toLowerCase().startsWith('ru') ? 'ru' : 'en';
  document.documentElement.lang = lang;
  for (const el of document.querySelectorAll('[data-en]')) el.textContent = el.dataset[lang];
  let failed = false;
  window.horizonSplash = {
    fail(detail) {
      if (failed) return;
      failed = true;
      document.body.classList.add('failed');
      document.querySelector('.splash').setAttribute('aria-busy', 'false');
      document.getElementById('status').hidden = true;
      document.getElementById('failure').hidden = false;
      document.getElementById('failureMessage').textContent = String(detail && detail.message || detail);
      if (detail && detail.log) {
        const log = document.getElementById('failureLog');
        log.hidden = false;
        log.textContent = (lang === 'ru' ? 'Журнал ядра: ' : 'Core log: ') + detail.log;
      }
    },
  };
}());
