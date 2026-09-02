/* questionnaire_editor.js — editeur de questionnaire.
 *
 * Principe : l'administrateur ne voit jamais de JSON. Chaque type de question
 * decrit ses propres champs via /api/questionnaires/types/, et l'editeur en
 * construit un vrai formulaire, avec libelles, aide et exemples.
 *
 * Le JSON reste accessible dans un bloc « Reglages avances » replie, pour les
 * cas que le formulaire ne couvre pas.
 */

const CONDITION_OPS = [
    ['EQUALS',       'est egale a'],
    ['NOT_EQUALS',   "n'est pas egale a"],
    ['CONTAINS',     'contient'],
    ['NOT_CONTAINS', 'ne contient pas'],
    ['GT',           'est superieure a'],
    ['GTE',          'est superieure ou egale a'],
    ['LT',           'est inferieure a'],
    ['LTE',          'est inferieure ou egale a'],
    ['ANSWERED',     'a recu une reponse'],
    ['NOT_ANSWERED', "n'a pas recu de reponse"],
];

const OPLESS = ['ANSWERED', 'NOT_ANSWERED'];

/* Lit et ecrit une valeur derriere un chemin pointe, par exemple value.country. */
function qGet(object, path) {
    return path.split('.').reduce((o, k) => (o === null || o === undefined ? undefined : o[k]), object);
}
function qSet(object, path, value) {
    const keys = path.split('.');
    const last = keys.pop();
    let node = object;
    for (const key of keys) {
        if (node[key] === null || typeof node[key] !== 'object') node[key] = {};
        node = node[key];
    }
    if (value === null || value === '' || value === undefined) delete node[last];
    else node[last] = value;
}
function qHasValue(rule, fields) {
    return fields.some(f => {
        const v = qGet(rule, f.path);
        return f.multiple ? (v || []).length : (v !== undefined && v !== null && v !== '');
    });
}


class QuestionnaireEditor {

    constructor(root) {
        this.id        = Number(root.dataset.questionnaire);
        this.indicator = new QSaveIndicator(
            document.getElementById('q-save-state'),
            document.getElementById('q-save-label'));
        this.open = new Set();          // questions depliees
        this.bindChrome();
        this.load();
    }

    base()    { return `/api/questionnaires/${this.id}`; }
    version() { return `${this.base()}/versions/${this.draft.version_number}`; }
    get editable() { return this.draft.is_editable; }

    /* ------------------------------------------------------------------ */
    /* Chargement                                                          */
    /* ------------------------------------------------------------------ */

    async load() {
        const [detail, types] = await Promise.all([
            QAPI.get(`${this.base()}/`),
            QAPI.get('/api/questionnaires/types/'),
        ]);

        this.questionnaire = detail.questionnaire;
        this.capabilities  = detail.capabilities;
        this.types         = types.types;
        this.families      = types.families;
        this.typeById      = Object.fromEntries(types.types.map(t => [t.id, t]));

        const versions = this.questionnaire.versions;
        const target = versions.find(v => v.is_editable)
                    || versions.find(v => v.status === 'DRAFT')
                    || versions[0];
        this.draft = (await QAPI.get(`${this.base()}/versions/${target.version_number}/`)).version;

        document.getElementById('q-title').textContent = this.questionnaire.title;
        /* on remplit un emplacement stable : `replaceWith` supprimait l'element
           cible, et le rechargement suivant echouait silencieusement */
        document.getElementById('q-status-slot')
            .replaceChildren(qStatus(this.questionnaire.status));
        document.getElementById('q-version').textContent = `version ${this.draft.version_number}`;
        document.getElementById('q-preview').href =
            `/questionnaires/manage/${this.id}/preview/${this.draft.version_number}/`;

        document.getElementById('q-locked-note').hidden   = this.editable;
        document.getElementById('q-questions-intro').hidden = !this.editable;

        this.fillTypeSelect();
        this.renderQuestions();
        this.renderSettings();
        this.renderScoring();
        /* ces trois-la interrogent le serveur : sans `await`, l'ecran affiche
           encore l'etat precedent quand le rechargement rend la main */
        await Promise.all([this.renderAccess(), this.renderHistory(), this.renderPublish()]);
        this.indicator.set('idle');
    }

    /* Recharge la version courante.
       Le panneau de publication depend du contenu (nombre de questions,
       questions notees) : il doit etre rejoue a chaque modification, sinon le
       bouton « Publier » reste desactive jusqu'au rechargement de la page. */
    async reloadVersion() {
        this.draft = (await QAPI.get(`${this.version()}/`)).version;
        this.renderQuestions();
        await this.renderPublish();
    }

    /* ------------------------------------------------------------------ */
    /* Chrome : onglets et actions globales                                */
    /* ------------------------------------------------------------------ */

    bindChrome() {
        document.querySelectorAll('.q-tab').forEach(tab => {
            tab.addEventListener('click', () => this.showTab(tab.dataset.tab));
        });
        if (location.hash) this.showTab(location.hash.slice(1));

        document.getElementById('q-add-question').addEventListener('click', () => this.addQuestion());
        document.getElementById('q-new-text').addEventListener('keydown', (e) => {
            if (e.key === 'Enter') { e.preventDefault(); this.addQuestion(); }
        });
        document.getElementById('q-new-type').addEventListener('change', () => this.showTypeHint());
        document.getElementById('q-make-editable').addEventListener('click', () => this.makeEditable());

        this.on('q-publish', () => this.publish());
        this.on('q-to-test', () => this.confirmAction(
            'test', 'Mettre cette version en test ?',
            'Seuls les testeurs autorises pourront la passer. La version sera figee.'));
        this.on('q-export', () => this.exportJson());
    }

    showTab(name) {
        document.querySelectorAll('.q-tab').forEach(t =>
            t.classList.toggle('q-tab-active', t.dataset.tab === name));
        document.querySelectorAll('.q-tabpane').forEach(p => p.hidden = p.dataset.pane !== name);
    }

    on(id, handler) {
        const node = document.getElementById(id);
        if (node) node.addEventListener('click', handler);
    }

    async guard(action, message) {
        this.indicator.set('saving');
        this.footerError('');
        try {
            const result = await action();
            this.indicator.set('saved', message);
            return result;
        } catch (error) {
            this.indicator.set('error', error.message);
            this.footerError(error.message);
            throw error;
        }
    }

    /* Le pied de page est colle en bas : l'erreur doit s'afficher la, a cote du
       bouton cliquez, et pas seulement dans l'indicateur en haut de page. */
    footerError(message) {
        const node = document.getElementById('q-footer-error');
        if (node) node.textContent = message;
    }

    async confirmAction(action, title, detail) {
        if (!confirm(`${title}\n\n${detail}`)) return;
        try {
            await this.guard(() => QAPI.post(`${this.version()}/${action}/`, {}));
            await this.load();
        } catch (_) { /* l'indicateur porte deja le message */ }
    }

    async makeEditable() {
        await this.guard(() => QAPI.post(`${this.base()}/versions/editable/`, {}),
                         'Nouvelle version creee');
        await this.load();
    }

    /* ------------------------------------------------------------------ */
    /* Ajout d'une question                                                */
    /* ------------------------------------------------------------------ */

    fillTypeSelect() {
        const select = document.getElementById('q-new-type');
        select.replaceChildren();
        const grouped = {};
        this.types.forEach(t => (grouped[t.family] = grouped[t.family] || []).push(t));

        for (const [family, types] of Object.entries(grouped)) {
            const group = qEl('optgroup', { label: this.families[family] || family });
            types.forEach(t => group.appendChild(qEl('option', { value: t.id, text: t.label })));
            select.appendChild(group);
        }
        select.disabled = !this.editable;
        document.getElementById('q-new-text').disabled = !this.editable;
        document.getElementById('q-add-question').disabled = !this.editable;
        this.showTypeHint();
    }

