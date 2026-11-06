(() => {
  const sections = ['people','schedule','attendance','leave','salary','audit'];
  function syncNavigation() {
    const portal = location.pathname.endsWith('/portal.html');
    const hash = sections.includes(location.hash.slice(1)) ? location.hash : '#people';
    for (const link of document.querySelectorAll('[data-cafe-link], #app > nav a')) {
      const url = new URL(link.href, location.href);
      const active = url.pathname === location.pathname && (!portal || url.hash === hash);
      if (active) link.setAttribute('aria-current','page');
      else link.removeAttribute('aria-current');
    }
    if (portal) {
      for (const id of sections) {
        const section = document.getElementById(id);
        if (section) section.classList.toggle('cafe-offscreen', '#' + id !== hash);
      }
      for (const section of document.querySelectorAll('[data-cafe-section]')) {
        section.classList.toggle('cafe-offscreen', '#' + section.dataset.cafeSection !== hash);
      }
    }
  }
  syncNavigation();
  window.addEventListener('hashchange', syncNavigation);
})();
