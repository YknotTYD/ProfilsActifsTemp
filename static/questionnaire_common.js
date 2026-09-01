/* questionnaire_common.js — utilitaires partages par toutes les pages. */

const QAPI = (() => {

    const csrf = () => {
        const meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.content : '';
    };

    async function request(url, { method = 'GET', body = null } = {}) {
        const options = {
            method,
            headers: { 'X-CSRFToken': csrf(), 'Accept': 'application/json' },
            credentials: 'same-origin',
        };
        if (body !== null) {
            options.headers['Content-Type'] = 'application/json';
            options.body = JSON.stringify(body);
        }

        const response = await fetch(url, options);
        let payload = {};
        try { payload = await response.json(); } catch (_) { /* reponse vide */ }

        if (!response.ok) {
            const error = new Error(payload.error || `Erreur ${response.status}`);
            error.status  = response.status;
            error.code    = payload.code;
            error.payload = payload;
            throw error;
        }
        return payload;
    }

    return {
        get:  (url)       => request(url),
        post: (url, body) => request(url, { method: 'POST',   body: body || {} }),
        put:  (url, body) => request(url, { method: 'PUT',    body: body || {} }),
        del:  (url)       => request(url, { method: 'DELETE' }),
        uuid: () => (crypto.randomUUID ? crypto.randomUUID()
                                       : `${Date.now()}-${Math.random().toString(16).slice(2)}`),
    };
})();


/* Indicateur d'etat de sauvegarde. */
class QSaveIndicator {

    constructor(root, label) {
        this.root  = root;
        this.label = label;
        this.texts = {
            idle:    'Pret',
            saving:  'Enregistrement…',
            saved:   'Enregistre',
            error:   'Echec de l’enregistrement',
            offline: 'Hors ligne',
        };
    }

    set(state, detail) {
        if (!this.root) return;
        this.root.dataset.state = state;
        if (this.label) this.label.textContent = detail || this.texts[state] || state;
        if (state === 'saved') {
            clearTimeout(this._timer);
            this._timer = setTimeout(() => {
                if (this.root.dataset.state === 'saved') this.set('idle');
            }, 4000);
        }
    }
}


/* --------------------------------------------------------------------- */
/* Fabrique d'elements                                                    */
/* --------------------------------------------------------------------- */

function qEl(tag, attrs = {}, children = []) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs)) {
        if (value === null || value === undefined || value === false) continue;
        if (key === 'class')           node.className = value;
        else if (key === 'text')       node.textContent = value;
        else if (key === 'html')       node.innerHTML = value;
        else if (key === 'dataset')    Object.assign(node.dataset, value);
        else if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
        else node.setAttribute(key, value === true ? '' : value);
    }
    for (const child of [].concat(children)) {
        if (child === null || child === undefined || child === false) continue;
        node.appendChild(typeof child === 'string' ? document.createTextNode(child) : child);
    }
    return node;
}


/* --------------------------------------------------------------------- */
/* Briques de formulaire, avec libelle + aide + exemple                    */
/* --------------------------------------------------------------------- */

