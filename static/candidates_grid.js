// Grille de profils : lecture video a la demande (point 3.4).
//
// Rien ne joue tant qu'on n'a rien demande. Le gabarit
// (`templates/candidates_grid.html`) ne pose qu'une vignette et un bouton
// "Lire" ; l'element <video> ou <iframe> n'existe qu'a partir du clic, et
// disparait des qu'on ouvre une autre carte. C'est ce qui remplace l'ancien
// feed vertical, ou les vingt videos de la page se chargeaient et
// demarraient toutes seules.
(() => {
  const grid = document.querySelector('[data-cgrid]');
  if (!grid) return;

  // Une seule video a la fois : ouvrir une carte ferme la precedente. Deux
  // bandes-son en meme temps n'ont aucun sens, et une iframe laissee en
  // arriere-plan continuerait de jouer sans qu'on la voie.
  let playing = null;

  function close(player) {
    if (!player) return;
    const media = player.querySelector('[data-cgrid-media]');
    // Vider la source avant de retirer l'element : sinon Chrome poursuit le
    // telechargement de la video sur un noeud detache.
    if (media && media.tagName === 'VIDEO') {
      media.pause();
      media.removeAttribute('src');
      media.load();
    }
    if (media) media.remove();
    player.classList.remove('is-playing');
    if (playing === player) playing = null;
  }

  /* Adresse de lecture d'un lecteur distant : `autoplay` n'est ajoute qu'ici,
     au moment du clic. L'URL rendue par le serveur, elle, ne demarre rien --
     c'est la difference entre une grille et un feed. */
  function embedSrc(url) {
    try {
      const src = new URL(url, window.location.origin);
      src.searchParams.set('autoplay', '1');
      src.searchParams.set('playsinline', '1');
      return src.href;
    } catch (err) {
      // Adresse que le navigateur ne sait pas analyser : on la sert telle
      // quelle plutot que de ne rien afficher.
      return url;
    }
  }

  function open(player) {
    close(playing);

    const url = player.dataset.videoUrl;
    const label = player.dataset.videoLabel || '';
    let media;

    if (player.dataset.videoMode === 'iframe') {
      media = document.createElement('iframe');
      media.src = embedSrc(url);
      media.title = label;
      media.setAttribute('frameborder', '0');
      media.setAttribute('allow', 'autoplay; encrypted-media; picture-in-picture; fullscreen');
      media.setAttribute('referrerpolicy', 'strict-origin-when-cross-origin');
      media.allowFullscreen = true;
    } else {
      media = document.createElement('video');
      media.src = url;
      media.controls = true;
      media.playsInline = true;
      media.setAttribute('aria-label', label);
      // Pas d'attribut `autoplay` : la lecture part du geste de
      // l'utilisateur, ce qui autorise le son (contrairement a un demarrage
      // automatique, que le navigateur n'accepte qu'en muet).
      media.addEventListener('ended', () => close(player));
    }

    media.className = 'cgrid-video';
    media.dataset.cgridMedia = '';
    player.appendChild(media);
    player.classList.add('is-playing');
    playing = player;

    if (media.tagName === 'VIDEO') media.play().catch(() => {});
    media.focus({ preventScroll: true });
  }

  grid.querySelectorAll('[data-cgrid-play]').forEach((button) => {
    button.addEventListener('click', () => open(button.closest('[data-cgrid-player]')));
  });

  // Echap referme la video en cours : on revient a la grille sans avoir a
  // viser une autre carte.
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && playing) {
      const player = playing;
      close(player);
      player.querySelector('[data-cgrid-play]').focus();
    }
  });
})();
