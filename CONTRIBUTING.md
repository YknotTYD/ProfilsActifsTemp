# Contribuer à Compétences+

Ce document décrit le flux de travail attendu sur ce dépôt : comment brancher,
tester et proposer un changement. Pour comprendre le code lui-même, voir
[`docs/architecture.md`](docs/architecture.md).

## Avant de coder

```bash
./setup install       # dépendances système Docker
npm install            # dépendances front (Tailwind CLI)
uv sync                 # dépendances Python
python manage.py migrate
```

En local sans Docker :

```bash
npm run dev             # Django + Tailwind en parallèle
```

Voir [`README.md`](README.md#configuration-env) pour la génération du `.env`
(`DJANGO_SECRET_KEY` obligatoire).

## Branches

Le dépôt n'a pas de convention imposée par outillage, mais l'usage observé
est :

- `feature/<sujet>` pour une fonctionnalité ou un correctif ciblé ;
- `worktree-<sujet>` pour un travail mené depuis un git worktree isolé.

Les branches ne sont pas supprimées après merge : l'historique reste
consultable (voir `docs/journal-des-modifications.md` pour un exemple de
raison — traçabilité d'un renommage sensible).

## Tests

**Aucune fonctionnalité n'est mergée sans test qui la couvre.** Le projet en
compte plusieurs centaines (voir `docs/architecture.md#tests` pour la
répartition par app) ; `profiles/tests/test_security.py` est la suite dédiée
aux fuites d'accès (profil privé, modification d'autrui, données non
autorisées dans l'API).

```bash
python manage.py test --parallel 4                     # tout
python manage.py test profils.profiles --parallel 4    # une app
```

Avant d'ouvrir une PR :

```bash
python manage.py check
python manage.py test --parallel 4
npm run build:css       # vérifier que le CSS compile sans erreur
```

## Migrations

Toute modification de modèle s'accompagne de sa migration, commitée avec le
code qui la nécessite (`python manage.py makemigrations <app>`). Ne pas
committer de migration générée par erreur sur un autre changement.

## Style de code

Le projet suit un motif constant, détaillé dans
[`docs/architecture.md#10-les-motifs-transverses`](docs/architecture.md) :

- **vue → service → modèle** : une vue ne fait que du transport, la logique et
  la validation vivent dans `services.py`, les décisions d'accès dans
  `permissions.py` / `visibility.py` ;
- une donnée qu'un visiteur n'a pas le droit de voir est **absente** de la
  réponse, jamais présente avec un indicateur `visible: false` ;
- une ressource dont l'existence ne doit pas être confirmée (profil privé,
  console d'administration) répond **404**, jamais 403 ;
- les extensions se font par **registre** (`@register`, `@criterion`, `@rule`)
  plutôt que par un `choices=` figé qui demande une migration à chaque ajout.

Un changement qui s'écarte de l'un de ces principes doit avoir une raison
explicite dans la description de la PR.

## Pull requests

Le gabarit (`.github/pull_request_template.md`) demande une description, le
lien vers l'issue le cas échéant, le type de changement, et le plan de test —
le remplir sert de check-list avant relecture, pas de formalité. `Build`
(`.github/workflows/build.yml`) tourne sur chaque push vers `main` ; il
n'est pas déclenché sur les branches de PR — faire tourner les tests et
`manage.py check` en local avant de merger.

## Documentation à tenir à jour

Un changement de comportement observable met à jour, selon ce qu'il touche :

| Changement | Document |
|---|---|
| Route ou schéma de l'API profils | `swagger.yaml` |
| Logique d'un module (`profiles`, `questionnaires`…) | `docs/architecture.md` et/ou le README du module (`profils/<app>/README.md`) |
| Donnée collectée, mécanisme RGPD, accessibilité | `docs/data-governance.md` |
| Variable d'environnement, procédure de déploiement | `docs/deployment.md` |
| Renommage, retrait de fonctionnalité sensible | `docs/journal-des-modifications.md` |
