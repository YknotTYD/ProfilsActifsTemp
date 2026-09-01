/* questionnaire_runner.js — interface de passage d'un questionnaire.
 *
 * Sauvegarde (sections 11 a 14) :
 *   - chaque modification part immediatement vers le serveur ;
 *   - une file par question, la derniere valeur gagne, une requete a la fois ;
 *   - chaque envoi porte une cle d'idempotence et un numero de sequence, ce qui
 *     rend les rejeux sans effet et empeche une requete en retard d'ecraser une
 *     valeur plus recente ;
 *   - en cas d'echec la valeur est conservee (memoire + localStorage) et
 *     reessayee avec un delai croissant, puis au retour de la connexion ;
 *   - l'etat de sauvegarde est affiche en permanence.
 */

class QuestionnaireRunner {

    constructor(root) {
        this.root          = root;
        this.questionnaire = Number(root.dataset.questionnaire);
        this.test          = root.dataset.test === '1';

        this.form      = document.getElementById('q-form');
        this.footer    = document.getElementById('q-footer');
        this.startPane = document.getElementById('q-start-panel');
        this.resultPane = document.getElementById('q-result');
        this.indicator = new QSaveIndicator(
            document.getElementById('q-save-state'),
            document.getElementById('q-save-label'),
        );

        this.state    = null;
        this.pending  = new Map();   // question_id -> { value, key, seq, attempts }
        this.sequence = Number(localStorage.getItem(this.storageKey('seq')) || 0);
        this.sending  = false;
        this.cursor   = 0;
        this.timer    = null;

        this.bind();
        this.restorePending();
        this.load();
    }

    storageKey(suffix) {
        return `q:${this.questionnaire}:${this.test ? 'test' : 'real'}:${suffix}`;
    }

    base() {
        return `/api/questionnaires/${this.questionnaire}`;
    }

    /* --- amorcage -------------------------------------------------------- */

    bind() {
        document.getElementById('q-start').addEventListener('click', () => this.start());
        document.getElementById('q-finish').addEventListener('click', () => this.finish());
        document.getElementById('q-later').addEventListener('click', () => {
            this.flush().finally(() => { window.location.href = '/questionnaires/'; });
        });
        document.getElementById('q-prev').addEventListener('click', () => this.move(-1));
        document.getElementById('q-next').addEventListener('click', () => this.move(1));

        window.addEventListener('online',  () => { this.indicator.set('saving'); this.drain(); });
        window.addEventListener('offline', () => this.indicator.set('offline'));
        window.addEventListener('beforeunload', (event) => {
            if (this.pending.size === 0) return;
            event.preventDefault();
            event.returnValue = '';
        });
    }

    async load() {
        try {
            const data = await QAPI.get(`${this.base()}/current/?test=${this.test ? 1 : 0}`);
            if (data.attempt) {
                this.state = data;
                this.render();
                this.drain();
            } else {
                this.showStart(data);
            }
        } catch (error) {
            this.showStart(null, error.message);
        }
    }

    showStart(data, message) {
        this.startPane.hidden = false;
        this.form.hidden      = true;
        this.footer.hidden    = true;

        const box = document.getElementById('q-start-error');
        const can = data && data.can_start;
        if (message)                       box.textContent = message;
        else if (can && !can.allowed)      box.textContent = can.reason;
        else                               box.textContent = '';

        document.getElementById('q-start').disabled = Boolean(can && !can.allowed);
    }

    async start() {
        const button = document.getElementById('q-start');
        button.disabled = true;
        try {
            this.state = await QAPI.post(`${this.base()}/start/`, { test: this.test });
            this.render();
        } catch (error) {
            document.getElementById('q-start-error').textContent = error.message;
            button.disabled = false;
        }
    }

    /* --- rendu ----------------------------------------------------------- */

    render() {
        this.startPane.hidden = true;
        this.form.hidden      = false;
        this.footer.hidden    = false;
        this.resultPane.hidden = true;
        this.form.replaceChildren();

        const linear = this.state.questionnaire.navigation_mode === 'LINEAR';
        const resume = this.state.attempt.resume_question_id;
        if (resume && linear) {
            const index = this.state.questions.findIndex(q => q.id === resume);
            if (index >= 0) this.cursor = index;
        }

        this.state.questions.forEach((question, index) => {
            this.form.appendChild(this.renderQuestion(question, index));
        });

        this.applyNavigation();
        this.updateProgress(this.state.attempt.progress);
    }

