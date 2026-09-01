/* questionnaire_editor.js — editeur de questionnaire.
 *
 * L'editeur travaille toujours sur une version modifiable : si la version
 * courante est figee (mise en test, publiee ou deja utilisee), le serveur en
 * derive une nouvelle a la demande. Aucune version publiee n'est jamais
 * modifiee en place.
 */

class QuestionnaireEditor {

    constructor(root) {
        this.id        = Number(root.dataset.questionnaire);
        this.indicator = new QSaveIndicator(
            document.getElementById('q-save-state'),
            document.getElementById('q-save-label'),
        );
        this.bind();
        this.load();
    }

    base()    { return `/api/questionnaires/${this.id}`; }
    version() { return `${this.base()}/versions/${this.draft.version_number}`; }

    /* --- chargement ------------------------------------------------------ */

    async load() {
        const [detail, types] = await Promise.all([
            QAPI.get(`${this.base()}/`),
            QAPI.get('/api/questionnaires/types/'),
        ]);

        this.questionnaire = detail.questionnaire;
        this.capabilities  = detail.capabilities;
        this.types         = types.types;
        this.typeById      = Object.fromEntries(types.types.map(t => [t.id, t]));

        const draft = this.questionnaire.versions.find(v => v.is_editable)
            || this.questionnaire.versions.find(v => v.status === 'DRAFT')
            || this.questionnaire.versions[0];

        const full = await QAPI.get(`${this.base()}/versions/${draft.version_number}/`);
        this.draft = full.version;

        document.getElementById('q-status').textContent  = this.questionnaire.status;
        document.getElementById('q-version').textContent = `v${this.draft.version_number}`;
        document.getElementById('q-locked-note').hidden  = this.draft.is_editable;

        this.fillTypeSelect();
        this.renderQuestions();
        this.renderSettings();
        this.renderScoring();
        this.renderAccess();
        this.indicator.set('saved', 'Charge');
    }

    fillTypeSelect() {
        const select = document.getElementById('q-new-type');
        select.replaceChildren();
        const families = {};
        this.types.forEach(type => {
            (families[type.family] = families[type.family] || []).push(type);
        });
        Object.entries(families).forEach(([family, types]) => {
            const group = qEl('optgroup', { label: family });
            types.forEach(type => group.appendChild(qEl('option', { value: type.id, text: type.label })));
            select.appendChild(group);
        });
    }

    /* --- actions globales ------------------------------------------------ */

    bind() {
        document.querySelectorAll('.q-tab').forEach(tab => {
            tab.addEventListener('click', () => {
                document.querySelectorAll('.q-tab').forEach(t => t.classList.remove('q-tab-active'));
                tab.classList.add('q-tab-active');
                document.querySelectorAll('.q-tabpane').forEach(pane => {
                    pane.hidden = pane.dataset.pane !== tab.dataset.tab;
                });
                if (tab.dataset.tab === 'audit') this.renderAudit();
            });
        });

        document.getElementById('q-add-question').addEventListener('click', () => this.addQuestion());
        document.getElementById('q-make-editable').addEventListener('click', () => this.makeEditable());
        document.getElementById('q-preview').addEventListener('click', () => {
            window.location.href = `/questionnaires/manage/${this.id}/preview/${this.draft.version_number}/`;
        });

        this.on('q-publish',    () => this.transition('publish',    'Publier cette version ?'));
        this.on('q-to-test',    () => this.transition('test',       'Passer cette version en mode TEST ?'));
        this.on('q-invalidate', () => this.invalidate());
    }

    on(id, handler) {
        const node = document.getElementById(id);
        if (node) node.addEventListener('click', handler);
    }

    async guard(action) {
        this.indicator.set('saving');
        try {
            const result = await action();
            this.indicator.set('saved');
            return result;
        } catch (error) {
            this.indicator.set('error', error.message);
            throw error;
        }
    }

    async makeEditable() {
        const data = await this.guard(() => QAPI.post(`${this.base()}/versions/editable/`, {}));
        this.draft = data.version;
        await this.load();
    }

    async transition(action, question) {
        if (!confirm(question)) return;
        await this.guard(() => QAPI.post(`${this.version()}/${action}/`, {}));
        await this.load();
    }

