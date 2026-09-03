/* questionnaire_admin.js - liste d'administration. */

class QuestionnaireList {

    constructor() {
        this.tbody = document.querySelector('#q-list tbody');
        this.bind();
        this.load();
    }

    bind() {
        document.getElementById('q-filter-status').addEventListener('change', () => this.load());
        document.getElementById('q-filter-search').addEventListener('input', () => {
            clearTimeout(this.timer);
            this.timer = setTimeout(() => this.load(), 250);
        });
        document.getElementById('q-new')?.addEventListener('click', () => this.create());

        const file = document.getElementById('q-import-file');
        document.getElementById('q-import')?.addEventListener('click', () => file.click());
        file?.addEventListener('change', () => this.importFile(file));
    }

    /* Import d'un document exporte depuis cette application. */
    async importFile(input) {
        const file = input.files[0];
        if (!file) return;
        input.value = '';

        let document_;
        try {
            document_ = JSON.parse(await file.text());
        } catch (_) {
            await QModal.alert("Ce fichier n'est pas du JSON valide.");
            return;
        }
        if (document_.format !== 'jibjob.questionnaire') {
            await QModal.alert("Ce fichier n'est pas un export de questionnaire JibJob.");
            return;
        }

        const count = (document_.content?.questions || []).length;
        const title = document_.questionnaire?.title || document_.content?.title || 'sans titre';
        const ok = await QModal.confirm(`Importer « ${title} » ?\n\n${count} question(s). `
            + `Un nouveau questionnaire sera cree en brouillon - rien n'est ecrase.`, { title: 'Importer' });
        if (!ok) return;

        try {
            const data = await QAPI.post('/api/questionnaires/import/', { document: document_ });
            window.location.href = `/questionnaires/manage/${data.questionnaire.id}/`;
        } catch (error) {
            await QModal.alert(`Import impossible.\n\n${error.message}`, 'Erreur');
        }
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
            this.tbody.appendChild(qEl('tr', {}, [qEl('td', {
                colspan: 7, class: 'q-empty',
                text: search || status
                    ? 'Aucun questionnaire ne correspond a ce filtre.'
                    : 'Aucun questionnaire. Creez le premier avec le bouton ci-dessus.',
            })]));
            return;
        }
        data.questionnaires.forEach(item => this.tbody.appendChild(this.row(item)));
    }

    row(item) {
        return qEl('tr', {}, [
            qEl('td', {}, [
                qEl('a', { href: `/questionnaires/manage/${item.id}/`, text: item.title }),
                item.description ? qEl('p', { class: 'q-help', text: item.description.slice(0, 90) }) : null,
            ]),
            qEl('td', {}, [qStatus(item.status)]),
            qEl('td', { text: item.current_version === null ? '-' : `version ${item.current_version}` }),
            qEl('td', { class: 'num', text: item.version_count }),
            qEl('td', { class: 'num' }, [
                String(item.attempt_count),
                item.test_attempt_count
                    ? qEl('span', { class: 'q-badge q-test', text: `+${item.test_attempt_count} test` })
                    : null,
            ]),
            qEl('td', { text: qDate(item.updated_at) }),
            qEl('td', {}, [qEl('div', { class: 'q-actions' }, [
                qEl('a', { class: 'q-btn small', href: `/questionnaires/manage/${item.id}/`, text: 'Editer' }),
                qEl('a', { class: 'q-btn small', href: `/questionnaires/manage/${item.id}/attempts/`, text: 'Tentatives' }),
                qEl('a', { class: 'q-btn small', text: 'Exporter',
                    href: `/api/questionnaires/${item.id}/export/`, download: `${item.slug}.json` }),
                this.capabilities.create ? qEl('button', {
                    class: 'q-btn small', text: 'Dupliquer', onclick: () => this.duplicate(item) }) : null,
                this.capabilities.archive && item.status !== 'ARCHIVED' ? qEl('button', {
                    class: 'q-btn small q-danger', text: 'Archiver', onclick: () => this.archive(item) }) : null,
            ])]),
        ]);
    }

    async create() {
        const title = await QModal.prompt('Titre du nouveau questionnaire ?', { title: 'Nouveau questionnaire', confirmText: 'CREER' });
        if (!title || !title.trim()) return;
        try {
            const data = await QAPI.post('/api/questionnaires/', { title: title.trim() });
            window.location.href = `/questionnaires/manage/${data.id}/`;
        } catch (error) { await QModal.alert(error.message, 'Erreur'); }
    }

    async duplicate(item) {
        const ok = await QModal.confirm(`Dupliquer « ${item.title} » ?\n\nUne copie en brouillon sera creee.`, { title: 'Dupliquer', confirmText: 'DUPLIQUER' });
        if (!ok) return;
        const data = await QAPI.post(`/api/questionnaires/${item.id}/duplicate/`, {});
        window.location.href = `/questionnaires/manage/${data.questionnaire.id}/`;
    }

    async archive(item) {
        const ok = await QModal.confirm(`Archiver « ${item.title} » ?\n\n`
            + `Il ne sera plus propose aux participants. Les resultats deja obtenus sont conserves.`,
            { title: 'Archiver', confirmText: 'ARCHIVER', danger: true });
        if (!ok) return;
        await QAPI.post(`/api/questionnaires/${item.id}/archive/`, {});
        this.load();
    }
}

document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('q-manage')) new QuestionnaireList();
});