    renderQuestion(question, index) {
        const node = qEl('section', {
            class: 'q-question', id: `q-question-${question.id}`,
            dataset: { questionId: question.id, index },
        });

        node.appendChild(qEl('h3', {}, [
            qEl('span', { class: 'q-qnum', text: index + 1 }),
            qEl('span', {}, [
                question.text,
                question.required ? qEl('span', { class: 'q-required', text: ' *' }) : null,
            ]),
        ]));
        if (question.description) {
            node.appendChild(qEl('p', { class: 'q-hint', text: question.description }));
        }

        node.appendChild(qEl('div', { class: 'q-answer' }, [
            QFields.build(question, (value) => this.change(question.id, value)),
        ]));
        node.appendChild(qEl('p', { class: 'q-error', id: `q-error-${question.id}` }));
        return node;
    }

    applyNavigation() {
        const linear = this.state.questionnaire.navigation_mode === 'LINEAR';
        const back   = this.state.questionnaire.allow_back;

        this.form.querySelectorAll('.q-question').forEach((node, index) => {
            node.hidden = linear && index !== this.cursor;
            node.classList.toggle('q-current', index === this.cursor);
        });

        document.getElementById('q-prev').hidden = !linear || !back;
        document.getElementById('q-next').hidden = !linear;
        document.getElementById('q-prev').disabled = this.cursor === 0;
        document.getElementById('q-next').disabled = this.cursor >= this.state.questions.length - 1;
    }

    move(delta) {
        const next = this.cursor + delta;
        if (next < 0 || next >= this.state.questions.length) return;
        this.cursor = next;
        this.applyNavigation();
    }

    updateProgress(progress) {
        document.getElementById('q-progress-wrap').hidden = false;
        document.getElementById('q-progress-bar').style.width = `${progress.percent}%`;
        const left = progress.total - progress.answered;
        document.getElementById('q-progress-label').textContent = left === 0
            ? `Toutes les questions sont remplies (${progress.total}).`
            : `${progress.answered} sur ${progress.total} — il reste ${left} question${left > 1 ? 's' : ''}.`;
    }

    /* --- file de sauvegarde ---------------------------------------------- */

    change(questionId, value) {
        this.sequence += 1;
        localStorage.setItem(this.storageKey('seq'), String(this.sequence));

        this.pending.set(questionId, {
            value,
            key:      QAPI.uuid(),
            seq:      this.sequence,
            attempts: 0,
        });
        this.persistPending();
        this.indicator.set(navigator.onLine ? 'saving' : 'offline');
        this.drain();
    }

    persistPending() {
        try {
            localStorage.setItem(
                this.storageKey('pending'),
                JSON.stringify([...this.pending.entries()]),
            );
        } catch (_) { /* quota : la file memoire reste la reference */ }
    }

    restorePending() {
        try {
            const raw = localStorage.getItem(this.storageKey('pending'));
            if (raw) this.pending = new Map(JSON.parse(raw));
        } catch (_) { this.pending = new Map(); }
    }

    async drain() {
        if (this.sending || this.pending.size === 0) return;
        if (!navigator.onLine) { this.indicator.set('offline'); return; }

        this.sending = true;
        const [questionId, entry] = this.pending.entries().next().value;

        try {
            const response = await QAPI.post(`${this.base()}/answers/`, {
                question_id:     questionId,
                value:           entry.value,
                client_sequence: entry.seq,
                idempotency_key: entry.key,
                test:            this.test,
            });

            /* la valeur n'est retiree qu'une fois confirmee, et seulement si
               l'utilisateur ne l'a pas modifiee entre-temps */
            const latest = this.pending.get(questionId);
            if (latest && latest.seq === entry.seq) this.pending.delete(questionId);
            this.persistPending();

            this.setError(questionId, '');
            this.afterSave(response);
        } catch (error) {
            await this.handleSaveError(questionId, entry, error);
        } finally {
            this.sending = false;
            if (this.pending.size > 0) this.schedule();
            else if (navigator.onLine) this.indicator.set('saved');
        }
    }