    async invalidate() {
        const reason = prompt('Motif de l\'invalidation ?');
        if (reason === null) return;
        await this.guard(() => QAPI.post(`${this.version()}/invalidate/`, { reason }));
        await this.load();
    }

    /* --- questions -------------------------------------------------------- */

    renderQuestions() {
        const box = document.getElementById('q-questions');
        box.replaceChildren();

        if (!this.draft.questions.length) {
            box.appendChild(qEl('p', { class: 'q-empty', text: 'Aucune question pour le moment.' }));
        }
        this.draft.questions.forEach((question, index) => {
            box.appendChild(this.questionCard(question, index));
        });

        const editable = this.draft.is_editable;
        document.getElementById('q-add-question').disabled = !editable;
        document.getElementById('q-new-type').disabled     = !editable;
    }

    questionCard(question, index) {
        const meta     = this.typeById[question.type] || {};
        const editable = this.draft.is_editable;
        const card     = qEl('article', { class: 'q-editor-question' });

        card.appendChild(qEl('header', {}, [
            qEl('strong', { text: `${index + 1}. ${meta.label || question.type}` }),
            qEl('div', { class: 'q-actions' }, [
                qEl('button', { class: 'q-btn', text: '↑', disabled: !editable || index === 0,
                    onclick: () => this.moveQuestion(index, -1) }),
                qEl('button', { class: 'q-btn', text: '↓', disabled: !editable || index === this.draft.questions.length - 1,
                    onclick: () => this.moveQuestion(index, 1) }),
                qEl('button', { class: 'q-btn q-danger', text: 'Supprimer', disabled: !editable,
                    onclick: () => this.deleteQuestion(question) }),
            ]),
        ]));

        const grid = qEl('div', { class: 'q-grid' });
        const text = this.field(grid, 'Enonce', 'text', question.text, editable);
        const desc = this.field(grid, 'Description', 'text', question.description, editable);
        const expl = this.field(grid, 'Explication (resultats)', 'text', question.explanation, editable);

        const required = qEl('input', { type: 'checkbox', checked: question.required, disabled: !editable });
        grid.appendChild(qEl('label', {}, [required, ' Obligatoire']));

        const scoring = question.scoring_config || {};
        const weight  = this.field(grid, 'Poids', 'number', scoring.weight, editable);
        const good    = this.field(grid, 'Score bonne reponse', 'number', scoring.correct_score, editable);
        const bad     = this.field(grid, 'Score mauvaise reponse', 'number', scoring.incorrect_score, editable);

        const partial = qEl('input', { type: 'checkbox', checked: scoring.partial !== false, disabled: !editable });
        grid.appendChild(qEl('label', {}, [partial, ' Score partiel']));

        card.appendChild(grid);

        const config = qEl('textarea', {
            rows: 2, disabled: !editable, text: JSON.stringify(question.config || {}),
        });
        card.appendChild(qEl('label', {}, ['Configuration (JSON) ', config]));

        const expected = qEl('textarea', {
            rows: 2, disabled: !editable, text: JSON.stringify(question.expected_config || {}),
        });
        card.appendChild(qEl('label', {}, ['Reponses attendues (JSON) ', expected]));

        const condition = qEl('textarea', {
            rows: 2, disabled: !editable,
            text: question.condition ? JSON.stringify(question.condition) : '',
        });
        card.appendChild(qEl('label', {}, ['Condition d\'affichage (JSON, vide = toujours) ', condition]));

        let options = null;
        if (meta.uses_options) {
            options = this.optionsEditor(question, editable);
            card.appendChild(options.node);
        }

        card.appendChild(qEl('button', {
            class: 'q-btn q-primary', text: 'Enregistrer la question', disabled: !editable,
            onclick: () => this.saveQuestion(question, {
                text: text.value, description: desc.value, explanation: expl.value,
                required: required.checked,
                config:   this.parseJSON(config.value, {}),
                expected_config: this.parseJSON(expected.value, {}),
                condition: condition.value.trim() ? this.parseJSON(condition.value, null) : null,
                scoring_config: {
                    ...scoring,
                    weight:          Number(weight.value),
                    correct_score:   Number(good.value),
                    incorrect_score: Number(bad.value),
                    partial:         partial.checked,
                },
                options: options ? options.read() : undefined,
            }),
        }));

        card.appendChild(qEl('p', { class: 'q-error', id: `q-err-${question.id}` }));
        return card;
    }

