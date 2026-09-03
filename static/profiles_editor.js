/* profiles_editor.js — interface d'edition du profil (section 22).
 *
 * Chaque onglet lit et ecrit directement l'API : il n'y a pas d'etat
 * intermediaire a synchroniser, ce qui evite qu'un onglet affiche des
 * donnees perimees par rapport a ce que le serveur a reellement enregistre.
 * `QAPI` et `qEl` viennent de `questionnaire_common.js`.
 */

(() => {
    const meta = JSON.parse(document.getElementById('p-meta').textContent);
    const choices = (key) => (meta[key] || []).map(o => [o.value, o.label]);

    const save = new QSaveIndicator(
        document.getElementById('p-save'), document.getElementById('p-save-label')
    );

    async function saved(promise) {
        save.set('saving');
        try {
            const result = await promise;
            save.set('saved');
            return result;
        } catch (err) {
            save.set('error', err.message);
            throw err;
        }
    }

    /* --------------------------------------------------------------- */
    /* Onglets                                                            */
    /* --------------------------------------------------------------- */

    const panels = {};
    document.querySelectorAll('.p-tabpanel').forEach(el => { panels[el.id.replace('p-tab-', '')] = el; });
    const loaded = new Set();

    const loaders = {
        general:        renderGeneral,
        skills:         renderSkills,
        experiences:    () => renderList('experiences', experienceFields, '/api/profiles/me/experiences/'),
        education:      () => renderList('education', educationFields, '/api/profiles/me/education/'),
        certifications: () => renderList('certifications', certificationFields, '/api/profiles/me/certifications/'),
        projects:       () => renderList('projects', projectFields, '/api/profiles/me/projects/'),
        languages:      renderLanguages,
        availability:   renderAvailability,
        videos:         renderVideos,
        privacy:        renderPrivacy,
    };

    function activate(tab) {
        document.querySelectorAll('.p-tab').forEach(btn => {
            btn.classList.toggle('p-tab-active', btn.dataset.tab === tab);
        });
        Object.entries(panels).forEach(([name, el]) => { el.hidden = name !== tab; });
        if (!loaded.has(tab)) { loaded.add(tab); loaders[tab](panels[tab]); }
    }

    document.querySelectorAll('.p-tab').forEach(btn => {
        btn.addEventListener('click', () => activate(btn.dataset.tab));
    });
    activate('general');

    /* --------------------------------------------------------------- */
    /* Informations generales + mon profil                                */
    /* --------------------------------------------------------------- */

    async function renderGeneral(root) {
        const { profile } = await QAPI.get('/api/profiles/me/');
        root.innerHTML = '';
        const panel = qEl('div', { class: 'p-panel' });
        root.appendChild(panel);

        const grid = qEl('div', { class: 'p-grid' });

        const patch = (field) => (value) => saved(QAPI.put('/api/profiles/me/', { [field]: value }));

        const photoField = QForm.text('Photo (URL)', profile.photo_url, patch('photo_url'));
        const photoInput = photoField.querySelector('input');

        const avatar = qEl('div', { class: 'p-editor-avatar' });
        function refreshAvatar(url) {
            avatar.style.backgroundImage = url ? `url('${url}')` : 'none';
            avatar.textContent = url ? '' : (profile.first_name || profile.username || '?')[0].toUpperCase();
        }
        refreshAvatar(profile.photo_url);
        photoInput.addEventListener('input', () => refreshAvatar(photoInput.value));

        const photoRow = qEl('div', { class: 'p-editor-photo' }, [
            avatar,
            qEl('a', {
                href: '#', text: 'Modifier la photo',
                onclick: (e) => { e.preventDefault(); photoInput.focus(); },
            }),
        ]);

        panel.append(qEl('h2', { text: 'Informations generales' }), photoRow, grid);

        grid.append(
            QForm.text('Prenom', profile.first_name, patch('first_name')),
            QForm.text('Nom', profile.last_name, patch('last_name')),
            QForm.text('Titre professionnel', profile.headline, patch('headline')),
            QForm.select('Domaine professionnel', profile.professional_field, choices('fields'),
                        patch('professional_field'), { blank: '—' }),
            QForm.text('Ville', profile.location.city, patch('location_city')),
            QForm.text('Region', profile.location.region, patch('location_region')),
            QForm.text('Pays (code ISO)', profile.location.country, patch('location_country'), {
                placeholder: 'FR',
            }),
            photoField,
            QForm.text('Couverture (URL)', profile.cover_url, patch('cover_url')),
        );

        panel.appendChild(qEl('div', { class: 'p-field' }, [
            qEl('label', { text: 'Presentation' }),
            qEl('textarea', {
                text: profile.summary, rows: 6,
                oninput: (e) => { clearTimeout(root._t); root._t = setTimeout(() => patch('summary')(e.target.value), 500); },
            }),
        ]));

        const linksBox = qEl('div', { class: 'p-panel', style: 'background:var(--ground);margin-top:1rem' }, [
            qEl('h3', { text: 'Liens professionnels' }),
        ]);
        panel.appendChild(linksBox);
        await renderLinks(linksBox);
    }

    async function renderLinks(container) {
        const { links } = await QAPI.get('/api/profiles/me/links/');
        const list = qEl('div');
        container.appendChild(list);

        function draw(rows) {
            list.innerHTML = '';
            rows.forEach((row, index) => {
                list.appendChild(qEl('div', { class: 'p-row' }, [
                    qEl('select', {
                        onchange: (e) => { rows[index].kind = e.target.value; commit(rows); },
                    }, choices('link_kinds').map(([v, l]) => qEl('option', { value: v, text: l, selected: v === row.kind }))),
                    qEl('input', {
                        type: 'text', value: row.label, placeholder: 'Libelle', style: 'flex:1 1 8rem',
                        oninput: (e) => { rows[index].label = e.target.value; },
                        onblur: () => commit(rows),
                    }),
                    qEl('input', {
                        type: 'url', value: row.url, placeholder: 'https://…', style: 'flex:2 1 12rem',
                        oninput: (e) => { rows[index].url = e.target.value; },
                        onblur: () => commit(rows),
                    }),
                    qEl('button', {
                        type: 'button', class: 'p-btn small p-danger', text: 'Retirer',
                        onclick: () => { rows.splice(index, 1); commit(rows); },
                    }),
                ]));
            });
            list.appendChild(qEl('button', {
                type: 'button', class: 'p-btn small', text: '+ Ajouter un lien',
                onclick: () => { rows.push({ kind: 'WEBSITE', label: '', url: '' }); draw(rows); },
            }));
        }

        function commit(rows) {
            saved(QAPI.put('/api/profiles/me/links/', { links: rows.map(({ kind, label, url }) => ({ kind, label, url })) }));
        }

        draw(links);
    }

    /* --------------------------------------------------------------- */
    /* Competences                                                        */
    /* --------------------------------------------------------------- */

    async function renderSkills(root) {
        root.innerHTML = '';
        const panel = qEl('div', { class: 'p-panel' });
        root.appendChild(panel);
        panel.appendChild(qEl('h2', { text: 'Competences' }));

        const list = qEl('div');
        panel.appendChild(list);

        async function refresh() {
            const { skills } = await QAPI.get('/api/profiles/me/skills/');
            drawList(skills);
        }

        function drawList(skills) {
            list.innerHTML = '';
            for (const row of skills) {
                list.appendChild(qEl('div', { class: 'p-row' }, [
                    qEl('div', { class: 'p-row-main' }, [qEl('strong', { text: row.skill.name })]),
                    QForm.select('', row.level, choices('skill_levels'), (level) => {
                        saved(QAPI.put(`/api/profiles/me/skills/${row.skill.id}/`, { level }));
                    }, {}),
                    qEl('input', {
                        type: 'number', min: 0, max: 60, value: row.years_experience ?? '',
                        placeholder: 'annees', style: 'width:6rem',
                        onchange: (e) => saved(QAPI.put(`/api/profiles/me/skills/${row.skill.id}/`, {
                            years_experience: e.target.value === '' ? null : Number(e.target.value),
                        })),
                    }),
                    qEl('button', {
                        type: 'button', class: 'p-btn small p-danger', text: 'Retirer',
                        onclick: async () => { await saved(QAPI.del(`/api/profiles/me/skills/${row.skill.id}/`)); refresh(); },
                    }),
                ]));
            }
        }

        const addRow = qEl('div', { class: 'p-add-row' });
        panel.appendChild(addRow);

        const input = qEl('input', { type: 'text', placeholder: 'Ajouter une competence (Java, Docker…)' });
        const suggest = qEl('div', { class: 'p-suggest', hidden: true, style: 'position:absolute' });
        const wrap = qEl('div', { style: 'position:relative;flex:1 1 14rem' }, [input, suggest]);

        let timer = null;
        input.addEventListener('input', () => {
            clearTimeout(timer);
            const term = input.value.trim();
            if (!term) { suggest.hidden = true; return; }
            timer = setTimeout(async () => {
                const { skills } = await QAPI.get(`/api/skills/?q=${encodeURIComponent(term)}&limit=8`);
                suggest.innerHTML = '';
                for (const skill of skills) {
                    suggest.appendChild(qEl('button', {
                        type: 'button', text: skill.name,
                        onclick: () => addSkill(skill.name),
                    }));
                }
                suggest.hidden = skills.length === 0;
            }, 150);
        });
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && input.value.trim()) { e.preventDefault(); addSkill(input.value.trim()); }
        });

        async function addSkill(name) {
            input.value = '';
            suggest.hidden = true;
            await saved(QAPI.post('/api/profiles/me/skills/', { name, level: 'BEGINNER' }));
            refresh();
        }

        addRow.append(wrap, qEl('button', {
            type: 'button', class: 'p-btn p-primary', text: 'Ajouter',
            onclick: () => input.value.trim() && addSkill(input.value.trim()),
        }));

        await refresh();
    }

    /* --------------------------------------------------------------- */
    /* Sections en liste : experiences, formations, certifications, projets */
    /* --------------------------------------------------------------- */

    const experienceFields = () => [
        { key: 'title', label: 'Poste', kind: 'text', required: true },
        { key: 'company', label: 'Entreprise', kind: 'text', required: true },
        { key: 'location_city', label: 'Ville', kind: 'text' },
        { key: 'contract_type', label: 'Contrat', kind: 'select', choices: choices('contract_types'), blank: '—' },
        { key: 'start_date', label: 'Debut', kind: 'date', required: true },
        { key: 'end_date', label: 'Fin', kind: 'date' },
        { key: 'is_current', label: 'Poste actuel', kind: 'bool' },
        { key: 'description', label: 'Description', kind: 'textarea' },
        { key: 'skills', label: 'Competences utilisees', kind: 'skills' },
    ];

    const educationFields = () => [
        { key: 'institution', label: 'Etablissement', kind: 'text', required: true },
        { key: 'degree', label: 'Diplome', kind: 'text' },
        { key: 'degree_level', label: 'Niveau', kind: 'select', choices: choices('degree_levels'), blank: '—' },
        { key: 'field_of_study', label: 'Domaine', kind: 'text' },
        { key: 'start_date', label: 'Debut', kind: 'date', required: true },
        { key: 'end_date', label: 'Fin', kind: 'date' },
        { key: 'is_current', label: 'Formation actuelle', kind: 'bool' },
        { key: 'diploma_url', label: 'Preuve du diplome (URL)', kind: 'text' },
        { key: 'description', label: 'Description', kind: 'textarea' },
        { key: 'skills', label: 'Competences associees', kind: 'skills' },
    ];

    const certificationFields = () => [
        { key: 'name', label: 'Nom', kind: 'text', required: true },
        { key: 'issuer', label: 'Organisme', kind: 'text' },
        { key: 'issued_on', label: "Date d'obtention", kind: 'date' },
        { key: 'expires_on', label: 'Expiration', kind: 'date' },
        { key: 'credential_id', label: 'Identifiant', kind: 'text' },
        { key: 'verification_url', label: 'URL de verification', kind: 'text' },
        { key: 'skills', label: 'Competences associees', kind: 'skills' },
    ];

    const projectFields = () => [
        { key: 'title', label: 'Titre', kind: 'text', required: true },
        { key: 'role', label: 'Role', kind: 'text' },
        { key: 'url', label: 'Lien', kind: 'text' },
        { key: 'started_on', label: 'Debut', kind: 'date' },
        { key: 'ended_on', label: 'Fin', kind: 'date' },
        { key: 'description', label: 'Description', kind: 'textarea' },
        { key: 'skills', label: 'Competences utilisees', kind: 'skills' },
    ];

    async function renderList(name, fieldsFn, url) {
        const root = panels[name];
        root.innerHTML = '';
        const panel = qEl('div', { class: 'p-panel' });
        root.appendChild(panel);

        const titles = {
            experiences: 'Experiences', education: 'Formations',
            certifications: 'Certifications', projects: 'Projets',
        };
        panel.appendChild(qEl('h2', { text: titles[name] }));

        const list = qEl('div');
        const addPanel = qEl('div', { class: 'p-add-row', style: 'display:block' });
        panel.append(list, qEl('h3', { text: 'Ajouter', style: 'margin-top:1rem' }), addPanel);

        async function refresh() {
            const payload = await QAPI.get(url);
            const rows = payload[name];
            list.innerHTML = '';
            for (const row of rows) list.appendChild(renderEntry(row));
        }

        function renderEntry(row) {
            const box = qEl('div', { class: 'p-panel', style: 'background:var(--ground);margin-bottom:.75rem' });
            const form = qEl('div', { class: 'p-grid' });
            const skillsBox = qEl('div');
            const draft = { ...row };

            for (const field of fieldsFn()) {
                if (field.kind === 'skills') continue;
                if (field.kind === 'textarea') continue;
                form.appendChild(buildField(field, row[field.key], (value) => {
                    draft[field.key] = value;
                    save.set('saving');
                    saved(QAPI.put(`${url}${row.id}/`, { [field.key]: value })).then(refresh);
                }));
            }
            box.appendChild(form);

            const textField = fieldsFn().find(f => f.kind === 'textarea');
            if (textField) {
                let timer = null;
                box.appendChild(qEl('div', { class: 'p-field' }, [
                    qEl('label', { text: textField.label }),
                    qEl('textarea', {
                        text: row[textField.key] || '', rows: 3,
                        oninput: (e) => {
                            clearTimeout(timer);
                            const value = e.target.value;
                            timer = setTimeout(() => saved(QAPI.put(`${url}${row.id}/`, { [textField.key]: value })), 500);
                        },
                    }),
                ]));
            }

            box.appendChild(renderSkillPicker(row.skills || [], (names) => {
                saved(QAPI.put(`${url}${row.id}/`, { skills: names }));
            }));

            box.appendChild(qEl('div', { class: 'p-actions end', style: 'margin-top:.5rem' }, [
                qEl('button', {
                    type: 'button', class: 'p-btn small p-danger', text: 'Supprimer',
                    onclick: async () => { await saved(QAPI.del(`${url}${row.id}/`)); refresh(); },
                }),
            ]));

            return box;
        }

        function buildForCreate() {
            addPanel.innerHTML = '';
            const draft = {};
            const form = qEl('div', { class: 'p-grid' });
            for (const field of fieldsFn()) {
                if (field.kind === 'skills' || field.kind === 'textarea') continue;
                form.appendChild(buildField(field, draft[field.key], (value) => { draft[field.key] = value; }));
            }
            addPanel.appendChild(form);

            const textField = fieldsFn().find(f => f.kind === 'textarea');
            let textarea = null;
            if (textField) {
                textarea = qEl('textarea', { rows: 3 });
                addPanel.appendChild(qEl('div', { class: 'p-field' }, [
                    qEl('label', { text: textField.label }), textarea,
                ]));
            }

            let skillNames = [];
            addPanel.appendChild(renderSkillPicker([], (names) => { skillNames = names; }));

            addPanel.appendChild(qEl('button', {
                type: 'button', class: 'p-btn p-primary', text: 'Ajouter', style: 'margin-top:.75rem',
                onclick: async () => {
                    const payload = { ...draft, skills: skillNames };
                    if (textField) payload[textField.key] = textarea.value;
                    try {
                        await saved(QAPI.post(url, payload));
                        buildForCreate();
                        refresh();
                    } catch (err) { /* deja affiche par l'indicateur */ }
                },
            }));
        }

        buildForCreate();
        await refresh();
    }

    function buildField(field, value, onChange) {
        const opts = { required: field.required };
        switch (field.kind) {
            case 'select': return QForm.select(field.label, value, field.choices, onChange, { ...opts, blank: field.blank });
            case 'date':   return QForm.text(field.label, value, onChange, { ...opts, type: 'date' });
            case 'bool':   return QForm.check(field.label, value, onChange, opts);
            default:       return QForm.text(field.label, value, onChange, opts);
        }
    }

    function renderSkillPicker(initial, onChange) {
        const names = [...initial.map(s => s.name || s)];
        const tokens = qEl('div', { class: 'p-tokens' });
        const input = qEl('input', { type: 'text', placeholder: 'Ajouter une competence' , style: 'max-width:16rem'});

        function draw() {
            tokens.innerHTML = '';
            names.forEach((name, index) => {
                tokens.appendChild(qEl('span', { class: 'p-token' }, [
                    name, qEl('button', { type: 'button', text: '×',
                                          onclick: () => { names.splice(index, 1); draw(); onChange(names); } }),
                ]));
            });
        }
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && input.value.trim()) {
                e.preventDefault();
                names.push(input.value.trim());
                input.value = '';
                draw();
                onChange(names);
            }
        });
        draw();
        return qEl('div', { class: 'p-field' }, [
            qEl('label', { text: 'Competences' }), tokens, input,
        ]);
    }

    /* --------------------------------------------------------------- */
    /* Langues                                                            */
    /* --------------------------------------------------------------- */

    async function renderLanguages(root) {
        root.innerHTML = '';
        const panel = qEl('div', { class: 'p-panel' });
        root.appendChild(panel);
        panel.appendChild(qEl('h2', { text: 'Langues' }));

        const { languages: catalog } = await QAPI.get('/api/languages/');
        const list = qEl('div');
        panel.appendChild(list);

        async function refresh() {
            const { languages } = await QAPI.get('/api/profiles/me/languages/');
            list.innerHTML = '';
            for (const row of languages) {
                list.appendChild(qEl('div', { class: 'p-row' }, [
                    qEl('div', { class: 'p-row-main' }, [qEl('strong', { text: row.name })]),
                    QForm.select('', row.level, choices('language_levels'), (level) => {
                        saved(QAPI.post('/api/profiles/me/languages/', { language: row.code, level }));
                    }, {}),
                    qEl('button', {
                        type: 'button', class: 'p-btn small p-danger', text: 'Retirer',
                        onclick: async () => { await saved(QAPI.del(`/api/profiles/me/languages/${row.id}/`)); refresh(); },
                    }),
                ]));
            }
        }

        const codeSelect = qEl('select', {}, [
            qEl('option', { value: '', text: 'Choisir une langue' }),
            ...catalog.map(l => qEl('option', { value: l.code, text: l.name })),
        ]);
        const levelSelect = qEl('select', {}, choices('language_levels').map(([v, l]) => qEl('option', { value: v, text: l })));
        panel.appendChild(qEl('div', { class: 'p-add-row' }, [
            codeSelect, levelSelect,
            qEl('button', {
                type: 'button', class: 'p-btn p-primary', text: 'Ajouter',
                onclick: async () => {
                    if (!codeSelect.value) return;
                    await saved(QAPI.post('/api/profiles/me/languages/', { language: codeSelect.value, level: levelSelect.value }));
                    refresh();
                },
            }),
        ]));

        await refresh();
    }

    /* --------------------------------------------------------------- */
    /* Disponibilite                                                      */
    /* --------------------------------------------------------------- */

    async function renderAvailability(root) {
        const { profile, availability } = await QAPI.get('/api/profiles/me/');
        root.innerHTML = '';
        const panel = qEl('div', { class: 'p-panel' });
        root.appendChild(panel);
        panel.appendChild(qEl('h2', { text: 'Disponibilite' }));

        const patch = (field) => (value) => saved(QAPI.put('/api/profiles/me/', { [field]: value }));
        const grid = qEl('div', { class: 'p-grid' });
        panel.appendChild(grid);

        grid.append(
            QForm.select('Statut', profile.availability_status, choices('availability'), patch('availability_status')),
            QForm.text('Disponible a partir du', profile.available_from, patch('available_from'), { type: 'date' }),
        );

        panel.append(
            qEl('div', { class: 'p-label', text: 'Mode de travail', style: 'margin-bottom:.5rem' }),
            qEl('div', { class: 'q-field-group' }, ['REMOTE', 'HYBRID', 'ONSITE'].map((mode, i) => QForm.check(
                choices('work_modes')[i][1], availability.work_modes.includes(mode),
                (checked) => patch({ REMOTE: 'open_to_remote', HYBRID: 'open_to_hybrid', ONSITE: 'open_to_onsite' }[mode])(checked),
            ))),
        );

        panel.append(
            qEl('div', { class: 'p-label', text: 'Types de contrat recherches', style: 'margin-bottom:.5rem' }),
            qEl('div', { class: 'q-field-group' }, choices('contract_types').map(([value, label]) => QForm.check(
                label, availability.contract_types.includes(value),
                async (checked) => {
                    const current = new Set(availability.contract_types);
                    checked ? current.add(value) : current.delete(value);
                    availability.contract_types = [...current];
                    await saved(QAPI.put('/api/profiles/me/', { contract_types: [...current] }));
                },
            ))),
        );

        grid.append(
            QForm.check('Mobile geographiquement', profile.willing_to_relocate, patch('willing_to_relocate')),
            QForm.number('Rayon de mobilite (km)', profile.mobility_radius_km, patch('mobility_radius_km')),
        );
        panel.appendChild(QForm.text('Note de mobilite', profile.mobility_note, patch('mobility_note')));
    }

    /* --------------------------------------------------------------- */
    /* Videos                                                             */
    /* --------------------------------------------------------------- */

    /* section 1 : statut -> ce que l'utilisateur voit, et ce qu'il peut
     * encore faire depuis cet etat. Les badges reprennent les couleurs
     * deja utilisees ailleurs dans l'app (.p-ok/.p-info/.p-warn/.p-ko). */
    const VIDEO_STATUS_LABELS = {
        PENDING:   ['En attente de moderation', 'p-warn'],
        APPROVED:  ['Validee', 'p-info'],
        PUBLISHED: ['Publiee', 'p-ok'],
        REJECTED:  ['Refusee', 'p-ko'],
        HIDDEN:    ['Masquee', 'p-badge'],
        DRAFT:     ['Brouillon', 'p-badge'],
        PROCESSING: ['En traitement', 'p-badge'],
    };

    async function renderVideos(root) {
        root.innerHTML = '';
        const panel = qEl('div', { class: 'p-panel' });
        root.appendChild(panel);
        panel.appendChild(qEl('h2', { text: 'Videos' }));
        panel.appendChild(qEl('p', { class: 'p-help' }, [
            'Une video soumise par lien passe en moderation avant de pouvoir etre ',
            "publiee : sa validation ne la rend jamais publique toute seule, c'est ",
            'a vous de le confirmer une fois validee.',
        ]));

        const list = qEl('div');
        panel.appendChild(list);

        async function refresh() {
            const { videos } = await QAPI.get('/api/profiles/me/videos/');
            list.innerHTML = '';
            if (!videos.length) list.appendChild(qEl('p', { class: 'p-empty', text: 'Aucune video pour le moment.' }));
            for (const video of videos) {
                const [label, badgeClass] = VIDEO_STATUS_LABELS[video.status] || [video.status, 'p-badge'];
                const rowChildren = [
                    qEl('strong', { text: video.title }),
                    qEl('div', { class: 'p-badge ' + badgeClass, text: label }),
                ];
                if (video.status === 'REJECTED' && video.rejection_reason) {
                    rowChildren.push(qEl('div', { class: 'p-muted', text: 'Motif : ' + video.rejection_reason }));
                }

                const actions = [];
                if (video.requires_user_action === 'CONFIRM_PUBLICATION') {
                    actions.push(qEl('button', {
                        type: 'button', class: 'p-btn small p-primary', text: 'Publier',
                        onclick: async () => {
                            await saved(QAPI.post(`/api/profiles/me/videos/${video.id}/publish/`, {}));
                            refresh();
                        },
                    }));
                }
                if (video.status === 'REJECTED') {
                    actions.push(qEl('button', {
                        type: 'button', class: 'p-btn small', text: 'Re-soumettre',
                        onclick: async () => {
                            await saved(QAPI.post(`/api/profiles/me/videos/${video.id}/resubmit/`, {}));
                            refresh();
                        },
                    }));
                }
                actions.push(qEl('button', {
                    type: 'button', class: 'p-btn small p-danger', text: 'Supprimer',
                    onclick: async () => { await saved(QAPI.del(`/api/profiles/me/videos/${video.id}/`)); refresh(); },
                }));

                list.appendChild(qEl('div', { class: 'p-row' }, [
                    qEl('div', { class: 'p-row-main' }, rowChildren),
                    qEl('div', { class: 'p-actions' }, actions),
                ]));
            }
        }

        const titleInput = qEl('input', { type: 'text', placeholder: 'Titre de la video' });
        const urlInput   = qEl('input', { type: 'url', placeholder: 'https://exemple.com/ma-video.mp4' });
        let skillNames = [];
        panel.appendChild(qEl('div', { class: 'p-add-row', style: 'display:block' }, [
            qEl('div', { class: 'p-field' }, [qEl('label', { text: 'Titre' }), titleInput]),
            qEl('div', { class: 'p-field' }, [qEl('label', { text: 'Lien de la video' }), urlInput]),
            renderSkillPicker([], (names) => { skillNames = names; }),
            qEl('button', {
                type: 'button', class: 'p-btn p-primary', text: 'Soumettre a la moderation', style: 'margin-top:.5rem',
                onclick: async () => {
                    if (!titleInput.value.trim() || !urlInput.value.trim()) return;
                    await saved(QAPI.post('/api/profiles/me/videos/', {
                        title: titleInput.value.trim(), file_url: urlInput.value.trim(), skills: skillNames,
                    }));
                    titleInput.value = '';
                    urlInput.value = '';
                    refresh();
                },
            }),
        ]));

        await refresh();
    }

    /* --------------------------------------------------------------- */
    /* Confidentialite                                                    */
    /* --------------------------------------------------------------- */

    async function renderPrivacy(root) {
        const settings = await QAPI.get('/api/profiles/me/privacy/');
        root.innerHTML = '';
        const panel = qEl('div', { class: 'p-panel' });
        root.appendChild(panel);
        panel.appendChild(qEl('h2', { text: 'Confidentialite' }));

        function patch(payload) { return saved(QAPI.put('/api/profiles/me/privacy/', payload)); }

        panel.appendChild(QForm.select('Visibilite du profil', settings.profile_visibility, choices('visibilities'),
            (value) => patch({ profile_visibility: value }),
            { help: "Qui peut ouvrir la page de votre profil." }));

        panel.appendChild(qEl('h3', { text: 'Visibilite par section', style: 'margin-top:1.25rem' }));
        panel.appendChild(qEl('p', { class: 'p-help' },
            "Une section ne peut jamais etre plus ouverte que le profil lui-meme."));
        const sectionGrid = qEl('div', { class: 'p-grid' });
        panel.appendChild(sectionGrid);
        for (const [key, label] of choices('sections')) {
            sectionGrid.appendChild(QForm.select(label, settings.sections[key], choices('visibilities'),
                (value) => patch({ sections: { [key]: value } })));
        }

        panel.appendChild(qEl('h3', { text: 'Recherche', style: 'margin-top:1.25rem' }));
        panel.appendChild(QForm.check('Apparaitre dans les resultats de recherche', settings.search.searchable,
            (checked) => patch({ search: { searchable: checked } }),
            { help: "Un profil peut etre public et refuser d'apparaitre dans les recherches." }));
        panel.appendChild(QForm.check("Afficher ma disponibilite dans les resultats", settings.search.show_availability_in_results,
            (checked) => patch({ search: { show_availability_in_results: checked } })));
        panel.appendChild(QForm.check('Etre contactable par les recruteurs', settings.search.contactable_by_recruiters,
            (checked) => patch({ search: { contactable_by_recruiters: checked } })));
    }
})();