    showTypeHint() {
        const meta = this.typeById[document.getElementById('q-new-type').value];
        const node = document.getElementById('q-type-hint');
        if (!meta) { node.textContent = ''; return; }
        node.replaceChildren(
            qEl('span', { text: meta.hint }),
            meta.example ? qEl('span', { class: 'q-example', text: meta.example }) : null,
        );
    }

    async addQuestion() {
        const type  = document.getElementById('q-new-type').value;
        const input = document.getElementById('q-new-text');
        const error = document.getElementById('q-add-error');
        const text  = input.value.trim();

        error.textContent = '';
        if (!text) { error.textContent = "Donnez un enonce a la question."; input.focus(); return; }

        const meta    = this.typeById[type] || {};
        const payload = { type, text };

        /* valeurs de depart raisonnables pour que la question soit utilisable tout de suite */
        if (meta.uses_options && !meta.fixed_options.length && type !== 'scale') {
            payload.options = [{ text: 'Premiere reponse' }, { text: 'Deuxieme reponse' }];
        }
        if (type === 'scale') payload.config = { min: 1, max: 5, step: 1 };
        if (type === 'city')  payload.config = { cities: [{ code: 'PARIS', name: 'Paris' }] };

        try {
            const created = await this.guard(() => QAPI.post(`${this.version()}/questions/`, payload),
                                             'Question ajoutee');
            input.value = '';
            this.open.add(created.question.id);
            await this.reloadVersion();
            document.getElementById(`q-eq-${created.question.id}`)
                ?.scrollIntoView({ behavior: 'smooth', block: 'center' });
        } catch (err) {
            error.textContent = err.message;
        }
    }

    /* ------------------------------------------------------------------ */
    /* Liste des questions                                                 */
    /* ------------------------------------------------------------------ */

    renderQuestions() {
        const box = document.getElementById('q-questions');
        box.replaceChildren();

        if (!this.draft.questions.length) {
            box.appendChild(qEl('div', { class: 'q-panel' }, [
                qEl('p', { class: 'q-empty',
                           text: "Aucune question pour l'instant. Ajoutez la premiere ci-dessous." }),
            ]));
            return;
        }
        this.draft.questions.forEach((q, i) => box.appendChild(this.questionCard(q, i)));
    }

    questionCard(question, index) {
        const meta = this.typeById[question.type] || {};
        const card = qEl('article', { class: 'q-editor-question', id: `q-eq-${question.id}` });
        const open = this.open.has(question.id);

        const body = qEl('div', { class: 'q-eq-body', hidden: !open });

        const header = qEl('header', {
            onclick: (e) => {
                if (e.target.closest('button')) return;
                body.hidden = !body.hidden;
                body.hidden ? this.open.delete(question.id) : this.open.add(question.id);
            },
        }, [
            qEl('div', { class: 'q-eq-title' }, [
                qEl('span', { class: 'q-qnum', text: index + 1 }),
                qEl('strong', { text: question.text || '(sans enonce)' }),
                qEl('span', { class: 'q-badge', text: meta.label || question.type }),
                question.required ? null : qEl('span', { class: 'q-badge', text: 'facultative' }),
                question.condition ? qEl('span', { class: 'q-badge q-info', text: 'conditionnelle' }) : null,
                question.is_graded ? qEl('span', { class: 'q-badge q-ok', text: 'notee' })
                                   : qEl('span', { class: 'q-badge', text: 'non notee' }),
            ]),
            qEl('div', { class: 'q-actions' }, [
                qEl('button', { class: 'q-btn small', text: '↑', title: 'Monter',
                    disabled: !this.editable || index === 0,
                    onclick: () => this.move(index, -1) }),
                qEl('button', { class: 'q-btn small', text: '↓', title: 'Descendre',
                    disabled: !this.editable || index === this.draft.questions.length - 1,
                    onclick: () => this.move(index, 1) }),
                qEl('button', { class: 'q-btn small q-danger', text: 'Supprimer',
                    disabled: !this.editable,
                    onclick: () => this.remove(question) }),
            ]),
        ]);

        /* etat local edite, envoye en bloc a l'enregistrement */
        const draft = {
            text:            question.text,
            description:     question.description,
            explanation:     question.explanation,
            required:        question.required,
            config:          { ...(question.config || {}) },
            expected_config: JSON.parse(JSON.stringify(question.expected_config || {})),
            scoring_config:  { ...(question.scoring_config || {}) },
            condition:       question.condition ? JSON.parse(JSON.stringify(question.condition)) : null,
            options:         (question.options || []).map(o => ({ ...o })),
        };

        body.append(
            this.sectionWording(draft),
            meta.uses_options ? this.sectionOptions(question, meta, draft) : null,
            meta.config_fields.length ? this.sectionConfig(meta, draft) : null,
            this.sectionExpected(question, meta, draft),
            this.sectionScoring(draft),
            this.sectionCondition(question, draft),
            this.sectionAdvanced(draft),
            qEl('div', { class: 'q-actions end' }, [
                qEl('p', { class: 'q-error', id: `q-err-${question.id}`, style: 'margin-right:auto' }),
                qEl('button', {
                    class: 'q-btn q-primary', text: 'Enregistrer cette question',
                    disabled: !this.editable,
                    onclick: () => this.save(question, draft),
                }),
            ]),
        );

        card.append(header, body);
        return card;
    }

    /* --- sections du formulaire ------------------------------------- */

    sectionWording(draft) {
        return qEl('fieldset', { class: 'q-fieldset' }, [
            qEl('legend', { text: 'Enonce' }),
            QForm.text('Question posee', draft.text, v => draft.text = v,
                { disabled: !this.editable, required: true }),
            QForm.text('Precision affichee sous la question', draft.description,
                v => draft.description = v,
                { disabled: !this.editable,
                  help: 'Facultatif. Utile pour lever une ambiguite ou donner une consigne.' }),
            QForm.check('Reponse obligatoire', draft.required, v => draft.required = v,
                { disabled: !this.editable,
                  help: 'Si coche, le participant ne pourra pas terminer sans y repondre.' }),
            QForm.text("Explication montree dans les resultats", draft.explanation,
                v => draft.explanation = v,
                { disabled: !this.editable,
                  help: "Affichee apres coup, si vous avez autorise les explications dans l'onglet « Qui y a acces »." }),
        ]);
    }

    sectionOptions(question, meta, draft) {
        const list = qEl('div', { class: 'q-field-group', style: 'gap:.4rem' });
        const fixed = meta.fixed_options.length > 0;

        const redraw = () => {
            list.replaceChildren();
            draft.options.forEach((option, i) => list.appendChild(this.optionRow(option, i, draft, redraw, fixed)));
            if (!fixed && this.editable) {
                list.appendChild(qEl('button', {
                    class: 'q-btn small', text: '+ Ajouter une reponse',
                    onclick: (e) => {
                        e.preventDefault();
                        draft.options.push({ text: '', value: '', is_correct: false });
                        redraw();
                    },
                }));
            }
        };
        redraw();

        return qEl('fieldset', { class: 'q-fieldset' }, [
            qEl('legend', { text: 'Reponses proposees' }),
            qEl('p', { class: 'q-help', text: fixed
                ? 'Ce type impose ses reponses. Cochez celle qui est correcte.'
                : (meta.multiple
                    ? 'Cochez toutes les bonnes reponses. Si vous n’en cochez aucune, la question ne sera pas notee.'
                    : 'Cochez la bonne reponse. Si vous n’en cochez aucune, la question ne sera pas notee.') }),
            list,
        ]);
    }