    field(parent, label, type, value, enabled) {
        const input = qEl('input', {
            type, value: value === null || value === undefined ? '' : value, disabled: !enabled,
        });
        parent.appendChild(qEl('label', {}, [`${label} `, input]));
        return input;
    }

    optionsEditor(question, editable) {
        const box  = qEl('div');
        const rows = [];

        const addRow = (option) => {
            const text = qEl('input', { type: 'text', value: option.text || '', disabled: !editable });
            const value = qEl('input', {
                type: 'text', value: option.value || '', size: 6, disabled: !editable,
                title: 'valeur (echelle, notation)',
            });
            const correct = qEl('input', { type: 'checkbox', checked: option.is_correct, disabled: !editable });
            const row = qEl('div', { class: 'q-option-row' }, [
                text, value,
                qEl('label', {}, [correct, ' correcte']),
                qEl('button', {
                    class: 'q-btn q-danger', text: '×', disabled: !editable,
                    onclick: (event) => { event.preventDefault(); row.remove(); rows.splice(rows.indexOf(entry), 1); },
                }),
            ]);
            const entry = { id: option.id, stable_key: option.stable_key, text, value, correct };
            rows.push(entry);
            box.appendChild(row);
        };

        (question.options || []).forEach(addRow);
        box.appendChild(qEl('button', {
            class: 'q-btn', text: 'Ajouter une option', disabled: !editable,
            onclick: (event) => { event.preventDefault(); addRow({ text: '', value: '', is_correct: false }); },
        }));

        return {
            node: qEl('fieldset', {}, [qEl('legend', { text: 'Reponses proposees' }), box]),
            read: () => rows.map((entry, index) => ({
                id: entry.id, stable_key: entry.stable_key, order: index,
                text: entry.text.value, value: entry.value.value, is_correct: entry.correct.checked,
            })),
        };
    }

    parseJSON(raw, fallback) {
        try { return raw.trim() ? JSON.parse(raw) : fallback; }
        catch (_) { throw new Error('JSON invalide'); }
    }

    async addQuestion() {
        const type = document.getElementById('q-new-type').value;
        const text = prompt('Enonce de la question ?');
        if (!text) return;

        const payload = { type, text };
        const meta    = this.typeById[type] || {};
        if (meta.uses_options && !['yes_no', 'true_false', 'scale'].includes(type)) {
            payload.options = [{ text: 'Option 1' }, { text: 'Option 2' }];
        }
        if (type === 'scale')  payload.config = { min: 1, max: 5, step: 1 };
        if (type === 'city')   payload.config = { cities: [{ code: 'PAR', name: 'Paris' }] };

        await this.guard(() => QAPI.post(`${this.version()}/questions/`, payload));
        await this.reloadVersion();
    }

    async saveQuestion(question, payload) {
        const box = document.getElementById(`q-err-${question.id}`);
        box.textContent = '';
        try {
            await this.guard(() =>
                QAPI.put(`${this.version()}/questions/${question.id}/`, payload));
            await this.reloadVersion();
        } catch (error) {
            box.textContent = error.message;
        }
    }

    async deleteQuestion(question) {
        if (!confirm('Supprimer cette question ?')) return;
        try {
            await this.guard(() => QAPI.del(`${this.version()}/questions/${question.id}/`));
            await this.reloadVersion();
        } catch (error) {
            document.getElementById(`q-err-${question.id}`).textContent = error.message;
        }
    }

    async moveQuestion(index, delta) {
        const order = this.draft.questions.map(q => q.id);
        const target = index + delta;
        [order[index], order[target]] = [order[target], order[index]];

        await this.guard(() => QAPI.post(`${this.version()}/questions/reorder/`, { order }));
        await this.reloadVersion();
    }

    async reloadVersion() {
        const data = await QAPI.get(`${this.version()}/`);
        this.draft = data.version;
        this.renderQuestions();
    }

