document.addEventListener('DOMContentLoaded', () => {
  const search = document.querySelector('[data-autofocus-search]');
  if (search && window.matchMedia('(min-width: 700px)').matches) search.focus();
});