    optionRow(option, index, draft, redraw, fixed) {
        return qEl('div', { class: 'q-option-row' }, [
            qEl('span', { class: 'q-drag', text: '⠿' }),
            qEl('input', {
                type: 'text', class: 'q-opt-text', value: option.text || '',
                placeholder: 'Libelle de la reponse', disabled: !this.editable || fixed,
                oninput: (e) => option.text = e.target.value,
            }),
            qEl('input', {
                type: 'text', class: 'q-opt-value', value: option.value || '',
                placeholder: 'valeur', title: 'Valeur numerique (echelles et notations)',
                disabled: !this.editable || fixed,
                oninput: (e) => option.value = e.target.value,
            }),
            qEl('label', { class: 'q-check', title: 'Cette reponse est correcte' }, [
                qEl('input', {
                    type: 'checkbox', checked: option.is_correct, disabled: !this.editable,
                    onchange: (e) => {
                        option.is_correct = e.target.checked;
                        e.target.closest('.q-option-row').classList.toggle('correct', e.target.checked);
                    },
                }),
                qEl('span', { text: 'correcte' }),
            ]),
            fixed ? null : qEl('button', {
                class: 'q-btn small q-danger', text: '×', title: 'Retirer cette reponse',
                disabled: !this.editable,
                onclick: (e) => { e.preventDefault(); draft.options.splice(index, 1); redraw(); },
            }),
        ]);
    }

    sectionConfig(meta, draft) {
        const fields = meta.config_fields.map(descriptor =>
            QForm.fromDescriptor(descriptor, draft.config[descriptor.key],
                (key, value) => {
                    if (value === null || value === '' ||
                        (Array.isArray(value) && !value.length)) delete draft.config[key];
                    else draft.config[key] = value;
                },
                { disabled: !this.editable }));

        return qEl('fieldset', { class: 'q-fieldset' }, [
            qEl('legend', { text: 'Format de la reponse' }),
            qEl('p', { class: 'q-help',
                text: 'Ces limites sont verifiees par le serveur : une saisie hors bornes est refusee immediatement.' }),
            qEl('div', { class: 'q-grid' }, fields),
        ]);
    }

    /* Reponses attendues : construit des regles lisibles, pas du JSON. */
    sectionExpected(question, meta, draft) {
        const specs = meta.expected_rules;
        const body  = qEl('div', { class: 'q-field-group' });

        if (!specs.length) {
            return qEl('fieldset', { class: 'q-fieldset' }, [
                qEl('legend', { text: 'Bonne reponse' }),
                qEl('p', { class: 'q-help', text: meta.expected_help }),
            ]);
        }

        draft.expected_config.rules = draft.expected_config.rules || [];
        draft.expected_config.match = draft.expected_config.match || 'any';

        const redraw = () => {
            body.replaceChildren();
            const rules = draft.expected_config.rules;

            if (rules.length > 1) {
                body.appendChild(QForm.select(
                    'Combinaison des regles', draft.expected_config.match,
                    [['any', "il suffit qu'une regle soit satisfaite"],
                     ['all', 'toutes les regles doivent etre satisfaites']],
                    v => draft.expected_config.match = v, { disabled: !this.editable }));
            }

            rules.forEach((rule, i) => body.appendChild(
                this.ruleRow(rule, i, meta, draft.expected_config.rules, redraw, draft)));

            if (this.editable) {
                body.appendChild(qEl('button', {
                    class: 'q-btn small', text: '+ Ajouter une regle',
                    onclick: (e) => {
                        e.preventDefault();
                        rules.push({ type: specs[0].kind });
                        redraw();
                    },
                }));
            }
            if (!rules.length) {
                body.appendChild(qEl('p', { class: 'q-help',
                    text: 'Aucune regle : la question sera posee mais pas notee.' }));
            }
        };
        redraw();

        return qEl('fieldset', { class: 'q-fieldset' }, [
            qEl('legend', { text: 'Bonne reponse' }),
            qEl('p', { class: 'q-help', text: meta.expected_help }),
            body,
        ]);
    }

    ruleRow(rule, index, meta, rules, redraw, draft) {
        const specs   = meta.expected_rules;
        const spec    = specs.find(r => r.kind === rule.type) || specs[0];
        const choices = this.valueChoices(meta, draft);

        /* un controle par champ decrit par le serveur */
        const control = (f) => {
            const current = qGet(rule, f.path);

            if (choices && f.input !== 'number' && !f.path.startsWith('value.')) {
                if (f.multiple) {
                    const chosen = new Set((current || []).map(String));
                    return qEl('select', {
                        multiple: true, size: Math.min(choices.length, 5), disabled: !this.editable,
                        title: f.label,
                        onchange: (e) => qSet(rule, f.path,
                            [...e.target.selectedOptions].map(o => o.value)),
                    }, choices.map(([v, l]) => qEl('option', {
                        value: v, text: l, selected: chosen.has(String(v)) })));
                }
                return qEl('select', {
                    disabled: !this.editable, title: f.label,
                    onchange: (e) => qSet(rule, f.path, e.target.value),
                }, [
                    qEl('option', { value: '', text: `— ${f.label} —` }),
                    ...choices.map(([v, l]) => qEl('option', {
                        value: v, text: l, selected: String(current) === String(v) })),
                ]);
            }

            if (f.multiple) {
                return qEl('input', {
                    type: 'text', value: (current || []).join(', '), title: f.label,
                    placeholder: `${f.label} (separees par des virgules)`, disabled: !this.editable,
                    oninput: (e) => qSet(rule, f.path,
                        e.target.value.split(',').map(x => x.trim()).filter(Boolean)),
                });
            }

            return qEl('input', {
                type: f.input === 'datetime' ? 'datetime-local' : f.input,
                step: f.input === 'number' ? 'any' : null,
                value: current === undefined || current === null ? '' : current,
                placeholder: f.label, title: f.label, disabled: !this.editable,
                oninput: (e) => qSet(rule, f.path, e.target.value),
            });
        };

        const controls = [];
        spec.fields.forEach((f, i) => {
            if (i) controls.push(qEl('span', { class: 'q-unit', text: f.label }));
            controls.push(control(f));
        });

        return qEl('div', { class: 'q-rule-row' }, [
            qEl('select', {
                disabled: !this.editable,
                onchange: (e) => { rules[index] = { type: e.target.value }; redraw(); },
            }, specs.map(r => qEl('option', {
                value: r.kind, text: r.label, selected: rule.type === r.kind }))),
            ...controls,
            this.editable ? qEl('button', {
                class: 'q-btn small q-danger', text: '×', title: 'Retirer cette regle',
                onclick: (e) => { e.preventDefault(); rules.splice(index, 1); redraw(); },
            }) : null,
        ]);
    }

    /* Vocabulaire proposable pour une reponse attendue, s'il existe. */
    valueChoices(meta, draft) {
        if (meta.id === 'city') {
            const cities = (draft.config || {}).cities || [];
            return cities.length ? cities.map(c => [c.code, c.name]) : null;
        }
        if (meta.id === 'country') {
            const allowed = (draft.config || {}).allowed || [];
            if (allowed.length) {
                const names = Object.fromEntries(meta.value_choices || []);
                return allowed.map(code => [code, names[code] || code]);
            }
        }
        return meta.value_choices || null;
    }