const QForm = (() => {

    /* Un champ complet : libelle, controle, aide, exemple. */
    function wrap(label, control, { help, example, required } = {}) {
        const id = control.id || `f-${QAPI.uuid().slice(0, 8)}`;
        control.id = id;
        return qEl('div', { class: 'q-field' }, [
            qEl('label', { for: id }, [label, required ? qEl('span', { class: 'q-req', text: ' *' }) : null]),
            control,
            help    ? qEl('p', { class: 'q-help', text: help }) : null,
            example ? qEl('p', { class: 'q-example' }, [qEl('b', { text: 'Exemple : ' }), example]) : null,
        ]);
    }

    function text(label, value, onInput, opts = {}) {
        return wrap(label, qEl('input', {
            type: opts.type || 'text',
            value: value === null || value === undefined ? '' : value,
            placeholder: opts.placeholder || '',
            disabled: opts.disabled,
            oninput: (e) => onInput(e.target.value),
        }), opts);
    }

    function number(label, value, onInput, opts = {}) {
        return wrap(label, qEl('input', {
            type: 'number',
            step: opts.step || 'any',
            min: opts.min, max: opts.max,
            value: value === null || value === undefined ? '' : value,
            placeholder: opts.placeholder || '',
            disabled: opts.disabled,
            oninput: (e) => onInput(e.target.value === '' ? null : Number(e.target.value)),
        }), opts);
    }

    function select(label, value, choices, onChange, opts = {}) {
        const node = qEl('select', {
            disabled: opts.disabled,
            onchange: (e) => onChange(e.target.value),
        });
        if (opts.blank) node.appendChild(qEl('option', { value: '', text: opts.blank }));
        for (const choice of choices) {
            const [v, l] = Array.isArray(choice) ? choice : [choice, choice];
            node.appendChild(qEl('option', { value: v, text: l, selected: String(value) === String(v) }));
        }
        return wrap(label, node, opts);
    }

    /* Case a cocher : le libelle est a droite, pas au-dessus. */
    function check(label, value, onChange, opts = {}) {
        const input = qEl('input', {
            type: 'checkbox', checked: !!value, disabled: opts.disabled,
            onchange: (e) => onChange(e.target.checked),
        });
        return qEl('div', { class: 'q-field' }, [
            qEl('label', { class: 'q-check' }, [input, qEl('span', { text: label })]),
            opts.help ? qEl('p', { class: 'q-help', text: opts.help }) : null,
        ]);
    }

    /* Champ construit a partir d'un descripteur renvoye par l'API. */
    function fromDescriptor(descriptor, value, onChange, opts = {}) {
        const { key, label, kind, help, example, choices, unit } = descriptor;
        const shared = { help, example, disabled: opts.disabled };
        const current = value === undefined ? descriptor.default : value;

        switch (kind) {
            case 'bool':
                return check(label, current, (v) => onChange(key, v), shared);
            case 'int':
                return number(label, current, (v) => onChange(key, v), { ...shared, step: 1 });
            case 'number':
                return number(label, current, (v) => onChange(key, v), shared);
            case 'select':
                return select(label, current, choices || [], (v) => onChange(key, v || null),
                              { ...shared, blank: '—' });
            case 'select-multi':
                return multiCheck(label, current || [], choices || [], (v) => onChange(key, v), shared);
            case 'date': case 'time': case 'datetime':
                return text(label, current, (v) => onChange(key, v || null),
                            { ...shared, type: kind === 'datetime' ? 'datetime-local' : kind });
            case 'countries':
                return tokens(label, current || [], (v) => onChange(key, v),
                              { ...shared, placeholder: 'FR, BE, CH…', upper: true, maxlen: 2 });
            case 'cities':
                return cityList(label, current || [], (v) => onChange(key, v), shared);
            default:
                return text(label, current, (v) => onChange(key, v || null),
                            { ...shared, unit });
        }
    }

    /* Liste de cases a cocher rendant un tableau de valeurs. */
    function multiCheck(label, values, choices, onChange, opts = {}) {
        const chosen = new Set(values);
        const box = qEl('div', { class: 'q-field-group', style: 'gap:.3rem' });
        for (const choice of choices) {
            const [v, l] = Array.isArray(choice) ? choice : [choice, choice];
            box.appendChild(qEl('label', { class: 'q-check' }, [
                qEl('input', {
                    type: 'checkbox', checked: chosen.has(v), disabled: opts.disabled,
                    onchange: (e) => {
                        e.target.checked ? chosen.add(v) : chosen.delete(v);
                        onChange([...chosen]);
                    },
                }),
                qEl('span', { text: l }),
            ]));
        }
        return qEl('div', { class: 'q-field' }, [
            qEl('span', { class: 'q-label', text: label }),
            box,
            opts.help ? qEl('p', { class: 'q-help', text: opts.help }) : null,
        ]);
    }

    /* Saisie d'une liste de codes courts, separes par des virgules. */
    function tokens(label, values, onChange, opts = {}) {
        const input = qEl('input', {
            type: 'text', value: values.join(', '),
            placeholder: opts.placeholder || '', disabled: opts.disabled,
            oninput: (e) => {
                let parts = e.target.value.split(',').map(s => s.trim()).filter(Boolean);
                if (opts.upper)  parts = parts.map(s => s.toUpperCase());
                if (opts.maxlen) parts = parts.map(s => s.slice(0, opts.maxlen));
                onChange(parts);
            },
        });
        return wrap(label, input, opts);
    }

    /* Liste de villes : une ligne par ville, code genere automatiquement. */
    function cityList(label, cities, onChange, opts = {}) {
        const input = qEl('input', {
            type: 'text',
            value: cities.map(c => c.name).join(', '),
            placeholder: 'Paris, Lyon, Marseille',
            disabled: opts.disabled,
            oninput: (e) => {
                const names = e.target.value.split(',').map(s => s.trim()).filter(Boolean);
                onChange(names.map(name => ({
                    code: name.toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 12) || name,
                    name,
                })));
            },
        });
        return wrap(label, input, {
            ...opts,
            help: opts.help || 'Separez les villes par des virgules.',
        });
    }

    return { wrap, text, number, select, check, multiCheck, tokens, cityList, fromDescriptor };
})();


/* Formate une date ISO pour l'affichage. */
function qDate(iso, withTime = false) {
    if (!iso) return '—';
    const d = new Date(iso);
    if (isNaN(d)) return iso.slice(0, 10);
    const date = d.toLocaleDateString('fr-FR', { day: '2-digit', month: 'short', year: 'numeric' });
    return withTime ? `${date} ${d.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}` : date;
}

/* Pastille de statut. */
function qStatus(status) {
    const labels = {
        DRAFT: 'Brouillon', TEST: 'En test', PUBLISHED: 'Publie', DISABLED: 'Desactive',
        ARCHIVED: 'Archive', INVALIDATED: 'Invalide',
        IN_PROGRESS: 'En cours', COMPLETED: 'Terminee', ABANDONED: 'Abandonnee', EXPIRED: 'Expiree',
    };
    return qEl('span', { class: `q-badge st-${status}`, text: labels[status] || status });
}
