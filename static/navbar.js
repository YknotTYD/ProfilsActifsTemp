// Barre de navigation : menus déroulants + centre de notifications.
(() => {
  // --- Menu hamburger (petits ecrans) ----------------------------------
  const burger = document.getElementById('topbar-burger');
  const navLinks = document.getElementById('topbar-nav');

  function setNav(open) {
    if (!burger || !navLinks) return;
    navLinks.classList.toggle('is-open', open);
    burger.setAttribute('aria-expanded', String(open));
    burger.setAttribute('aria-label', open ? 'Fermer le menu' : 'Ouvrir le menu');
  }

  if (burger && navLinks) {
    burger.addEventListener('click', (e) => {
      e.stopPropagation();
      const opening = !navLinks.classList.contains('is-open');
      closeAll(null);
      setNav(opening);
    });
    // un lien choisi referme le panneau (la page suivante le rouvrirait sinon
    // le temps de la navigation).
    navLinks.addEventListener('click', () => setNav(false));
  }

  const menus = Array.from(document.querySelectorAll('.topbar-menu'));
  const toggles = menus.map((menu) => ({
    menu,
    btn: menu.querySelector('.topbar-menu-btn'),
    panel: menu.querySelector('.topbar-dropdown'),
  }));

  function closeAll(except) {
    toggles.forEach(({ btn, panel }) => {
      if (panel === except) return;
      panel.hidden = true;
      btn.setAttribute('aria-expanded', 'false');
    });
  }

  toggles.forEach(({ menu, btn, panel }) => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const opening = panel.hidden;
      setNav(false);
      closeAll(opening ? panel : null);
      panel.hidden = !opening;
      btn.setAttribute('aria-expanded', String(opening));
      if (opening && menu.dataset.menu === 'notif') openNotifications();
    });
  });

  document.addEventListener('click', () => {
    closeAll(null);
    setNav(false);
  });
  document.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape') return;
    closeAll(null);
    setNav(false);
  });

  // --- Centre de notifications -----------------------------------------
  const bell = document.getElementById('notif-bell');
  if (!bell) return;

  const meta = document.querySelector('meta[name="csrf-token"]');
  const csrftoken = meta ? meta.content : '';
  const badge = document.getElementById('notif-badge');
  const list = document.getElementById('notif-list');

  async function api(url, options = {}) {
    const res = await fetch(url, {
      ...options,
      headers: { 'X-CSRFToken': csrftoken, 'Content-Type': 'application/json' },
    });
    return res.json();
  }

  function setBadge(count) {
    if (count > 0) {
      badge.textContent = count > 99 ? '99+' : count;
      badge.hidden = false;
    } else {
      badge.hidden = true;
    }
  }

  const escape = (s) =>
    String(s).replace(/[&<>"']/g, (ch) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[ch]));

  function notifLabel(n) {
    // Consultation de profil : on complete avec l'organisation (jamais la
    // personne), portee dans le payload par le serveur.
    if (n.type === 'PROFILE_CONSULTED' && n.payload && n.payload.organisation) {
      return `${n.label} par ${escape(n.payload.organisation)}`;
    }
    return escape(n.label);
  }

  function renderList(notifications) {
    if (!notifications || notifications.length === 0) {
      list.innerHTML = '<li class="notif-empty">Aucune notification pour le moment.</li>';
      return;
    }
    list.innerHTML = notifications
      .map(
        (n) => `
        <li>
          <a href="${escape(n.url || '#')}" class="notif-item ${n.read ? '' : 'is-unread'}" data-id="${n.id}">
            <span class="notif-item-label">${notifLabel(n)}</span>
            <span class="notif-item-date">${new Date(n.created_at).toLocaleString('fr-FR')}</span>
          </a>
        </li>`,
      )
      .join('');
    list.querySelectorAll('.notif-item').forEach((item) => {
      item.addEventListener('click', () => {
        if (item.classList.contains('is-unread')) {
          api(`/api/notifications/${item.dataset.id}/read/`, { method: 'POST' });
        }
      });
    });
  }

  async function openNotifications() {
    try {
      const data = await api('/api/notifications/');
      renderList(data.notifications);
      if (data.unread_count > 0) {
        setBadge(0);
        await api('/api/notifications/read-all/', { method: 'POST' });
      }
    } catch (err) {
      console.error(err);
    }
  }

  async function refreshCount() {
    try {
      const { count } = await api('/api/notifications/unread-count/');
      setBadge(count);
    } catch (err) {
      console.error(err);
    }
  }

  refreshCount();
  setInterval(refreshCount, 60000);
})();