    sectionScoring(draft) {
        const s = draft.scoring_config;
        const preview = qEl('div', { class: 'q-score-preview' });

        const update = () => {
            const w = Number(s.weight ?? 1), good = Number(s.correct_score ?? 1);
            const bad = Number(s.incorrect_score ?? 0);
            preview.replaceChildren(
                'Bonne reponse : ', qEl('b', { text: `${(w * good).toFixed(2)} pt` }),
                ' · Mauvaise reponse : ', qEl('b', { text: `${(w * bad).toFixed(2)} pt` }),
                s.partial !== false ? ' · score partiel active' : ' · tout ou rien',
            );
        };
        update();

        return qEl('fieldset', { class: 'q-fieldset' }, [
            qEl('legend', { text: 'Bareme de cette question' }),
            qEl('div', { class: 'q-grid' }, [
                QForm.number('Poids', s.weight ?? 1, v => { s.weight = v ?? 1; update(); },
                    { disabled: !this.editable, step: 0.5, min: 0,
                      help: 'Multiplie les points de cette question. 2 = elle compte double.' }),
                QForm.number('Points si correct', s.correct_score ?? 1,
                    v => { s.correct_score = v ?? 0; update(); },
                    { disabled: !this.editable, step: 0.5 }),
                QForm.number('Points si incorrect', s.incorrect_score ?? 0,
                    v => { s.incorrect_score = v ?? 0; update(); },
                    { disabled: !this.editable, step: 0.5,
                      help: 'Mettez une valeur negative pour penaliser une mauvaise reponse.',
                      example: '-0.5' }),
                QForm.number('Points si sans reponse', s.unanswered_score ?? 0,
                    v => s.unanswered_score = v ?? 0, { disabled: !this.editable, step: 0.5 }),
            ]),
            QForm.check('Autoriser un score partiel', s.partial !== false,
                v => { s.partial = v; update(); },
                { disabled: !this.editable,
                  help: 'Pour les questions a plusieurs bonnes reponses : 2 bonnes sur 3 rapportent les deux tiers des points.' }),
            preview,
        ]);
    }

    /* Condition d'affichage : une phrase a completer, pas un arbre JSON. */
    sectionCondition(question, draft) {
        const others = this.draft.questions.filter(q => q.id !== question.id);
        const body   = qEl('div', { class: 'q-field-group' });

        const redraw = () => {
            body.replaceChildren();

            if (!draft.condition) {
                body.appendChild(qEl('p', { class: 'q-help',
                    text: 'Cette question est toujours affichee.' }));
                if (this.editable && others.length) {
                    body.appendChild(qEl('button', {
                        class: 'q-btn small', text: '+ Afficher seulement sous condition',
                        onclick: (e) => {
                            e.preventDefault();
                            draft.condition = { question: others[0].stable_key, operator: 'EQUALS', value: '' };
                            redraw();
                        },
                    }));
                } else if (!others.length) {
                    body.appendChild(qEl('p', { class: 'q-help',
                        text: 'Ajoutez une autre question pour pouvoir conditionner celle-ci.' }));
                }
                return;
            }

            const cond   = draft.condition;
            const source = others.find(q => q.stable_key === cond.question) || others[0];

            const valueControl = () => {
                if (OPLESS.includes(cond.operator)) return null;
                const meta = this.typeById[source?.type] || {};
                if (meta.uses_options && source) {
                    return qEl('select', {
                        disabled: !this.editable,
                        onchange: (e) => cond.value = e.target.value,
                    }, [
                        qEl('option', { value: '', text: '— choisir —' }),
                        ...source.options.map(o => qEl('option', {
                            value: o.stable_key, text: o.text, selected: cond.value === o.stable_key,
                        })),
                    ]);
                }
                return qEl('input', {
                    type: meta.value_input === 'number' ? 'number' : 'text',
                    value: cond.value ?? '', placeholder: 'valeur', disabled: !this.editable,
                    oninput: (e) => cond.value = e.target.value,
                });
            };

            const row = qEl('div', { class: 'q-cond-row' }, [
                qEl('span', { class: 'q-then', text: 'Afficher si la reponse a' }),
                qEl('select', {
                    disabled: !this.editable,
                    onchange: (e) => { cond.question = e.target.value; cond.value = ''; redraw(); },
                }, others.map(q => qEl('option', {
                    value: q.stable_key, text: q.text.slice(0, 60), selected: cond.question === q.stable_key,
                }))),
                qEl('select', {
                    disabled: !this.editable,
                    onchange: (e) => { cond.operator = e.target.value; redraw(); },
                }, CONDITION_OPS.map(([v, l]) => qEl('option', {
                    value: v, text: l, selected: cond.operator === v,
                }))),
                valueControl(),
                this.editable ? qEl('button', {
                    class: 'q-btn small q-danger', text: 'Retirer',
                    onclick: (e) => { e.preventDefault(); draft.condition = null; redraw(); },
                }) : null,
            ]);
            body.append(row, qEl('p', { class: 'q-help',
                text: "Si la condition n'est pas remplie, la question est masquee et ne compte pas dans le score." }));
        };
        redraw();

        return qEl('fieldset', { class: 'q-fieldset' }, [
            qEl('legend', { text: "Quand afficher cette question" }),
            body,
        ]);
    }

    sectionAdvanced(draft) {
        const area = (label, value, apply) => {
            const box = qEl('textarea', {
                rows: 3, disabled: !this.editable,
                text: value === null || value === undefined ? '' : JSON.stringify(value),
                onchange: (e) => {
                    try { apply(e.target.value.trim() ? JSON.parse(e.target.value) : null);
                          e.target.setCustomValidity(''); }
                    catch (_) { e.target.setCustomValidity('JSON invalide'); e.target.reportValidity(); }
                },
            });
            return qEl('div', { class: 'q-field' }, [qEl('span', { class: 'q-label', text: label }), box]);
        };

        return qEl('details', { class: 'q-advanced' }, [
            qEl('summary', { text: 'Reglages avances (JSON)' }),
            qEl('div', {}, [
                qEl('p', { class: 'q-help',
                    text: 'Pour les cas que le formulaire ne couvre pas. En temps normal, vous n’avez pas besoin de cette section.' }),
                area('Format de la reponse', draft.config, v => draft.config = v || {}),
                area('Bonne reponse', draft.expected_config, v => draft.expected_config = v || {}),
                area("Condition d'affichage", draft.condition, v => draft.condition = v),
            ]),
        ]);
    }

    /* --- ecritures --------------------------------------------------- */

    async save(question, draft) {
        const box = document.getElementById(`q-err-${question.id}`);
        box.textContent = '';

        const payload = { ...draft };
        /* une regle incomplete est ignoree plutot que refusee */
        if (payload.expected_config?.rules) {
            const meta = this.typeById[question.type] || { expected_rules: [] };
            payload.expected_config.rules = payload.expected_config.rules.filter(r => {
                const spec = meta.expected_rules.find(x => x.kind === r.type);
                return spec ? qHasValue(r, spec.fields) : false;
            });
        }
        if (payload.condition && !OPLESS.includes(payload.condition.operator)
            && (payload.condition.value === '' || payload.condition.value === null)) {
            box.textContent = "Completez la valeur de la condition d'affichage, ou retirez-la.";
            return;
        }

        try {
            await this.guard(() => QAPI.put(`${this.version()}/questions/${question.id}/`, payload),
                             'Question enregistree');
            await this.reloadVersion();
        } catch (error) {
            box.textContent = error.message;
        }
    }

    async remove(question) {
        if (!confirm(`Supprimer la question « ${question.text} » ?`)) return;
        try {
            await this.guard(() => QAPI.del(`${this.version()}/questions/${question.id}/`),
                             'Question supprimee');
            await this.reloadVersion();
        } catch (error) {
            alert(error.message);
        }
    }

    async move(index, delta) {
        const order = this.draft.questions.map(q => q.id);
        [order[index], order[index + delta]] = [order[index + delta], order[index]];
        await this.guard(() => QAPI.post(`${this.version()}/questions/reorder/`, { order }),
                         'Ordre mis a jour');
        await this.reloadVersion();
    }


    /* ------------------------------------------------------------------ */
    /* Panneau de publication                                              */
    /* ------------------------------------------------------------------ */

