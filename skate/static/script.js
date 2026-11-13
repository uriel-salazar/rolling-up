document.addEventListener('DOMContentLoaded', () => {
  const body = document.body;
  const menuOpenButton = document.getElementById('menu-open-button');
  const menuCloseButton = document.getElementById('menu-close-button');
  const navMenu = document.querySelector('.nav-menu');

  const logoLinks = document.querySelectorAll('.logo, .app-brand, .map-brand, .logo-text');

  logoLinks.forEach((logo) => {
    logo.addEventListener('click', (event) => {
      const href = logo.getAttribute('href');
      if (!href || href !== '/') {
        return;
      }

      if (window.location.pathname === '/' || window.location.pathname.endsWith('/index.html')) {
        event.preventDefault();
        window.scrollTo({ top: 0, left: 0, behavior: 'auto' });
      }
    });
  });

  if (!menuOpenButton || !menuCloseButton || !navMenu) {
    return;
  }

  const setMenuState = (isOpen) => {
    body.classList.toggle('show-mobile-menu', isOpen);
  };

  menuOpenButton.addEventListener('click', () => setMenuState(true));
  menuCloseButton.addEventListener('click', () => setMenuState(false));

  navMenu.querySelectorAll('.nav-link').forEach((link) => {
    link.addEventListener('click', () => setMenuState(false));
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && body.classList.contains('show-mobile-menu')) {
      setMenuState(false);
    }
  });
});
