/* questionnaire_fields.js - rendu des champs de saisie par type de question.
 *
 * Le rendu est pilote par la description renvoyee par l'API (type, famille,
 * config, vocabulaire) : ajouter un type de question cote serveur ne demande
 * ici qu'un cas supplementaire, et le reste de l'interface reste inchange.
 */

const QFields = (() => {

    /* Le serveur declare le controle a afficher : le client ne devine rien.
       Un type qui n'en declarerait pas est refuse des l'enregistrement. */
    const WIDGETS = {
        choice:     (q, v, on) => (q.multiple ? checkboxes : radios)(q, v, on),
        dropdown:   (q, v, on) => dropdown(q, v, on, q.multiple),
        vocabulary: vocabulary,
        number:     numeric,
        temporal:   temporal,
        date_range: dateRange,
        address:    address,
    };

    /* Construit le champ et notifie `onChange(valeur canonique)`. */
    function build(question, onChange) {
        const value = (question.answer && question.answer.value) || null;
        const lock  = question.answer && question.answer.locked;

        const render = WIDGETS[question.widget];
        if (!render) {
            return qEl('p', { class: 'q-error',
                text: `Ce type de question ne peut pas etre affiche (${question.type}). `
                    + `Signalez-le a l'administrateur du questionnaire.` });
        }

        const node = render(question, value, onChange);
        if (lock) node.querySelectorAll('input, select, textarea').forEach(i => i.disabled = true);
        return node;
    }

    /* --- types a options ------------------------------------------------ */

    function radios(question, value, onChange) {
        const selected = new Set((value && value.option_ids) || []);
        const wrap = qEl('div');
        question.options.forEach(option => {
            const input = qEl('input', {
                type: 'radio', name: `q_${question.id}`, value: option.id,
                checked: selected.has(option.id),
                onchange: () => onChange({ option_ids: [option.id] }),
            });
            wrap.appendChild(qEl('label', { class: 'q-choice' }, [
                input,
                qEl('span', { class: 'q-choice-text' }, [
                    option.text,
                    option.description ? qEl('span', { class: 'q-choice-desc', text: option.description }) : null,
                ]),
            ]));
        });
        return wrap;
    }

    function checkboxes(question, value, onChange) {
        const selected = new Set((value && value.option_ids) || []);
        const wrap = qEl('div');
        question.options.forEach(option => {
            const input = qEl('input', {
                type: 'checkbox', name: `q_${question.id}`, value: option.id,
                checked: selected.has(option.id),
                onchange: (event) => {
                    if (event.target.checked) selected.add(option.id);
                    else selected.delete(option.id);
                    onChange({ option_ids: [...selected] });
                },
            });
            wrap.appendChild(qEl('label', { class: 'q-choice' }, [
                input,
                qEl('span', { class: 'q-choice-text' }, [
                    option.text,
                    option.description ? qEl('span', { class: 'q-choice-desc', text: option.description }) : null,
                ]),
            ]));
        });
        return wrap;
    }

    function dropdown(question, value, onChange, multiple) {
        const selected = new Set((value && value.option_ids) || []);
        const select = qEl('select', {
            multiple: multiple, size: multiple ? Math.min(question.options.length, 6) : null,
            onchange: (event) => {
                const ids = [...event.target.selectedOptions].map(o => Number(o.value)).filter(Boolean);
                onChange({ option_ids: ids });
            },
        });
        if (!multiple) select.appendChild(qEl('option', { value: '', text: '-' }));
        question.options.forEach(option => {
            select.appendChild(qEl('option', {
                value: option.id, text: option.text, selected: selected.has(option.id),
            }));
        });
        return qEl('div', { class: 'q-inline' }, [select]);
    }

    /* --- vocabulaires controles ----------------------------------------- */

    function vocabulary(question, value, onChange) {
        const key     = { country: 'country', city: 'city', month: 'month', weekday: 'weekday' }[question.type];
        const current = value ? value[key] : '';
        const select  = qEl('select', {
            onchange: (event) => onChange(event.target.value ? { [key]: event.target.value } : null),
        });
        select.appendChild(qEl('option', { value: '', text: '-' }));
        (question.vocabulary || []).forEach(entry => {
            select.appendChild(qEl('option', {
                value: entry.code, text: entry.label, selected: String(current) === String(entry.code),
            }));
        });
        return qEl('div', { class: 'q-inline' }, [select]);
    }

    /* --- numerique ------------------------------------------------------ */

    function numeric(question, value, onChange) {
        const config = question.config || {};
        const step   = question.type === 'integer' || question.type === 'year'
            ? '1' : (config.decimals ? Math.pow(10, -config.decimals).toFixed(config.decimals) : 'any');

        let unit = (value && value.unit) || config.unit || (question.units || [])[0] || null;

        const emit = (raw) => {
            if (raw === '') { onChange(null); return; }
            onChange(unit ? { number: raw, unit } : { number: raw });
        };

        const input = qEl('input', {
            type: 'number', step,
            min: config.min !== undefined && config.min !== null ? config.min : null,
            max: config.max !== undefined && config.max !== null ? config.max : null,
            value: value ? value.number : '',
            onchange: (event) => emit(event.target.value.trim()),
        });

        const children = [input];
        if (config.allow_unit_choice && (question.units || []).length > 1) {
            const select = qEl('select', {
                onchange: (event) => { unit = event.target.value; emit(input.value.trim()); },
            });
            question.units.forEach(u => select.appendChild(
                qEl('option', { value: u, text: u, selected: u === unit })));
            children.push(select);
        } else if (unit) {
            children.push(qEl('span', { class: 'q-unit', text: unit }));
        }
        return qEl('div', { class: 'q-inline' }, children);
    }

    /* --- date et heure --------------------------------------------------- */

    function temporal(question, value, onChange) {
        const map = {
            date:        { type: 'date',           key: 'date' },
            time:        { type: 'time',           key: 'time' },
            datetime:    { type: 'datetime-local', key: 'datetime' },
            hour_minute: { type: 'time',           key: 'time' },
        }[question.type];
        const config = question.config || {};

        const input = qEl('input', {
            type: map.type, min: config.min || null, max: config.max || null,
            value: value ? value[map.key] : '',
            onchange: (event) => {
                const raw = event.target.value;
                onChange(raw ? { [map.key]: raw } : null);
            },
        });
        return qEl('div', { class: 'q-inline' }, [input]);
    }

    function dateRange(question, value, onChange) {
        const state = { start: value ? value.start : '', end: value ? value.end : '' };
        const emit  = () => onChange(state.start && state.end ? { ...state } : null);

        const start = qEl('input', {
            type: 'date', value: state.start,
            onchange: (event) => { state.start = event.target.value; emit(); },
        });
        const end = qEl('input', {
            type: 'date', value: state.end,
            onchange: (event) => { state.end = event.target.value; emit(); },
        });
        return qEl('div', { class: 'q-field' }, [
            qEl('span', { class: 'q-unit', text: 'Du' }), start,
            qEl('span', { class: 'q-unit', text: 'au' }), end,
        ]);
    }

    /* --- adresse structuree ---------------------------------------------- */

    function address(question, value, onChange) {
        const config = question.config || {};
        const state  = Object.assign({}, value || {});
        const emit   = () => onChange(Object.keys(state).length ? { ...state } : null);

        const wrap = qEl('div', { class: 'q-grid' });

        const number = qEl('input', {
            type: 'number', min: '0', value: state.street_number || '',
            onchange: (event) => {
                if (event.target.value === '') delete state.street_number;
                else state.street_number = Number(event.target.value);
                emit();
            },
        });
        wrap.appendChild(QForm.wrap('Numero', number));

        if (config.allow_street_text !== false) {
            const street = qEl('input', {
                type: 'text', maxlength: config.street_max_length || 120, value: state.street || '',
                onchange: (event) => {
                    const raw = event.target.value.trim();
                    if (raw) state.street = raw; else delete state.street;
                    emit();
                },
            });
            wrap.appendChild(QForm.wrap('Voie', street));
        }

        const postal = qEl('input', {
            type: 'text', maxlength: 12, value: state.postal_code || '',
            onchange: (event) => {
                const raw = event.target.value.trim();
                if (raw) state.postal_code = raw; else delete state.postal_code;
                emit();
            },
        });
        wrap.appendChild(QForm.wrap('Code postal', postal));

        const cities = config.cities || [];
        const city = cities.length
            ? qEl('select', {
                onchange: (event) => {
                    if (event.target.value) state.city = event.target.value; else delete state.city;
                    emit();
                },
              })
            : qEl('input', {
                type: 'text', maxlength: 120, value: state.city || '',
                onchange: (event) => {
                    const raw = event.target.value.trim();
                    if (raw) state.city = raw; else delete state.city;
                    emit();
                },
              });
        if (cities.length) {
            city.appendChild(qEl('option', { value: '', text: '-' }));
            cities.forEach(entry => city.appendChild(qEl('option', {
                value: entry.code, text: entry.name, selected: state.city === entry.code,
            })));
        }
        wrap.appendChild(QForm.wrap('Ville', city));

        const countries = config.countries || [];
        const country = qEl('select', {
            onchange: (event) => {
                if (event.target.value) state.country = event.target.value; else delete state.country;
                emit();
            },
        });
        country.appendChild(qEl('option', { value: '', text: '-' }));
        (countries.length ? countries : [state.country].filter(Boolean)).forEach(code =>
            country.appendChild(qEl('option', { value: code, text: code, selected: state.country === code })));
        wrap.appendChild(QForm.wrap('Pays', country));

        return wrap;
    }

    return { build };
})();