    /* Ce qui empeche encore de publier. */
    blockers() {
        const out = [];
        out.push({
            ok: this.draft.questions.length > 0,
            done: `${this.draft.questions.length} question(s) dans cette version.`,
            todo: "Ajoutez au moins une question dans l'onglet « Questions ».",
        });
        const graded = this.draft.questions.filter(q => q.is_graded).length;
        out.push({
            ok: true, warn: graded === 0 && this.draft.questions.length > 0,
            done: graded
                ? `${graded} question(s) notee(s) sur ${this.draft.questions.length}.`
                : "Aucune question notee : ce questionnaire sera un sondage, sans score.",
        });
        return out;
    }

    /* Qui pourra reellement le passer, en clair. */
    async whoCanAccess() {
        const data = await QAPI.get(`${this.base()}/access/`).catch(() => null);
        if (!data) return "Regles d'acces indisponibles.";
        if (!data.access.length)
            return "Tous les utilisateurs connectes pourront le commencer.";
        const groups = {};
        data.access.forEach(r => (groups[r.group_index] = groups[r.group_index] || []).push(r.description));
        return Object.values(groups).map(g => g.join(' et ')).join(' — ou bien — ');
    }

    async renderPublish() {
        const box     = document.getElementById('q-publish-panel');
        const draft   = this.draft;                       // la version editee
        const live    = this.questionnaire.current_version;
        const qStatut = this.questionnaire.status;
        const checks  = this.blockers();
        const ready   = checks.every(c => c.ok);
        const who     = await this.whoCanAccess();
        const isLive  = live === draft.version_number && qStatut === 'PUBLISHED';

        /* Le panneau parle de la VERSION en cours d'edition, pas du
           questionnaire : une fois publie, c'est le seul moyen de mettre en
           ligne la version suivante. */
        let title, detail, cls;

        if (['ARCHIVED', 'INVALIDATED'].includes(qStatut)) {
            cls = 'is-blocked';
            title = qStatut === 'ARCHIVED' ? 'Questionnaire archive' : 'Questionnaire invalide';
            detail = qStatut === 'ARCHIVED'
                ? "Il n'est plus propose aux participants. Les resultats obtenus restent consultables."
                : "Il n'accepte plus aucune reponse. Les tentatives passees restent consultables.";
        } else if (draft.status === 'DRAFT') {
            cls = ready ? 'is-draft' : 'is-blocked';
            title = `Version ${draft.version_number} en brouillon`;
            detail = live
                ? `La version ${live} est actuellement en ligne. Publier la version `
                  + `${draft.version_number} la remplacera ; la version ${live} sera archivee `
                  + `et les resultats deja obtenus resteront intacts.`
                : "Personne ne voit encore ce questionnaire. Publiez-le pour le rendre accessible.";
        } else if (draft.status === 'TEST') {
            cls = 'is-test';
            title = `Version ${draft.version_number} en test`;
            detail = "Seuls les testeurs autorises peuvent la passer, et leurs tentatives ne "
                   + "comptent pas dans les statistiques. Publiez-la quand elle vous convient.";
        } else if (isLive) {
            cls = 'is-published';
            title = `Version ${draft.version_number} en ligne`;
            detail = "Les participants autorises la voient et peuvent la commencer. "
                   + "Pour la modifier, creez une version modifiable : celle-ci restera en ligne "
                   + "jusqu'a ce que vous publiiez la nouvelle.";
        } else if (qStatut === 'DISABLED') {
            cls = 'is-blocked';
            title = 'Questionnaire desactive';
            detail = "Personne ne peut le commencer pour l'instant. Les resultats sont conserves.";
        } else {
            cls = 'is-draft';
            title = `Version ${draft.version_number} — ${draft.status.toLowerCase()}`;
            detail = live ? `La version ${live} est en ligne.`
                          : "Aucune version n'est en ligne pour le moment.";
        }

        const actions = qEl('div', { class: 'q-actions' });
        const err     = qEl('p', { class: 'q-error', id: 'q-publish-error' });
        const impact  = qEl('div', { id: 'q-impact' });

        const publishable = ['DRAFT', 'TEST'].includes(draft.status)
            && !['ARCHIVED', 'INVALIDATED'].includes(qStatut);

        if (publishable && this.capabilities.publish) {
            actions.appendChild(qEl('button', {
                class: 'q-btn q-primary',
                text: live ? `Publier la version ${draft.version_number}` : 'Publier maintenant',
                disabled: !ready,
                title: ready ? '' : "Completez d'abord les points signales ci-dessus",
                onclick: () => this.publish(),
            }));
        }
        if (publishable && draft.status === 'DRAFT' && this.capabilities.test) {
            actions.appendChild(qEl('button', {
                class: 'q-btn', text: 'Mettre en test d’abord', disabled: !ready,
                onclick: () => this.confirmAction('test', 'Mettre cette version en test ?',
                    'Seuls les testeurs autorises pourront la passer. La version sera figee.'),
            }));
        }
        if (isLive && this.capabilities.update) {
            actions.appendChild(qEl('button', {
                class: 'q-btn q-accent', text: 'Creer une version modifiable',
                onclick: () => this.makeEditable(),
            }));
            actions.appendChild(qEl('button', {
                class: 'q-btn', text: 'Desactiver temporairement',
                onclick: () => this.statusAction('disable', 'Desactiver ce questionnaire ?',
                    'Personne ne pourra le commencer tant qu’il sera desactive.'),
            }));
        }
        if (qStatut === 'DISABLED' && this.capabilities.publish) {
            actions.appendChild(qEl('button', {
                class: 'q-btn q-primary', text: 'Reactiver',
                onclick: () => this.statusAction('reactivate', 'Reactiver ce questionnaire ?',
                    'Il redeviendra accessible selon vos regles d’acces.'),
            }));
        }
        if (['PUBLISHED', 'DISABLED', 'TEST'].includes(qStatut) && this.capabilities.archive) {
            actions.appendChild(qEl('button', {
                class: 'q-btn q-danger', text: 'Archiver',
                onclick: () => this.statusAction('archive', 'Archiver ce questionnaire ?',
                    'Il ne sera plus propose. Les resultats deja obtenus sont conserves.'),
            }));
        }

        box.replaceChildren(qEl('section', { class: `q-publish ${cls}` }, [
            qEl('header', {}, [
                qStatus(draft.status),
                qEl('h2', { text: title }),
                live && !isLive
                    ? qEl('span', { class: 'q-badge q-info', text: `version ${live} en ligne` })
                    : null,
            ]),
            qEl('p', { text: detail }),

            publishable ? qEl('ul', { class: 'q-checklist' },
                checks.map(c => qEl('li', { class: c.ok ? 'ok' : 'ko' }, [
                    qEl('span', { class: 'mark', text: c.ok ? '✓' : '✗' }),
                    qEl('span', { text: c.ok ? c.done : c.todo }),
                ]))) : null,

            impact,

            qEl('p', { class: 'q-who' }, [
                qEl('b', { text: 'Qui y aura acces : ' }), who, ' ',
                qEl('button', {
                    class: 'q-btn small q-ghost', text: 'Modifier',
                    onclick: () => this.showTab('access'),
                }),
            ]),
            actions.children.length ? actions : null,
            err,
        ]));

        if (publishable) await this.renderImpact(impact);
    }

