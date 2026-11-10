document.addEventListener('DOMContentLoaded', () => {
  const body = document.body;
  const menuOpenButton = document.getElementById('menu-open-button');
  const menuCloseButton = document.getElementById('menu-close-button');
  const navMenu = document.querySelector('.nav-menu');

  if (!menuOpenButton || !menuCloseButton || !navMenu) {
    return;
  }

  const closeMenu = () => {
    body.classList.remove('show-mobile-menu');
    navMenu.classList.remove('show');
  };

  const openMenu = () => {
    body.classList.add('show-mobile-menu');
    navMenu.classList.add('show');
  };

  menuOpenButton.addEventListener('click', openMenu);
  menuCloseButton.addEventListener('click', closeMenu);

  navMenu.querySelectorAll('.nav-link').forEach((link) => {
    link.addEventListener('click', closeMenu);
  });
});
