/* questionnaire_attempts.js — suivi des tentatives et des resultats. */

class AttemptsView {

    constructor(root) {
        this.id = Number(root.dataset.questionnaire);
        document.getElementById('q-include-test').addEventListener('change', () => this.load());
        this.load();
    }

    get suffix() {
        return `?include_test=${document.getElementById('q-include-test').checked ? 1 : 0}`;
    }

    async load() {
        const [attempts, results, stats] = await Promise.all([
            QAPI.get(`/api/questionnaires/${this.id}/attempts/${this.suffix}`),
            QAPI.get(`/api/questionnaires/${this.id}/results/${this.suffix}`),
            QAPI.get(`/api/questionnaires/${this.id}/statistics/`).catch(() => null),
        ]);
        if (stats) this.renderStats(stats);
        this.renderAttempts(attempts.attempts);
        this.renderResults(results.results);
    }

    renderStats(s) {
        const rate = s.results.count ? Math.round(s.results.passed / s.results.count * 100) : null;
        const tile = (value, key) => qEl('div', { class: 'q-stat' }, [
            qEl('div', { class: 'v', text: value }), qEl('div', { class: 'k', text: key }),
        ]);
        document.getElementById('q-stats').replaceChildren(
            tile(s.attempts.total, 'tentatives'),
            tile(s.attempts.completed, 'terminees'),
            tile(s.attempts.in_progress, 'en cours'),
            tile(s.attempts.abandoned + s.attempts.expired, 'abandonnees ou expirees'),
            tile(rate === null ? '—' : `${rate} %`, 'taux de reussite'),
            tile(s.results.average === null ? '—' : `${Number(s.results.average).toFixed(0)} %`, 'moyenne'),
            tile(s.results.avg_seconds === null ? '—' : `${Math.round(s.results.avg_seconds / 60)} min`, 'duree moyenne'),
        );
    }

    renderAttempts(rows) {
        const tbody = document.querySelector('#q-attempt-list tbody');
        tbody.replaceChildren();
        if (!rows.length) {
            tbody.appendChild(qEl('tr', {}, [qEl('td', {
                colspan: 7, class: 'q-empty', text: 'Aucune tentative pour le moment.' })]));
            return;
        }
        rows.forEach(row => tbody.appendChild(qEl('tr', {}, [
            qEl('td', {}, [row.user, row.is_test ? qEl('span', { class: 'q-badge q-test', text: 'test' }) : null]),
            qEl('td', { text: `v${row.version}` }),
            qEl('td', {}, [qStatus(row.status)]),
            qEl('td', { text: `${row.answered_count} / ${row.visible_count}` }),
            qEl('td', { class: 'num', text: row.percentage === null ? '—' : `${row.percentage} %` }),
            qEl('td', { text: qDate(row.started_at, true) }),
            qEl('td', {}, [qEl('button', {
                class: 'q-btn small', text: 'Voir ses reponses',
                onclick: () => this.transcript(row.id) })]),
        ])));
    }

    renderResults(rows) {
        const tbody = document.querySelector('#q-result-list tbody');
        tbody.replaceChildren();
        if (!rows.length) {
            tbody.appendChild(qEl('tr', {}, [qEl('td', {
                colspan: 6, class: 'q-empty', text: 'Aucun resultat pour le moment.' })]));
            return;
        }
        rows.forEach(row => tbody.appendChild(qEl('tr', {}, [
            qEl('td', {}, [row.user, row.is_test ? qEl('span', { class: 'q-badge q-test', text: 'test' }) : null]),
            qEl('td', { text: `v${row.version}` }),
            qEl('td', { class: 'num', text: `${row.score} / ${row.max_score}` }),
            qEl('td', { class: 'num', text: `${row.percentage} %` }),
            qEl('td', {}, [
                qEl('span', { class: `q-badge ${row.passed ? 'q-ok' : 'q-ko'}`,
                              text: row.passed ? 'Reussi' : 'Echoue' }),
                row.level ? qEl('span', { class: 'q-badge', text: row.level }) : null,
            ]),
            qEl('td', { text: qDate(row.computed_at, true) }),
        ])));
    }

    async transcript(attemptId) {
        const data = await QAPI.get(`/api/questionnaires/${this.id}/attempts/${attemptId}/transcript/`);
        const box  = document.getElementById('q-transcript');
        box.hidden = false;

        box.replaceChildren(qEl('div', { class: 'q-panel' }, [
            qEl('h2', { text: `Reponses de ${data.transcript.attempt.user}` }),
            qEl('p', { class: 'q-help',
                text: `Tentative n°${attemptId}, version ${data.transcript.attempt.version}. `
                    + `Les enonces affiches sont ceux du moment de la tentative.` }),
            qEl('div', { class: 'q-tablewrap', style: 'margin-top:.75rem' }, [
                qEl('table', { class: 'q-table' }, [
                    qEl('thead', {}, [qEl('tr', {}, ['Question', 'Reponse', 'Repondu le']
                        .map(h => qEl('th', { text: h })))]),
                    qEl('tbody', {}, data.transcript.answers.map(a => qEl('tr', {}, [
                        qEl('td', { text: a.question.text }),
                        qEl('td', { text: a.display || '—' }),
                        qEl('td', { text: qDate(a.updated_at, true) }),
                    ]))),
                ]),
            ]),
        ]));
        box.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const root = document.getElementById('q-attempts');
    if (root) new AttemptsView(root);
});