    /* --- parametres ------------------------------------------------------- */

    renderSettings() {
        const form = document.getElementById('q-settings');
        form.replaceChildren();

        const q       = this.questionnaire;
        const rules   = q.attempt_rules;
        const answers = q.answer_rules;

        const inputs = {
            title:       this.field(form, 'Titre', 'text', q.title, true),
            description: this.field(form, 'Description', 'text', q.description, true),
            max_attempts: this.field(form, 'Tentatives max (vide = illimite)', 'number', rules.max_attempts, true),
            cooldown_seconds: this.field(form, 'Delai entre tentatives (s)', 'number', rules.cooldown_seconds, true),
            time_limit_seconds: this.field(form, 'Duree max d\'une tentative (s)', 'number', rules.time_limit_seconds, true),
            attempt_expiry_seconds: this.field(form, 'Expiration d\'une tentative (s)', 'number', rules.attempt_expiry_seconds, true),
            available_from: this.field(form, 'Disponible a partir du', 'datetime-local',
                (q.available_from || '').slice(0, 16), true),
            available_until: this.field(form, 'Disponible jusqu\'au', 'datetime-local',
                (q.available_until || '').slice(0, 16), true),
        };

        const retryPass = qEl('input', { type: 'checkbox', checked: rules.allow_retry_after_pass });
        const retryFail = qEl('input', { type: 'checkbox', checked: rules.allow_retry_after_fail });
        const back      = qEl('input', { type: 'checkbox', checked: answers.allow_back });
        form.appendChild(qEl('label', {}, [retryPass, ' Rejouable apres reussite']));
        form.appendChild(qEl('label', {}, [retryFail, ' Rejouable apres echec']));
        form.appendChild(qEl('label', {}, [back, ' Retour arriere autorise']));

        const editMode = qEl('select', {});
        [['FREE', 'Modifiables librement'],
         ['UNTIL_FINISH', 'Modifiables jusqu\'a la fin'],
         ['LOCKED_ON_VALIDATE', 'Verrouillees des validation']].forEach(([value, label]) => {
            editMode.appendChild(qEl('option', {
                value, text: label, selected: answers.answer_edit_mode === value }));
        });
        form.appendChild(qEl('label', {}, ['Modification des reponses ', editMode]));

        const navMode = qEl('select', {});
        [['FREE', 'Navigation libre'], ['LINEAR', 'Lineaire']].forEach(([value, label]) => {
            navMode.appendChild(qEl('option', {
                value, text: label, selected: answers.navigation_mode === value }));
        });
        form.appendChild(qEl('label', {}, ['Navigation ', navMode]));

        form.appendChild(qEl('button', {
            class: 'q-btn q-primary', type: 'button', text: 'Enregistrer les parametres',
            onclick: async () => {
                const payload = {
                    title: inputs.title.value,
                    description: inputs.description.value,
                    allow_retry_after_pass: retryPass.checked,
                    allow_retry_after_fail: retryFail.checked,
                    allow_back: back.checked,
                    answer_edit_mode: editMode.value,
                    navigation_mode:  navMode.value,
                };
                ['max_attempts', 'cooldown_seconds', 'time_limit_seconds', 'attempt_expiry_seconds']
                    .forEach(key => { payload[key] = inputs[key].value === '' ? null : Number(inputs[key].value); });
                ['available_from', 'available_until']
                    .forEach(key => { payload[key] = inputs[key].value || null; });

                await this.guard(() => QAPI.put(`${this.base()}/`, payload));
                await this.load();
            },
        }));
    }

    /* --- scoring ---------------------------------------------------------- */

