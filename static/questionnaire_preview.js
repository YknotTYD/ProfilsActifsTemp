/* questionnaire_preview.js - rendu exact de ce que verra le participant. */

document.addEventListener('DOMContentLoaded', async () => {
    const root = document.getElementById('q-preview');
    if (!root) return;

    const id     = Number(root.dataset.questionnaire);
    const number = Number(root.dataset.version);
    const body   = document.getElementById('q-preview-body');

    let data;
    try {
        data = await QAPI.get(`/api/questionnaires/${id}/versions/${number}/preview/`);
    } catch (error) {
        body.replaceChildren(qEl('div', { class: 'q-panel' }, [
            qEl('p', { class: 'q-error', text: error.message }),
        ]));
        return;
    }

    body.replaceChildren(qEl('div', { class: 'q-panel' }, [
        qEl('h2', { text: data.preview.title }),
        data.preview.description ? qEl('p', { class: 'q-muted', text: data.preview.description }) : null,
    ]));

    if (!data.preview.questions.length) {
        body.appendChild(qEl('div', { class: 'q-panel' }, [
            qEl('p', { class: 'q-empty', text: 'Cette version ne contient aucune question.' }),
        ]));
        return;
    }

    data.preview.questions.forEach((question, index) => {
        const node = qEl('section', { class: 'q-question' }, [
            qEl('h3', {}, [
                qEl('span', { class: 'q-qnum', text: index + 1 }),
                qEl('span', {}, [
                    question.text,
                    question.required ? qEl('span', { class: 'q-required', text: ' *' }) : null,
                ]),
            ]),
            question.description ? qEl('p', { class: 'q-hint', text: question.description }) : null,
            question.condition ? qEl('p', { class: 'q-hint' }, [
                qEl('span', { class: 'q-badge q-info', text: 'conditionnelle' }),
                ' Affichee seulement si une reponse precedente le declenche.',
            ]) : null,
        ]);
        node.appendChild(qEl('div', { class: 'q-answer' }, [QFields.build(question, () => {})]));
        body.appendChild(node);
    });
});
