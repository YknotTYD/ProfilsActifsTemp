// Barre de navigation : menus déroulants + centre de notifications.
(() => {
  const menus = Array.from(document.querySelectorAll('.topbar-menu'));
  if (menus.length === 0) return;

  const toggles = menus.map((menu) => ({
    menu,
    btn: menu.querySelector('.topbar-menu-btn'),
    panel: menu.querySelector('.topbar-dropdown'),
  }));

  // Elements focusables d'un panneau (RGAA 7.1 / 10.7 : les menus doivent
  // etre entierement utilisables au clavier).
  function focusables(panel) {
    return Array.from(
      panel.querySelectorAll('a[href], button:not([disabled])'),
    );
  }

  // `restoreFocus` : quand on ferme un menu ouvert au clavier (Echap), le
  // focus doit revenir sur le bouton qui l'a ouvert, jamais se perdre.
  function closeAll(except, restoreFocus) {
    toggles.forEach(({ btn, panel }) => {
      if (panel === except) return;
      if (!panel.hidden && restoreFocus) btn.focus();
      panel.hidden = true;
      btn.setAttribute('aria-expanded', 'false');
    });
  }

  function openPanel(entry) {
    closeAll(entry.panel);
    entry.panel.hidden = false;
    entry.btn.setAttribute('aria-expanded', 'true');
    if (entry.menu.dataset.menu === 'notif') openNotifications();
    const items = focusables(entry.panel);
    if (items.length) items[0].focus();
  }

  toggles.forEach((entry) => {
    const { btn, panel } = entry;

    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      if (panel.hidden) openPanel(entry);
      else closeAll(null);
    });

    btn.addEventListener('keydown', (e) => {
      if (panel.hidden && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) {
        e.preventDefault();
        openPanel(entry);
      }
    });

    // Fleches / Debut / Fin pour parcourir les entrees, Tab referme le menu.
    panel.addEventListener('keydown', (e) => {
      const items = focusables(panel);
      if (!items.length) return;
      const i = items.indexOf(document.activeElement);
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        items[(i + 1) % items.length].focus();
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        items[(i - 1 + items.length) % items.length].focus();
      } else if (e.key === 'Home') {
        e.preventDefault();
        items[0].focus();
      } else if (e.key === 'End') {
        e.preventDefault();
        items[items.length - 1].focus();
      } else if (e.key === 'Tab') {
        closeAll(null);
      }
    });
  });

  document.addEventListener('click', (e) => {
    if (e.target.closest('.topbar-menu')) return;
    closeAll(null);
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeAll(null, true);
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
    list.setAttribute('aria-busy', 'false');
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