    renderScoring() {
        const form = document.getElementById('q-scoring');
        form.replaceChildren();

        const scoring   = this.draft.scoring_config || {};
        const editable  = this.draft.is_editable;
        const threshold = this.field(form, 'Seuil de reussite (%)', 'number',
            scoring.pass_threshold_percent, editable);
        const floor = qEl('input', {
            type: 'checkbox', checked: scoring.floor_negative !== false, disabled: !editable });
        form.appendChild(qEl('label', {}, [floor, ' Plancher a 0 (pas de score negatif global)']));

        const levels = qEl('textarea', {
            rows: 3, disabled: !editable, text: JSON.stringify(scoring.levels || []),
        });
        form.appendChild(qEl('label', {}, ['Niveaux de reussite (JSON) ', levels]));

        form.appendChild(qEl('button', {
            class: 'q-btn q-primary', type: 'button', text: 'Enregistrer le scoring', disabled: !editable,
            onclick: async () => {
                await this.guard(() => QAPI.put(`${this.version()}/`, {
                    scoring_config: {
                        pass_threshold_percent: Number(threshold.value),
                        floor_negative: floor.checked,
                        levels: this.parseJSON(levels.value, []),
                    },
                }));
                await this.load();
            },
        }));
    }

    /* --- acces ------------------------------------------------------------ */

    async renderAccess() {
        const box  = document.getElementById('q-access');
        const data = await QAPI.get(`${this.base()}/access/`);
        box.replaceChildren();

        const describe = (rules, title) => {
            box.appendChild(qEl('h3', { text: title }));
            if (!rules.length) {
                box.appendChild(qEl('p', { class: 'q-muted', text: 'Aucune regle : ouvert a tous.' }));
                return;
            }
            const groups = {};
            rules.forEach(rule => { (groups[rule.group_index] = groups[rule.group_index] || []).push(rule); });
            Object.entries(groups).forEach(([index, group], position) => {
                box.appendChild(qEl('p', {
                    text: `${position ? 'OU ' : ''}groupe ${index} : `
                        + group.map(r => r.description).join(' ET '),
                }));
            });
        };

        describe(data.access, 'Accessibilite (qui peut commencer)');
        describe(data.visibility, 'Visibilite (qui voit qu\'il existe)');

        const editor = qEl('textarea', { rows: 6, text: JSON.stringify({
            access: this.toGroups(data.access), visibility: this.toGroups(data.visibility),
        }, null, 2) });
        box.appendChild(qEl('label', {}, [
            'Regles (JSON : liste de groupes, AND dans un groupe, OU entre groupes) ', editor,
        ]));

        box.appendChild(qEl('h3', { text: 'Visibilite des resultats' }));
        const visibility = {};
        Object.entries(data.result_visibility).forEach(([key, value]) => {
            const input = qEl('input', { type: 'checkbox', checked: value });
            visibility[key] = input;
            box.appendChild(qEl('label', {}, [input, ` ${key}`]));
        });

        box.appendChild(qEl('button', {
            class: 'q-btn q-primary', type: 'button', text: 'Enregistrer les acces',
            onclick: async () => {
                const parsed = this.parseJSON(editor.value, { access: [], visibility: [] });
                await this.guard(() => QAPI.put(`${this.base()}/access/`, {
                    ...parsed,
                    result_visibility: Object.fromEntries(
                        Object.entries(visibility).map(([key, input]) => [key, input.checked])),
                }));
                this.renderAccess();
            },
        }));
    }

    toGroups(rules) {
        const groups = {};
        rules.forEach(rule => {
            (groups[rule.group_index] = groups[rule.group_index] || []).push({
                rule_type: rule.rule_type,
                negate:    rule.negate,
                role:      rule.role || undefined,
                user_id:   rule.user ? rule.user.id : undefined,
                badge_code: rule.badge ? rule.badge.code : undefined,
            });
        });
        return Object.values(groups);
    }

    /* --- audit ------------------------------------------------------------ */

    async renderAudit() {
        const data  = await QAPI.get(`${this.base()}/audit/`);
        const tbody = document.querySelector('#q-audit tbody');
        tbody.replaceChildren();

        data.entries.forEach(entry => {
            tbody.appendChild(qEl('tr', {}, [
                qEl('td', { text: (entry.created_at || '').slice(0, 19).replace('T', ' ') }),
                qEl('td', { text: entry.action }),
                qEl('td', { text: entry.actor || 'systeme' }),
                qEl('td', { text: entry.object }),
                qEl('td', { text: JSON.stringify({ old: entry.old_value, new: entry.new_value }) }),
            ]));
        });
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const root = document.getElementById('q-editor');
    if (root) new QuestionnaireEditor(root);
});
