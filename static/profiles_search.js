/* profiles_search.js — page de recherche de profils.
 *
 * Le JavaScript ne filtre rien : il construit une requete, l'envoie a
 * `/api/profiles/search/` et affiche ce que le serveur renvoie deja trie,
 * pagine et classe. `QAPI` et `qEl` viennent de `questionnaire_common.js`.
 */

(() => {
    const state = {
        skills: [],       // [{id, name}]
        page: 1,
    };

    const els = {
        tokens:   document.getElementById('p-skill-tokens'),
        input:    document.getElementById('p-skill-input'),
        suggest:  document.getElementById('p-skill-suggest'),
        form:     document.getElementById('p-search-form'),
        count:    document.getElementById('p-count'),
        results:  document.getElementById('p-results'),
        pagination: document.getElementById('p-pagination'),
        reset:    document.getElementById('p-reset'),
        language: document.getElementById('f-language'),
    };

    /* --------------------------------------------------------------- */
    /* Autocompletion des competences                                    */
    /* --------------------------------------------------------------- */

    let suggestTimer = null;

    els.input.addEventListener('input', () => {
        clearTimeout(suggestTimer);
        const term = els.input.value.trim();
        if (!term) { els.suggest.hidden = true; return; }
        suggestTimer = setTimeout(async () => {
            const { skills } = await QAPI.get(`/api/skills/?q=${encodeURIComponent(term)}&limit=8`);
            renderSuggestions(skills.filter(s => !state.skills.some(x => x.id === s.id)));
        }, 150);
    });

    function renderSuggestions(skills) {
        els.suggest.innerHTML = '';
        if (!skills.length) { els.suggest.hidden = true; return; }
        for (const skill of skills) {
            els.suggest.appendChild(qEl('button', {
                type: 'button', text: skill.name,
                onclick: () => addSkill(skill),
            }));
        }
        els.suggest.hidden = false;
    }

    els.input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && els.input.value.trim()) {
            e.preventDefault();
            addSkill({ id: null, name: els.input.value.trim() });
        }
    });

    document.addEventListener('click', (e) => {
        if (!els.suggest.contains(e.target) && e.target !== els.input) els.suggest.hidden = true;
    });

    function addSkill(skill) {
        if (state.skills.some(s => s.name.toLowerCase() === skill.name.toLowerCase())) return;
        state.skills.push(skill);
        els.input.value = '';
        els.suggest.hidden = true;
        renderTokens();
        runSearch();
    }

    function removeSkill(index) {
        state.skills.splice(index, 1);
        renderTokens();
        runSearch();
    }

    function renderTokens() {
        els.tokens.innerHTML = '';
        state.skills.forEach((skill, index) => {
            els.tokens.appendChild(qEl('span', { class: 'p-token' }, [
                skill.name,
                qEl('button', { type: 'button', text: '×', 'aria-label': `Retirer ${skill.name}`,
                               onclick: () => removeSkill(index) }),
            ]));
        });
    }

    /* --------------------------------------------------------------- */
    /* Referentiel de langues, pour le filtre                            */
    /* --------------------------------------------------------------- */

    QAPI.get('/api/languages/').then(({ languages }) => {
        for (const lang of languages) {
            els.language.appendChild(qEl('option', { value: lang.code, text: lang.name }));
        }
        const initial = JSON.parse(document.getElementById('p-initial-languages').textContent);
        if (initial.length) els.language.value = initial[0];
    }).catch(() => {});

    /* --------------------------------------------------------------- */
    /* Construction de la requete                                        */
    /* --------------------------------------------------------------- */

    function buildParams() {
        const params = new URLSearchParams();

        for (const skill of state.skills) params.append('skill', skill.name);
        const mode = document.getElementById('f-mode').value;
        if (mode) params.set('mode', mode);

        const text = document.getElementById('p-text').value.trim();
        if (text) params.set('q', text);

        const minLevel = document.getElementById('f-min_level').value;
        if (minLevel) params.set('min_level', minLevel);
        const minYears = document.getElementById('f-min_years').value;
        if (minYears) params.set('min_years', minYears);

        if (document.getElementById('f-available').checked) params.set('available', '1');

        document.querySelectorAll('input[name="contract"]:checked')
            .forEach(el => params.append('contract', el.value));
        document.querySelectorAll('input[name="work_mode"]:checked')
            .forEach(el => params.append('work_mode', el.value));

        const field = document.getElementById('f-field').value;
        if (field) params.set('field', field);
        const city = document.getElementById('f-city').value.trim();
        if (city) params.set('city', city);
        const country = document.getElementById('f-country').value.trim();
        if (country) params.set('country', country);

        const minExp = document.getElementById('f-min_experience_years').value;
        if (minExp) params.set('min_experience_years', minExp);
        const minDegree = document.getElementById('f-min_degree_level').value;
        if (minDegree) params.set('min_degree_level', minDegree);

        const language = els.language.value;
        if (language) params.set('language', language);
        const minLang = document.getElementById('f-min_language_level').value;
        if (minLang) params.set('min_language_level', minLang);

        params.set('sort', document.getElementById('f-sort').value || 'relevance');
        params.set('page', String(state.page));
        return params;
    }

    /* --------------------------------------------------------------- */
    /* Recherche et affichage                                            */
    /* --------------------------------------------------------------- */

    let searchTimer = null;

    function scheduleSearch() {
        clearTimeout(searchTimer);
        searchTimer = setTimeout(runSearch, 250);
    }

    async function runSearch() {
        state.page = state.page || 1;
        els.count.textContent = 'Recherche…';
        let payload;
        try {
            payload = await QAPI.get(`/api/profiles/search/?${buildParams().toString()}`);
        } catch (err) {
            els.count.textContent = err.message || 'Erreur de recherche.';
            els.results.innerHTML = '';
            return;
        }
        renderResults(payload);
    }

    function renderResults({ results, pagination }) {
        const total = pagination.total;
        els.count.textContent = total
            ? `${total} profil${total > 1 ? 's' : ''} trouve${total > 1 ? 's' : ''}`
            : 'Aucun profil ne correspond a ces criteres.';

        els.results.innerHTML = '';
        for (const card of results) els.results.appendChild(renderCard(card));
        renderPagination(pagination);
    }

    function renderCard(card) {
        const initials = (card.full_name || card.username).split(' ')
            .slice(0, 2).map(p => p[0]).join('').toUpperCase();

        const avatar = qEl('div', { class: 'p-avatar-sm' },
            card.photo_url ? qEl('img', { src: card.photo_url, alt: '' }) : initials);

        const metaBits = [];
        if (card.location) metaBits.push(card.location);
        if (card.professional_field) metaBits.push(card.professional_field);
        if (card.total_experience_years) metaBits.push(`${card.total_experience_years} ans d'experience`);

        const body = qEl('div', { class: 'p-result-body' }, [
            qEl('h3', {}, [qEl('a', { href: card.url, text: card.full_name || card.username })]),
            card.headline ? qEl('p', { class: 'p-muted', text: card.headline, style: 'margin:.15rem 0' }) : null,
            qEl('p', { class: 'p-result-meta', text: metaBits.join(' · ') }),
            card.skills ? renderSkillChips(card.skills) : null,
        ]);

        const side = qEl('div', { class: 'p-result-side' }, [
            card.match && card.match.requested
                ? qEl('span', { class: 'p-match', text: `${card.match.skills}/${card.match.requested} competences` })
                : null,
            card.availability
                ? qEl('span', { class: `p-badge ${card.availability.is_available ? 'p-ok' : 'p-info'}`,
                               text: card.availability.status_label })
                : null,
        ]);

        return qEl('article', { class: 'p-result' }, [avatar, body, side]);
    }

    function renderSkillChips(skills) {
        return qEl('div', { class: 'p-skills', style: 'margin-top:.5rem' },
            skills.slice(0, 6).map(s => qEl('span', { class: 'p-skill', text: s.skill.name })));
    }

    function renderPagination({ page, pages, has_previous, has_next }) {
        els.pagination.innerHTML = '';
        if (pages <= 1) return;
        els.pagination.appendChild(qEl('button', {
            class: 'p-btn small', text: '← Precedent', disabled: !has_previous,
            onclick: () => { state.page = page - 1; runSearch(); window.scrollTo(0, 0); },
        }));
        els.pagination.appendChild(qEl('span', { class: 'p-page', text: `Page ${page} sur ${pages}` }));
        els.pagination.appendChild(qEl('button', {
            class: 'p-btn small', text: 'Suivant →', disabled: !has_next,
            onclick: () => { state.page = page + 1; runSearch(); window.scrollTo(0, 0); },
        }));
    }

    /* --------------------------------------------------------------- */
    /* Cablage                                                            */
    /* --------------------------------------------------------------- */

    els.form.addEventListener('submit', (e) => { e.preventDefault(); state.page = 1; runSearch(); });
    document.querySelectorAll('.p-filters select, .p-filters input')
        .forEach(el => el.addEventListener('change', () => { state.page = 1; scheduleSearch(); }));

    els.reset.addEventListener('click', () => {
        state.skills = [];
        state.page = 1;
        renderTokens();
        document.querySelectorAll('.p-filters select').forEach(el => { el.selectedIndex = 0; });
        document.querySelectorAll('.p-filters input[type="checkbox"]').forEach(el => { el.checked = false; });
        document.querySelectorAll('.p-filters input[type="text"], .p-filters input[type="number"]')
            .forEach(el => { el.value = ''; });
        document.getElementById('p-text').value = '';
        runSearch();
    });

    /* --------------------------------------------------------------- */
    /* Reprise d'une recherche partagee par URL                          */
    /*                                                                   */
    /* Les selects et champs texte sont deja pre-remplis cote serveur    */
    /* (attribut `selected`/`value` dans le template) ; ce qui manque au */
    /* rendu HTML, ce sont les jetons de competence et les cases a       */
    /* cocher, que ce bloc restaure avant le premier appel a l'API.      */
    /* --------------------------------------------------------------- */

    function hydrateFromUrl() {
        const query = JSON.parse(document.getElementById('p-initial-query').textContent);
        const skills = JSON.parse(document.getElementById('p-initial-skills').textContent);

        state.skills = skills;
        renderTokens();

        for (const value of query.contracts || []) {
            const el = document.querySelector(`input[name="contract"][value="${value}"]`);
            if (el) el.checked = true;
        }
        for (const value of query.work_modes || []) {
            const el = document.querySelector(`input[name="work_mode"][value="${value}"]`);
            if (el) el.checked = true;
        }
        if (query.available) document.getElementById('f-available').checked = true;
        state.page = query.page || 1;
    }

    hydrateFromUrl();
    runSearch();
})();
