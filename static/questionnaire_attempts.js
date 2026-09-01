/* questionnaire_attempts.js — suivi des tentatives, resultats et statistiques. */

class AttemptsView {

    constructor(root) {
        this.id = Number(root.dataset.questionnaire);
        document.getElementById('q-include-test')
            .addEventListener('change', () => this.load());
        this.load();
    }

    get includeTest() {
        return document.getElementById('q-include-test').checked ? '1' : '0';
    }

    async load() {
        const suffix = `?include_test=${this.includeTest}`;
        const [attempts, results, stats] = await Promise.all([
            QAPI.get(`/api/questionnaires/${this.id}/attempts/${suffix}`),
            QAPI.get(`/api/questionnaires/${this.id}/results/${suffix}`),
            QAPI.get(`/api/questionnaires/${this.id}/statistics/`).catch(() => null),
        ]);

        this.renderAttempts(attempts.attempts);
        this.renderResults(results.results);
        if (stats) this.renderStats(stats);
    }

    renderAttempts(rows) {
        const tbody = document.querySelector('#q-attempt-list tbody');
        tbody.replaceChildren();
        rows.forEach(row => {
            tbody.appendChild(qEl('tr', {}, [
                qEl('td', { text: row.id }),
                qEl('td', { text: row.user }),
                qEl('td', { text: `v${row.version}` }),
                qEl('td', {}, [qEl('span', { class: 'q-badge', text: row.status })]),
                qEl('td', {}, [row.is_test ? qEl('span', { class: 'q-badge q-test', text: 'test' }) : null]),
                qEl('td', { text: `${row.progress} % (${row.answered_count}/${row.visible_count})` }),
                qEl('td', { text: row.percentage === null ? '—' : `${row.percentage} %` }),
                qEl('td', { text: (row.started_at || '').slice(0, 16).replace('T', ' ') }),
                qEl('td', {}, [qEl('button', {
                    class: 'q-btn', text: 'Detail', onclick: () => this.transcript(row.id),
                })]),
            ]));
        });
    }

    renderResults(rows) {
        const tbody = document.querySelector('#q-result-list tbody');
        tbody.replaceChildren();
        rows.forEach(row => {
            tbody.appendChild(qEl('tr', {}, [
                qEl('td', { text: row.user }),
                qEl('td', { text: `v${row.version}` }),
                qEl('td', { text: `${row.score} / ${row.max_score}` }),
                qEl('td', { text: `${row.percentage} %` }),
                qEl('td', {}, [qEl('span', {
                    class: `q-badge ${row.passed ? 'q-ok' : 'q-ko'}`,
                    text: row.passed ? 'reussi' : 'echoue',
                })]),
                qEl('td', { text: row.level || '—' }),
                qEl('td', { text: (row.computed_at || '').slice(0, 16).replace('T', ' ') }),
            ]));
        });
    }

    renderStats(stats) {
        const box = document.getElementById('q-stats');
        box.replaceChildren(
            qEl('h2', { text: 'Statistiques' }),
            qEl('ul', { class: 'q-meta' }, [
                qEl('li', { text: `Tentatives : ${stats.attempts.total} `
                    + `(terminees ${stats.attempts.completed}, en cours ${stats.attempts.in_progress}, `
                    + `abandonnees ${stats.attempts.abandoned}, expirees ${stats.attempts.expired})` }),
                qEl('li', { text: `Resultats : ${stats.results.count}, reussites ${stats.results.passed}` }),
                qEl('li', { text: `Moyenne : ${stats.results.average === null ? '—'
                    : Number(stats.results.average).toFixed(2) + ' %'}` }),
                qEl('li', { text: `Duree moyenne : ${stats.results.avg_seconds === null ? '—'
                    : Math.round(stats.results.avg_seconds) + ' s'}` }),
            ]),
        );
    }

    async transcript(attemptId) {
        const data = await QAPI.get(
            `/api/questionnaires/${this.id}/attempts/${attemptId}/transcript/`);
        const box = document.getElementById('q-transcript');
        box.hidden = false;
        box.replaceChildren(qEl('h2', { text: `Tentative #${attemptId}` }));

        const table = qEl('table', { class: 'q-table' }, [
            qEl('thead', {}, [qEl('tr', {}, [
                qEl('th', { text: 'Question (au moment de la tentative)' }),
                qEl('th', { text: 'Reponse' }),
                qEl('th', { text: 'Repondu le' }),
            ])]),
        ]);
        const tbody = qEl('tbody');
        data.transcript.answers.forEach(answer => {
            tbody.appendChild(qEl('tr', {}, [
                qEl('td', { text: answer.question.text }),
                qEl('td', { text: answer.display || '—' }),
                qEl('td', { text: (answer.updated_at || '').slice(0, 19).replace('T', ' ') }),
            ]));
        });
        table.appendChild(tbody);
        box.appendChild(table);
        box.scrollIntoView({ behavior: 'smooth' });
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const root = document.getElementById('q-attempts');
    if (root) new AttemptsView(root);
});