    /* Ce que la publication changerait pour les participants deja passes. */
    async renderImpact(box) {
        let data;
        try { data = await QAPI.get(`${this.version()}/impact/`); }
        catch (_) { return; }

        const i = data.impact;
        if (!i.participants) return;

        const lines = [];
        if (!data.carry_over_enabled) {
            lines.push(`${i.participants} participant(s) ont deja repondu. Le report des reponses `
                     + `est desactive : ils repartiront de zero.`);
        } else {
            lines.push(`${i.participants} participant(s) ont deja repondu. Leurs reponses seront `
                     + `reportees sur cette version, et leurs anciens resultats conserves.`);
            if (i.rescored)  lines.push(`${i.rescored} verront leur score recalcule immediatement.`);
            if (i.pending)   lines.push(`${i.pending} devront repondre aux nouvelles questions.`);
            if (i.in_progress) lines.push(`${i.in_progress} sont en cours et continueront sur la nouvelle version.`);
            if (i.dropped_answers)
                lines.push(`${i.dropped_answers} reponse(s) seront perdues : la question ou l'option `
                         + `correspondante n'existe plus.`);
        }

        box.replaceChildren(qEl('div', {
            class: `q-callout ${i.dropped_answers || !data.carry_over_enabled ? 'warn' : ''}`,
            style: 'margin:0',
        }, [
            qEl('h3', { text: 'Effet sur les participants' }),
            ...lines.map(text => qEl('p', { text })),
            i.new_questions.length
                ? qEl('p', { class: 'q-help',
                    text: `Nouvelle(s) question(s) : ${i.new_questions.join(' · ')}` })
                : null,
        ]));
    }

    async publish() {
        const live = this.questionnaire.current_version;
        let impact = null;
        try { impact = (await QAPI.get(`${this.version()}/impact/`)).impact; } catch (_) {}

        const lines = [`Publier la version ${this.draft.version_number} ?`, ''];
        if (live) lines.push(`La version ${live} sera archivee et remplacee.`);
        lines.push("Cette version sera figee : pour la modifier ensuite, l'editeur en creera une nouvelle.");
        if (impact && impact.participants) {
            lines.push('', `${impact.participants} participant(s) ont deja repondu :`);
            if (impact.rescored)   lines.push(`  · ${impact.rescored} verront leur score recalcule`);
            if (impact.pending)    lines.push(`  · ${impact.pending} devront repondre aux nouvelles questions`);
            if (impact.in_progress) lines.push(`  · ${impact.in_progress} en cours continueront sur la nouvelle version`);
            if (impact.dropped_answers)
                lines.push(`  · ${impact.dropped_answers} reponse(s) seront perdues`);
            lines.push('Leurs anciens resultats sont conserves.');
        }
        if (!confirm(lines.join('\n'))) return;

        const err = document.getElementById('q-publish-error');
        if (err) err.textContent = '';
        try {
            const data = await this.guard(() => QAPI.post(`${this.version()}/publish/`, {}),
                                          'Version publiee');
            const report = data.carry_over;
            if (report && report.participants) {
                this.indicator.set('saved',
                    `Publiee — ${report.participants} participant(s) reportes`);
            }
            await this.load();
        } catch (error) {
            if (err) err.textContent = error.message;
        }
    }

    async statusAction(action, title, detail) {
        if (!confirm(`${title}\n\n${detail}`)) return;
        await this.guard(() => QAPI.post(`${this.base()}/${action}/`, {}), 'Statut mis a jour');
        await this.load();
    }

    /* ------------------------------------------------------------------ */
    /* Export                                                              */
    /* ------------------------------------------------------------------ */

