/* questionnaire_admin.js — liste d'administration des questionnaires. */

class QuestionnaireList {

    constructor(root) {
        this.root  = root;
        this.tbody = document.querySelector('#q-list tbody');
        this.bind();
        this.load();
    }

    bind() {
        const reload = () => this.load();
        document.getElementById('q-filter-status').addEventListener('change', reload);
        document.getElementById('q-filter-search').addEventListener('input', () => {
            clearTimeout(this.timer);
            this.timer = setTimeout(reload, 250);
        });
        const create = document.getElementById('q-new');
        if (create) create.addEventListener('click', () => this.create());
    }

    async load() {
        const params = new URLSearchParams();
        const status = document.getElementById('q-filter-status').value;
        const search = document.getElementById('q-filter-search').value.trim();
        if (status) params.set('status', status);
        if (search) params.set('q', search);

        const data = await QAPI.get(`/api/questionnaires/?${params}`);
        this.capabilities = data.capabilities;
        this.tbody.replaceChildren();

        if (!data.questionnaires.length) {
            this.tbody.appendChild(qEl('tr', {}, [
                qEl('td', { colspan: 8, class: 'q-empty', text: 'Aucun questionnaire.' }),
            ]));
            return;
        }
        data.questionnaires.forEach(item => this.tbody.appendChild(this.row(item)));
    }

    row(item) {
        const actions = qEl('div', { class: 'q-actions' }, [
            qEl('a', { class: 'q-btn', href: `/questionnaires/manage/${item.id}/`, text: 'Editer' }),
            qEl('a', { class: 'q-btn', href: `/questionnaires/manage/${item.id}/versions/`, text: 'Versions' }),
            qEl('a', { class: 'q-btn', href: `/questionnaires/manage/${item.id}/attempts/`, text: 'Tentatives' }),
            this.capabilities.create
                ? qEl('button', { class: 'q-btn', text: 'Dupliquer', onclick: () => this.duplicate(item) })
                : null,
            this.capabilities.archive
                ? qEl('button', { class: 'q-btn', text: 'Archiver', onclick: () => this.archive(item) })
                : null,
        ]);

        return qEl('tr', {}, [
            qEl('td', { text: item.id }),
            qEl('td', { text: item.title }),
            qEl('td', {}, [qEl('span', { class: 'q-badge', text: item.status })]),
            qEl('td', { text: item.current_version === null ? '—' : `v${item.current_version}` }),
            qEl('td', { text: item.version_count }),
            qEl('td', { text: `${item.attempt_count} (+${item.test_attempt_count} test)` }),
            qEl('td', { text: (item.updated_at || '').slice(0, 16).replace('T', ' ') }),
            qEl('td', {}, [actions]),
        ]);
    }

    async create() {
        const title = prompt('Titre du questionnaire ?');
        if (!title) return;
        const data = await QAPI.post('/api/questionnaires/', { title });
        window.location.href = `/questionnaires/manage/${data.id}/`;
    }

    async duplicate(item) {
        const data = await QAPI.post(`/api/questionnaires/${item.id}/duplicate/`, {});
        window.location.href = `/questionnaires/manage/${data.questionnaire.id}/`;
    }

    async archive(item) {
        if (!confirm(`Archiver "${item.title}" ?`)) return;
        await QAPI.post(`/api/questionnaires/${item.id}/archive/`, {});
        this.load();
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const root = document.getElementById('q-manage');
    if (root) new QuestionnaireList(root);
});
