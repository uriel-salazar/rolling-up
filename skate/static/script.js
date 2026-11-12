document.addEventListener('DOMContentLoaded', () => {
  const body = document.body;
  const menuOpenButton = document.getElementById('menu-open-button');
  const menuCloseButton = document.getElementById('menu-close-button');
  const navMenu = document.querySelector('.nav-menu');

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