    async handleSaveError(questionId, entry, error) {
        if (error.status === 400) {
            /* saisie refusee par le serveur : inutile de reessayer */
            this.pending.delete(questionId);
            this.persistPending();
            this.setError(questionId, error.message);
            this.indicator.set('error', 'Reponse refusee');
            return;
        }
        if (error.code === 'stale_write') {
            /* une reponse plus recente existe deja cote serveur */
            this.pending.delete(questionId);
            this.persistPending();
            await this.resync();
            return;
        }
        if (error.status === 409 || error.status === 403 || error.status === 401) {
            this.pending.delete(questionId);
            this.persistPending();
            this.setError(questionId, error.message);
            this.indicator.set('error', error.message);
            await this.resync();
            return;
        }

        entry.attempts += 1;
        this.indicator.set(navigator.onLine ? 'error' : 'offline',
                           navigator.onLine ? `Nouvel essai (${entry.attempts})` : null);
    }

    schedule() {
        if (this.timer) clearTimeout(this.timer);
        const worst = Math.max(0, ...[...this.pending.values()].map(e => e.attempts));
        const delay = Math.min(1000 * Math.pow(2, worst), 30000);
        this.timer  = setTimeout(() => this.drain(), worst === 0 ? 0 : delay);
    }

    afterSave(response) {
        this.updateProgress(response.progress);
        this.state.attempt.progress = response.progress;
        this.state.attempt.revision = response.attempt_revision;

        /* une reponse peut rendre visible ou masquer d'autres questions :
           l'ensemble visible fait autorite cote serveur */
        const visible = response.visible_question_ids || [];
        const shown   = this.state.questions.map(q => q.id);
        const same    = visible.length === shown.length && visible.every((id, i) => id === shown[i]);
        if (!same) this.resync();
    }

    async resync() {
        try {
            const data = await QAPI.get(`${this.base()}/state/?test=${this.test ? 1 : 0}`);
            const cursor = this.cursor;
            this.state = data;
            this.render();
            this.cursor = Math.min(cursor, this.state.questions.length - 1);
            this.applyNavigation();
        } catch (error) {
            this.indicator.set('error', error.message);
        }
    }

    setError(questionId, message) {
        const node = document.getElementById(`q-error-${questionId}`);
        if (node) node.textContent = message;
    }

    async flush() {
        for (let i = 0; i < 20 && this.pending.size > 0 && navigator.onLine; i += 1) {
            await this.drain();
        }
    }

    /* --- fin ------------------------------------------------------------- */

    /* Le pied de page est colle en bas de l'ecran : un message affiche en haut
       de page serait invisible au moment ou l'utilisateur clique. */
    footerError(message, nodes = []) {
        const box = document.getElementById('q-finish-error');
        if (!box) return;
        box.replaceChildren();
        if (!message) return;
        box.appendChild(qEl('span', { text: message }));
        nodes.forEach(n => box.appendChild(n));
    }

    async finish() {
        const left = this.state.attempt.progress.total - this.state.attempt.progress.answered;
        const warn = left > 0
            ? `Il reste ${left} question${left > 1 ? 's' : ''} sans reponse.\n\n`
            : '';
        if (!confirm(`${warn}Terminer le questionnaire ?\n\n`
            + `Vos reponses seront verrouillees et votre resultat calcule.`)) return;

        this.footerError('');
        const button = document.getElementById('q-finish');
        button.disabled = true;
        await this.flush();

        if (this.pending.size > 0) {
            this.indicator.set('error', 'Reponses non sauvegardees');
            this.footerError('Certaines reponses ne sont pas encore enregistrees. '
                + 'Verifiez votre connexion, puis reessayez.');
            button.disabled = false;
            return;
        }

        try {
            const data = await QAPI.post(`${this.base()}/finish/`, { test: this.test });
            this.showResult(data.result);
        } catch (error) {
            if (error.code === 'missing_required') {
                await this.resync();
                this.showMissing(error.payload.missing || []);
            } else {
                this.indicator.set('error', error.message);
                this.footerError(error.message);
            }
            button.disabled = false;
        }
    }

