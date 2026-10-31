document.addEventListener('DOMContentLoaded', () => {
  const search = document.querySelector('[data-autofocus-search]');
  if (search && window.matchMedia('(min-width: 700px)').matches) search.focus();

  document.querySelectorAll('form[data-confirm]').forEach((form) => {
    form.addEventListener('submit', (event) => {
      if (!window.confirm(form.dataset.confirm || 'Continue?')) event.preventDefault();
    });
  });

  document.querySelectorAll('button[type="submit"]').forEach((button) => {
    button.addEventListener('click', () => {
      const form = button.closest('form');
      if (!form || form.dataset.confirm) return;
      if (!form.checkValidity()) return;
      button.dataset.originalLabel = button.textContent.trim();
      button.classList.add('is-submitting');
      button.setAttribute('aria-busy', 'true');
      window.setTimeout(() => {
        if (button.isConnected) {
          button.classList.remove('is-submitting');
          button.removeAttribute('aria-busy');
        }
      }, 2500);
    });
  });
});
