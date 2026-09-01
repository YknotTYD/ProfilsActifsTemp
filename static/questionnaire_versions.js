/* questionnaire_versions.js — historique, comparaison et restauration. */

class VersionHistory {

    constructor(root) {
        this.id    = Number(root.dataset.questionnaire);
        this.tbody = document.querySelector('#q-version-list tbody');
        document.getElementById('q-diff-run').addEventListener('click', () => this.compare());
        this.load();
    }

    async load() {
        const data = await QAPI.get(`/api/questionnaires/${this.id}/versions/`);
        this.versions = data.versions;
        this.current  = data.current;

        this.tbody.replaceChildren();
        data.versions.forEach(version => this.tbody.appendChild(this.row(version)));

        ['q-diff-from', 'q-diff-to'].forEach((selectId, index) => {
            const select = document.getElementById(selectId);
            select.replaceChildren();
            data.versions.slice().reverse().forEach(version => {
                select.appendChild(qEl('option', {
                    value: version.version_number,
                    text: `v${version.version_number} (${version.status})`,
                }));
            });
            if (data.versions.length > 1) {
                select.selectedIndex = index === 0 ? data.versions.length - 2 : data.versions.length - 1;
            }
        });
    }

    row(version) {
        const actions = qEl('div', { class: 'q-actions' }, [
            qEl('a', {
                class: 'q-btn', text: 'Previsualiser',
                href: `/questionnaires/manage/${this.id}/preview/${version.version_number}/`,
            }),
            version.status === 'DRAFT'
                ? qEl('button', { class: 'q-btn', text: 'Publier', onclick: () => this.act(version, 'publish') })
                : null,
            version.status === 'DRAFT'
                ? qEl('button', { class: 'q-btn', text: 'Mode TEST', onclick: () => this.act(version, 'test') })
                : null,
            qEl('button', { class: 'q-btn', text: 'Restaurer', onclick: () => this.restore(version) }),
            version.status !== 'INVALIDATED'
                ? qEl('button', { class: 'q-btn q-danger', text: 'Invalider', onclick: () => this.invalidate(version) })
                : null,
        ]);

        return qEl('tr', {}, [
            qEl('td', {}, [
                `v${version.version_number}`,
                version.version_number === this.current
                    ? qEl('span', { class: 'q-badge q-ok', text: ' en ligne' }) : null,
            ]),
            qEl('td', {}, [qEl('span', { class: 'q-badge', text: version.status })]),
            qEl('td', { text: version.question_count }),
            qEl('td', { text: version.attempt_count }),
            qEl('td', { text: (version.created_at || '').slice(0, 16).replace('T', ' ') }),
            qEl('td', { text: version.created_by || '—' }),
            qEl('td', { text: (version.published_at || '—').slice(0, 16).replace('T', ' ') }),
            qEl('td', {}, [actions]),
        ]);
    }

    async act(version, action) {
        await QAPI.post(`/api/questionnaires/${this.id}/versions/${version.version_number}/${action}/`, {});
        this.load();
    }

    async invalidate(version) {
        const reason = prompt('Motif de l\'invalidation ?');
        if (reason === null) return;
        await QAPI.post(
            `/api/questionnaires/${this.id}/versions/${version.version_number}/invalidate/`, { reason });
        this.load();
    }

    async restore(version) {
        if (!confirm(`Restaurer la version ${version.version_number} dans une nouvelle version ?`)) return;
        const data = await QAPI.post(
            `/api/questionnaires/${this.id}/versions/${version.version_number}/restore/`, {});
        alert(`Version ${data.version.version_number} creee.`);
        this.load();
    }

    async compare() {
        const from = document.getElementById('q-diff-from').value;
        const to   = document.getElementById('q-diff-to').value;
        const data = await QAPI.get(`/api/questionnaires/${this.id}/versions/compare/?from=${from}&to=${to}`);
        this.renderDiff(data.diff);
    }

    renderDiff(diff) {
        const box = document.getElementById('q-diff');
        box.replaceChildren();

        box.appendChild(qEl('p', {
            text: `v${diff.from.version_number} (${diff.from.created_by || '?'}) → `
                + `v${diff.to.version_number} (${diff.to.created_by || '?'}) : `
                + `${diff.summary.added} ajoutee(s), ${diff.summary.removed} supprimee(s), `
                + `${diff.summary.changed} modifiee(s)`,
        }));

        Object.entries(diff.metadata).forEach(([field, change]) => {
            box.appendChild(qEl('p', {
                class: 'q-diff-change',
                text: `${field} : ${JSON.stringify(change.from)} → ${JSON.stringify(change.to)}`,
            }));
        });

        const list = qEl('ul');
        diff.questions.added.forEach(q =>
            list.appendChild(qEl('li', { class: 'q-diff-add', text: `+ ${q.text} (${q.type})` })));
        diff.questions.removed.forEach(q =>
            list.appendChild(qEl('li', { class: 'q-diff-remove', text: `− ${q.text} (${q.type})` })));

        diff.questions.changed.forEach(q => {
            const item = qEl('li', { class: 'q-diff-change' }, [`~ ${q.text}`]);
            const sub  = qEl('ul');
            Object.entries(q.fields).forEach(([field, change]) => {
                sub.appendChild(qEl('li', {
                    text: `${field} : ${JSON.stringify(change.from)} → ${JSON.stringify(change.to)}`,
                }));
            });
            q.options.added.forEach(o => sub.appendChild(
                qEl('li', { class: 'q-diff-add', text: `+ option « ${o.text} »` })));
            q.options.removed.forEach(o => sub.appendChild(
                qEl('li', { class: 'q-diff-remove', text: `− option « ${o.text} »` })));
            q.options.changed.forEach(o => sub.appendChild(
                qEl('li', { text: `~ option « ${o.text} » : ${Object.keys(o.fields).join(', ')}` })));
            item.appendChild(sub);
            list.appendChild(item);
        });

        box.appendChild(list);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const root = document.getElementById('q-versions');
    if (root) new VersionHistory(root);
});