    /* Signale precisement ce qui bloque, et emmene a la premiere question. */
    showMissing(ids) {
        this.form.querySelectorAll('.q-question').forEach(n => n.classList.remove('q-missing'));

        const titles = [];
        ids.forEach(id => {
            const node = document.getElementById(`q-question-${id}`);
            if (node) {
                node.classList.add('q-missing');
                const heading = node.querySelector('h3');
                if (heading) titles.push(heading.textContent.trim());
            }
            this.setError(id, 'Cette question est obligatoire.');
        });

        const jump = qEl('button', {
            class: 'q-btn small', type: 'button', text: 'Aller a la premiere',
            onclick: () => {
                const first = document.getElementById(`q-question-${ids[0]}`);
                if (!first) return;
                if (this.state.questionnaire.navigation_mode === 'LINEAR') {
                    const index = this.state.questions.findIndex(q => q.id === ids[0]);
                    if (index >= 0) { this.cursor = index; this.applyNavigation(); }
                }
                first.hidden = false;
                first.scrollIntoView({ behavior: 'smooth', block: 'center' });
            },
        });

        this.footerError(
            ids.length === 1
                ? `Il reste 1 question obligatoire sans reponse : ${titles[0] || ''}`
                : `Il reste ${ids.length} questions obligatoires sans reponse.`,
            ids.length ? [jump] : []);
        this.indicator.set('error', 'Questions obligatoires sans reponse');
    }

    showResult(result) {
        this.form.hidden   = true;
        this.footer.hidden = true;
        document.getElementById('q-progress-wrap').hidden = true;
        this.resultPane.hidden = false;

        const head = qEl('div', { class: 'q-result-head' }, [
            result.percentage !== undefined
                ? qEl('div', { class: 'score', text: `${result.percentage} %` })
                : qEl('div', { class: 'score', text: 'Termine' }),
            qEl('div', { class: 'sub', text: result.score !== undefined
                ? `${result.score} sur ${result.max_score} point(s)`
                : 'Vos reponses ont bien ete enregistrees.' }),
            result.passed !== undefined
                ? qEl('span', { class: `q-badge ${result.passed ? 'q-ok' : 'q-ko'}`,
                                text: (result.passed ? 'Reussi' : 'Echoue')
                                      + (result.level ? ` — ${result.level}` : '') })
                : null,
        ]);

        const inner = qEl('div', { style: 'padding:1.25rem' });

        if (result.answers && result.answers.length) {
            const showExpected = result.answers.some(a => a.expected);
            inner.append(
                qEl('h2', { text: 'Le detail' }),
                qEl('div', { class: 'q-tablewrap', style: 'margin-top:.75rem' }, [
                    qEl('table', { class: 'q-table' }, [
                        qEl('thead', {}, [qEl('tr', {}, [
                            qEl('th', { text: 'Question' }),
                            qEl('th', { text: 'Votre reponse' }),
                            showExpected ? qEl('th', { text: 'Attendu' }) : null,
                            qEl('th', { text: '' }),
                        ])]),
                        qEl('tbody', {}, result.answers.map(a => qEl('tr', {}, [
                            qEl('td', {}, [
                                a.text,
                                a.explanation ? qEl('p', { class: 'q-help', text: a.explanation }) : null,
                            ]),
                            qEl('td', { text: a.given || '—' }),
                            showExpected ? qEl('td', { text: a.expected || '—' }) : null,
                            qEl('td', {}, [
                                a.is_correct === true  ? qEl('span', { class: 'q-badge q-ok', text: 'correct' }) :
                                a.is_correct === false ? qEl('span', { class: 'q-badge q-ko', text: 'incorrect' }) : null,
                            ]),
                        ]))),
                    ]),
                ]),
            );
        } else {
            inner.appendChild(qEl('p', { class: 'q-muted',
                text: 'Le detail de vos reponses n’est pas consultable pour ce questionnaire.' }));
        }

        inner.appendChild(qEl('div', { class: 'q-actions', style: 'margin-top:1.25rem' }, [
            qEl('a', { class: 'q-btn q-primary', text: 'Mes resultats',
                       href: `/questionnaires/${this.questionnaire}/results/` }),
            qEl('a', { class: 'q-btn', text: 'Retour aux questionnaires', href: '/questionnaires/' }),
        ]));

        this.resultPane.replaceChildren(
            qEl('div', { class: 'q-panel', style: 'padding:0;overflow:hidden' }, [head, inner]));

        localStorage.removeItem(this.storageKey('pending'));
        this.indicator.set('saved', 'Tentative terminee');
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const root = document.getElementById('q-runner');
    if (root) new QuestionnaireRunner(root);
});