    async exportJson() {
        const doc  = await QAPI.get(`${this.base()}/export/?version=${this.draft.version_number}`);
        const blob = new Blob([JSON.stringify(doc, null, 2)], { type: 'application/json' });
        const url  = URL.createObjectURL(blob);
        const link = qEl('a', {
            href: url,
            download: `${(this.questionnaire.slug || 'questionnaire')}-v${this.draft.version_number}.json`,
        });
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);
        this.indicator.set('saved', 'Export telecharge');
    }

    /* ------------------------------------------------------------------ */
    /* Reglages                                                            */
    /* ------------------------------------------------------------------ */

    renderSettings() {
        const box = document.getElementById('q-settings');
        const q   = this.questionnaire;
        const p   = {
            title: q.title, description: q.description,
            ...q.attempt_rules, ...q.answer_rules,
            available_from:  (q.available_from  || '').slice(0, 16),
            available_until: (q.available_until || '').slice(0, 16),
        };

        box.replaceChildren(
            qEl('h3', { text: 'Identite' }),
            QForm.text('Titre', p.title, v => p.title = v, { required: true }),
            QForm.text('Description', p.description, v => p.description = v,
                { help: 'Affichee sur la carte du questionnaire, avant de commencer.' }),

            qEl('h3', { text: 'Combien de fois peut-on le passer' }),
            qEl('div', { class: 'q-grid' }, [
                QForm.number('Nombre de tentatives', p.max_attempts, v => p.max_attempts = v,
                    { step: 1, min: 1, help: 'Laissez vide pour un nombre illimite.', example: '3' }),
                QForm.number('Delai avant de recommencer (minutes)',
                    p.cooldown_seconds ? p.cooldown_seconds / 60 : null,
                    v => p.cooldown_seconds = v ? v * 60 : 0,
                    { step: 1, min: 0, help: "Temps d'attente entre deux tentatives." }),
                QForm.number('Duree maximale d\'une tentative (minutes)',
                    p.time_limit_seconds ? p.time_limit_seconds / 60 : null,
                    v => p.time_limit_seconds = v ? v * 60 : null,
                    { step: 1, min: 1, help: 'Le chronometre demarre au clic sur « Commencer ».' }),
                QForm.number('Delai pour terminer (jours)',
                    p.attempt_expiry_seconds ? p.attempt_expiry_seconds / 86400 : null,
                    v => p.attempt_expiry_seconds = v ? v * 86400 : null,
                    { step: 1, min: 1,
                      help: 'Une tentative commencee mais non terminee expire au bout de ce delai.',
                      example: '7' }),
            ]),
            QForm.check('Peut recommencer apres avoir reussi', p.allow_retry_after_pass,
                v => p.allow_retry_after_pass = v),
            QForm.check('Peut recommencer apres avoir echoue', p.allow_retry_after_fail,
                v => p.allow_retry_after_fail = v),
            QForm.check('Reporter les reponses lors d’une nouvelle version', p.carry_over_answers,
                v => p.carry_over_answers = v,
                { help: "A la publication d'une nouvelle version, les participants retrouvent "
                      + "leurs reponses et n'ont a repondre qu'aux questions ajoutees. "
                      + "Leurs anciens resultats sont conserves dans tous les cas." }),

            qEl('h3', { text: 'Periode de disponibilite' }),
            qEl('div', { class: 'q-grid' }, [
                QForm.text('Ouvre le', p.available_from, v => p.available_from = v,
                    { type: 'datetime-local', help: 'Laissez vide pour ouvrir des la publication.' }),
                QForm.text('Ferme le', p.available_until, v => p.available_until = v,
                    { type: 'datetime-local', help: 'Laissez vide pour ne jamais fermer.' }),
            ]),

            qEl('h3', { text: 'Comment on y repond' }),
            QForm.select('Navigation', p.navigation_mode,
                [['FREE', 'Libre — toutes les questions sur une page'],
                 ['LINEAR', 'Guidee — une question a la fois']],
                v => p.navigation_mode = v),
            QForm.check('Autoriser le retour en arriere', p.allow_back, v => p.allow_back = v,
                { help: 'En navigation guidee uniquement.' }),
            QForm.select('Modification des reponses', p.answer_edit_mode,
                [['UNTIL_FINISH', "Modifiables tant que la tentative n'est pas terminee"],
                 ['FREE',         'Modifiables librement'],
                 ['LOCKED_ON_VALIDATE', 'Verrouillees des la premiere reponse']],
                v => p.answer_edit_mode = v,
                { help: "« Verrouillees » empeche de revenir sur une reponse deja donnee." }),

            qEl('div', { class: 'q-actions end' }, [
                qEl('button', {
                    class: 'q-btn q-primary', text: 'Enregistrer les reglages',
                    onclick: async () => {
                        const payload = { ...p };
                        payload.available_from  = p.available_from  || null;
                        payload.available_until = p.available_until || null;
                        await this.guard(() => QAPI.put(`${this.base()}/`, payload),
                                         'Reglages enregistres');
                        await this.load();
                    },
                }),
            ]),
        );
    }

    /* ------------------------------------------------------------------ */
    /* Notation                                                            */
    /* ------------------------------------------------------------------ */

    renderScoring() {
        const box = document.getElementById('q-scoring');
        const s   = { ...(this.draft.scoring_config || {}) };
        const levels = qEl('div', { class: 'q-field-group', style: 'gap:.4rem' });
        s.levels = s.levels || [];

        const redrawLevels = () => {
            levels.replaceChildren();
            s.levels.forEach((level, i) => levels.appendChild(qEl('div', { class: 'q-rule-row' }, [
                qEl('input', {
                    type: 'text', value: level.name || '', placeholder: 'Nom du palier',
                    disabled: !this.editable, oninput: (e) => level.name = e.target.value,
                }),
                qEl('span', { class: 'q-unit', text: 'a partir de' }),
                qEl('input', {
                    type: 'number', value: level.min_percent ?? 0, min: 0, max: 100,
                    disabled: !this.editable,
                    oninput: (e) => level.min_percent = Number(e.target.value),
                }),
                qEl('span', { class: 'q-unit', text: '%' }),
                this.editable ? qEl('button', {
                    class: 'q-btn small q-danger', text: '×',
                    onclick: (e) => { e.preventDefault(); s.levels.splice(i, 1); redrawLevels(); },
                }) : null,
            ])));
            if (this.editable) {
                levels.appendChild(qEl('button', {
                    class: 'q-btn small', text: '+ Ajouter un palier',
                    onclick: (e) => {
                        e.preventDefault();
                        s.levels.push({ name: '', min_percent: 50 });
                        redrawLevels();
                    },
                }));
            }
        };
        redrawLevels();

        box.replaceChildren(
            QForm.number('Seuil de reussite (%)', s.pass_threshold_percent ?? 60,
                v => s.pass_threshold_percent = v ?? 0,
                { min: 0, max: 100, step: 1, disabled: !this.editable,
                  help: 'En dessous de ce pourcentage, le questionnaire est considere comme echoue.' }),
            QForm.check('Empecher un score total negatif', s.floor_negative !== false,
                v => s.floor_negative = v,
                { disabled: !this.editable,
                  help: 'Utile si vous penalisez les mauvaises reponses : le total ne descend pas sous zero.' }),
            qEl('div', { class: 'q-field' }, [
                qEl('span', { class: 'q-label', text: 'Paliers de reussite (facultatif)' }),
                qEl('p', { class: 'q-help',
                    text: 'Un libelle affiche selon le pourcentage obtenu. Le palier le plus haut atteint gagne.' }),
                qEl('p', { class: 'q-example' }, [qEl('b', { text: 'Exemple : ' }), 'Bronze a 50 %, Argent a 75 %, Or a 90 %']),
                levels,
            ]),
            qEl('div', { class: 'q-actions end' }, [
                qEl('button', {
                    class: 'q-btn q-primary', text: 'Enregistrer la notation',
                    disabled: !this.editable,
                    onclick: async () => {
                        await this.guard(() => QAPI.put(`${this.version()}/`, { scoring_config: s }),
                                         'Notation enregistree');
                        await this.load();
                    },
                }),
            ]),
        );
    }

    /* ------------------------------------------------------------------ */
    /* Acces                                                               */
    /* ------------------------------------------------------------------ */

    async renderAccess() {
        const box  = document.getElementById('q-access');
        const data = await QAPI.get(`${this.base()}/access/`);

        const groups = {
            ACCESS:     this.toGroups(data.access),
            VISIBILITY: this.toGroups(data.visibility),
        };
        const visibility = { ...data.result_visibility };

        const ruleBlock = (kind, title, help) => {
            const list = qEl('div', { class: 'q-field-group', style: 'gap:.5rem' });

            const redraw = () => {
                list.replaceChildren();
                const set = groups[kind];

                if (!set.length) {
                    list.appendChild(qEl('p', { class: 'q-help',
                        text: kind === 'ACCESS'
                            ? 'Aucune restriction : tout utilisateur connecte peut le commencer.'
                            : 'Aucune restriction : la visibilite suit les regles d’accessibilite.' }));
                }

                set.forEach((group, gi) => {
                    const rows = qEl('div', { class: 'q-field-group', style: 'gap:.35rem' });
                    group.forEach((rule, ri) => rows.appendChild(qEl('div', { class: 'q-cond-row' }, [
                        ri ? qEl('span', { class: 'q-then', text: 'ET' }) : null,
                        qEl('select', {
                            onchange: (e) => { group[ri] = { rule_type: e.target.value }; redraw(); },
                        }, [['EVERYONE', 'tout le monde'], ['ROLE', 'a le role'],
                            ['USER', "est l'utilisateur n°"], ['BADGE', 'possede le badge']]
                            .map(([v, l]) => qEl('option', { value: v, text: l, selected: rule.rule_type === v }))),
                        rule.rule_type === 'ROLE' ? qEl('input', {
                            type: 'text', value: rule.role || '', placeholder: 'Recruiter, Admin…',
                            oninput: (e) => rule.role = e.target.value }) : null,
                        rule.rule_type === 'USER' ? qEl('input', {
                            type: 'number', value: rule.user_id || '', placeholder: 'identifiant',
                            oninput: (e) => rule.user_id = Number(e.target.value) }) : null,
                        rule.rule_type === 'BADGE' ? qEl('input', {
                            type: 'text', value: rule.badge_code || '', placeholder: 'code du badge',
                            oninput: (e) => rule.badge_code = e.target.value }) : null,
                        qEl('label', { class: 'q-check' }, [
                            qEl('input', { type: 'checkbox', checked: !!rule.negate,
                                onchange: (e) => rule.negate = e.target.checked }),
                            qEl('span', { text: 'sauf' }),
                        ]),
                        qEl('button', { class: 'q-btn small q-danger', text: '×',
                            onclick: (e) => { e.preventDefault(); group.splice(ri, 1);
                                              if (!group.length) set.splice(gi, 1); redraw(); } }),
                    ])));

                    rows.appendChild(qEl('button', {
                        class: 'q-btn small', text: '+ ET aussi',
                        onclick: (e) => { e.preventDefault(); group.push({ rule_type: 'ROLE', role: '' }); redraw(); },
                    }));

                    list.append(
                        gi ? qEl('p', { class: 'q-eyebrow', text: 'ou bien' }) : null,
                        qEl('div', { class: 'q-panel', style: 'padding:.75rem' }, [rows]),
                    );
                });

                list.appendChild(qEl('button', {
                    class: 'q-btn small', text: set.length ? '+ Ou bien…' : '+ Ajouter une regle',
                    onclick: (e) => { e.preventDefault(); set.push([{ rule_type: 'ROLE', role: '' }]); redraw(); },
                }));
            };
            redraw();

            return qEl('div', { class: 'q-panel' }, [
                qEl('h3', { text: title }),
                qEl('p', { class: 'q-help', text: help }),
                list,
            ]);
        };

        const visibilityLabels = {
            show_score: 'Son score en points',
            show_percentage: 'Son pourcentage',
            show_pass_fail: 'Reussite ou echec',
            show_user_answers: 'Les reponses qu’il a donnees',
            show_correct_answers: 'Les bonnes reponses attendues',
            show_incorrect_answers: 'Le detail de ses erreurs',
            show_explanations: 'Les explications que vous avez ecrites',
            show_badge: 'Les badges obtenus',
        };

        box.replaceChildren(
            ruleBlock('ACCESS', 'Qui peut le commencer',
                'Les regles d’un meme bloc doivent toutes etre vraies. Il suffit qu’un bloc soit satisfait.'),
            ruleBlock('VISIBILITY', 'Qui le voit dans la liste',
                'Laissez vide pour que la visibilite suive l’accessibilite.'),
            qEl('div', { class: 'q-panel' }, [
                qEl('h3', { text: 'Ce que le participant voit apres avoir termine' }),
                qEl('div', { class: 'q-field-group', style: 'gap:.3rem;margin-top:.5rem' },
                    Object.entries(visibilityLabels).map(([key, label]) =>
                        QForm.check(label, visibility[key], v => visibility[key] = v))),
            ]),
            qEl('div', { class: 'q-actions end', style: 'margin-top:1rem' }, [
                qEl('button', {
                    class: 'q-btn q-primary', text: 'Enregistrer les acces',
                    onclick: async () => {
                        const clean = (set) => set
                            .map(g => g.filter(r => r.rule_type === 'EVERYONE'
                                || (r.rule_type === 'ROLE'  && r.role)
                                || (r.rule_type === 'USER'  && r.user_id)
                                || (r.rule_type === 'BADGE' && r.badge_code)))
                            .filter(g => g.length);
                        await this.guard(() => QAPI.put(`${this.base()}/access/`, {
                            access:     clean(groups.ACCESS),
                            visibility: clean(groups.VISIBILITY),
                            result_visibility: visibility,
                        }), 'Acces enregistres');
                        await this.renderAccess();
                        await this.renderPublish();
                    },
                }),
            ]),
        );
    }

    toGroups(rules) {
        const groups = {};
        rules.forEach(r => (groups[r.group_index] = groups[r.group_index] || []).push({
            rule_type: r.rule_type, negate: r.negate,
            role: r.role || '', user_id: r.user ? r.user.id : null,
            badge_code: r.badge ? r.badge.code : '',
        }));
        return Object.values(groups);
    }

    /* ------------------------------------------------------------------ */
    /* Historique                                                          */
    /* ------------------------------------------------------------------ */

    async renderHistory() {
        const box  = document.getElementById('q-history');
        const data = await QAPI.get(`${this.base()}/versions/`);

        const rows = data.versions.map(v => qEl('tr', {}, [
            qEl('td', {}, [
                qEl('b', { text: `Version ${v.version_number}` }),
                v.version_number === data.current ? qEl('span', { class: 'q-badge q-ok', text: 'en ligne' }) : null,
            ]),
            qEl('td', {}, [qStatus(v.status)]),
            qEl('td', { class: 'num', text: v.question_count }),
            qEl('td', { class: 'num', text: v.attempt_count }),
            qEl('td', { text: qDate(v.created_at) }),
            qEl('td', { text: v.created_by || '—' }),
            qEl('td', {}, [qEl('div', { class: 'q-actions' }, [
                qEl('a', { class: 'q-btn small', text: 'Voir',
                    href: `/questionnaires/manage/${this.id}/preview/${v.version_number}/` }),
                v.status !== 'DRAFT' && this.capabilities.versions ? qEl('button', {
                    class: 'q-btn small', text: 'Restaurer',
                    onclick: () => this.restore(v) }) : null,
                v.status !== 'INVALIDATED' && this.capabilities.invalidate ? qEl('button', {
                    class: 'q-btn small q-danger', text: 'Invalider',
                    onclick: () => this.invalidate(v) }) : null,
            ])]),
        ]));

        const pick = (id) => qEl('select', { id },
            data.versions.map(v => qEl('option', { value: v.version_number, text: `Version ${v.version_number}` })));
        const from = pick('q-diff-from'), to = pick('q-diff-to');
        if (data.versions.length > 1) { from.selectedIndex = 1; to.selectedIndex = 0; }
        const diffBox = qEl('div');

        box.replaceChildren(
            qEl('div', { class: 'q-tablewrap' }, [
                qEl('table', { class: 'q-table' }, [
                    qEl('thead', {}, [qEl('tr', {}, ['Version', 'Statut', 'Questions', 'Tentatives',
                        'Creee le', 'Par', 'Actions'].map(h => qEl('th', { text: h })))]),
                    qEl('tbody', {}, rows),
                ]),
            ]),
            qEl('div', { class: 'q-panel', style: 'margin-top:1.25rem' }, [
                qEl('h3', { text: 'Comparer deux versions' }),
                qEl('p', { class: 'q-help', text: 'Voir ce qui a change entre deux versions : questions ajoutees, supprimees, modifiees.' }),
                qEl('div', { class: 'q-inline', style: 'margin:.75rem 0' }, [
                    qEl('span', { class: 'q-unit', text: 'De' }), from,
                    qEl('span', { class: 'q-unit', text: 'vers' }), to,
                    qEl('button', { class: 'q-btn q-primary', text: 'Comparer',
                        onclick: async () => {
                            const d = await QAPI.get(
                                `${this.base()}/versions/compare/?from=${from.value}&to=${to.value}`);
                            this.renderDiff(diffBox, d.diff);
                        } }),
                ]),
                diffBox,
            ]),
        );
    }

    renderDiff(box, diff) {
        const items = [];
        diff.questions.added.forEach(q =>
            items.push(qEl('li', { class: 'q-diff-add', text: `Ajoutee : ${q.text}` })));
        diff.questions.removed.forEach(q =>
            items.push(qEl('li', { class: 'q-diff-remove', text: `Supprimee : ${q.text}` })));
        diff.questions.changed.forEach(q => {
            const sub = qEl('ul');
            Object.keys(q.fields).forEach(f => sub.appendChild(qEl('li', { text: `${f} modifie` })));
            q.options.added.forEach(o => sub.appendChild(qEl('li', { text: `reponse ajoutee : ${o.text}` })));
            q.options.removed.forEach(o => sub.appendChild(qEl('li', { text: `reponse retiree : ${o.text}` })));
            q.options.changed.forEach(o => sub.appendChild(qEl('li', { text: `reponse modifiee : ${o.text}` })));
            items.push(qEl('li', { class: 'q-diff-change' }, [`Modifiee : ${q.text}`, sub]));
        });

        box.replaceChildren(
            qEl('p', { class: 'q-help',
                text: `${diff.summary.added} ajoutee(s), ${diff.summary.removed} supprimee(s), ${diff.summary.changed} modifiee(s).` }),
            items.length ? qEl('ul', { class: 'q-diff-list' }, items)
                         : qEl('p', { class: 'q-empty', text: 'Ces deux versions sont identiques.' }),
        );
    }

    async restore(version) {
        if (!confirm(`Restaurer la version ${version.version_number} ?\n\n`
            + `Une nouvelle version sera creee a partir de son contenu. L'ancienne reste intacte.`)) return;
        const d = await this.guard(
            () => QAPI.post(`${this.base()}/versions/${version.version_number}/restore/`, {}),
            'Version restauree');
        alert(`Version ${d.version.version_number} creee.`);
        await this.load();
    }

    async invalidate(version) {
        const reason = prompt("Pourquoi invalider cette version ?\n\n"
            + "Elle n'acceptera plus de reponse. Les tentatives deja passees restent consultables.");
        if (reason === null) return;
        await this.guard(
            () => QAPI.post(`${this.base()}/versions/${version.version_number}/invalidate/`, { reason }),
            'Version invalidee');
        await this.load();
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const root = document.getElementById('q-editor');
    if (root) new QuestionnaireEditor(root);
});
