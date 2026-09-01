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
            const error = new Error(payload.error || `HTTP ${response.status}`);
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

/* Indicateur d'etat de sauvegarde (section 12). */
class QSaveIndicator {

    constructor(root, label) {
        this.root  = root;
        this.label = label;
        this.texts = {
            idle:    'Pret',
            saving:  'Sauvegarde...',
            saved:   'Sauvegarde',
            error:   'Erreur de sauvegarde',
            offline: 'Hors ligne',
        };
    }

    set(state, detail) {
        if (!this.root) return;
        this.root.dataset.state = state;
        if (this.label) this.label.textContent = detail || this.texts[state] || state;
    }
}

/* Echappement systematique : aucun texte saisi n'est injecte en HTML brut. */
function qEscape(value) {
    return String(value === null || value === undefined ? '' : value)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function qEl(tag, attrs = {}, children = []) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs)) {
        if (value === null || value === undefined || value === false) continue;
        if (key === 'class')      node.className = value;
        else if (key === 'text')  node.textContent = value;
        else if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
        else if (key === 'dataset') Object.assign(node.dataset, value);
        else node.setAttribute(key, value === true ? '' : value);
    }
    for (const child of [].concat(children)) {
        if (child) node.appendChild(typeof child === 'string' ? document.createTextNode(child) : child);
    }
    return node;
}
