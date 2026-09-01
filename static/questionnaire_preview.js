/* questionnaire_preview.js — rendu exact de ce que verra l'utilisateur. */

document.addEventListener('DOMContentLoaded', async () => {
    const root = document.getElementById('q-preview');
    if (!root) return;

    const id      = Number(root.dataset.questionnaire);
    const number  = Number(root.dataset.version);
    const body    = document.getElementById('q-preview-body');
    const data    = await QAPI.get(`/api/questionnaires/${id}/versions/${number}/preview/`);

    body.replaceChildren(
        qEl('h2', { text: data.preview.title }),
        qEl('p', { class: 'q-muted', text: data.preview.description }),
    );

    data.preview.questions.forEach((question, index) => {
        const node = qEl('section', { class: 'q-question' }, [
            qEl('h3', {}, [
                `${index + 1}. ${question.text}`,
                question.required ? qEl('span', { class: 'q-required', text: ' *' }) : null,
            ]),
            question.description ? qEl('p', { class: 'q-hint', text: question.description }) : null,
            question.condition ? qEl('p', { class: 'q-hint', text: 'question conditionnelle' }) : null,
        ]);
        node.appendChild(QFields.build(question, () => {}));
        body.appendChild(node);
    });
});
