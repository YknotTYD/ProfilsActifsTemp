// Feed vidéo du tableau de bord : réactions et comptage des vues.
// Source unique côté serveur : profiles.ProfileVideo (voir templates/feed.html).
(() => {
  const feed = document.getElementById('feed');
  if (!feed) return;

  const csrftoken = document.querySelector('meta[name="csrf-token"]').content;

  async function post(url, payload) {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'X-CSRFToken': csrftoken, 'Content-Type': 'application/json' },
      body: payload ? JSON.stringify(payload) : null,
    });
    return res.ok ? res.json().catch(() => ({})) : Promise.reject(res);
  }

  // --- Réactions -----------------------------------------------------------
  feed.querySelectorAll('.react-btn').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const item = btn.closest('.feed-item');
      const reaction = btn.dataset.reaction;
      try {
        const data = await post(
          `/api/profiles/videos/${btn.dataset.videoId}/react/`,
          { reaction },
        );
        const like = item.querySelector('[data-reaction="like"]');
        const dislike = item.querySelector('[data-reaction="dislike"]');
        like.classList.toggle('is-on', data.reaction === 'like');
        dislike.classList.toggle('is-on', data.reaction === 'dislike');
        const count = like.querySelector('.feed-btn-count');
        if (count) count.textContent = data.likes;
      } catch (err) {
        console.error(err);
      }
    });
  });

  // --- Comptage des vues --------------------------------------------------
  // Une vue par vidéo et par session (le serveur dédoublonne) : on notifie
  // dès qu'une vidéo occupe l'essentiel du viewport du feed.
  const seen = new Set();
  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting || entry.intersectionRatio < 0.6) return;
        const item = entry.target;
        const id = item.dataset.videoId;
        if (seen.has(id)) return;
        seen.add(id);
        post(`/api/profiles/videos/${id}/view/`).catch(() => seen.delete(id));
      });
    },
    { threshold: [0, 0.6, 1] },
  );
  feed.querySelectorAll('.feed-item').forEach((item) => observer.observe(item));
})();
