# Module questionnaires

Système de questionnaires versionnés : création, publication, passage, scoring, résultats.

App Django autonome. Aucune dépendance en plus, `mainapp` n'est pas touchée.

---

## Démarrer

```bash
docker compose watch          # comme d'habitude
```

ou en local :

```bash
python manage.py migrate
python manage.py runserver
python manage.py test profils.questionnaires --parallel 4    # 285 tests
```

### Se donner les droits admin

Trois façons, au choix :

```bash
python manage.py createsuperuser          # le plus simple
```

```python
# ou : le rôle Admin de mainapp suffit
Role.objects.create(user = mon_user, role = "Admin")
```

```python
# ou : permission par permission (10 dispos, voir constants.py)
user.user_permissions.add(Permission.objects.get(codename = "publish_questionnaire"))
```

---

## Les pages

| URL | Qui | Quoi |
|---|---|---|
| `/questionnaires/` | tout le monde | catalogue de ce à quoi j'ai droit |
| `/questionnaires/<id>/` | tout le monde | passer le questionnaire |
| `/questionnaires/<id>/results/` | tout le monde | mes résultats |
| `/questionnaires/manage/` | admin | liste + création |
| `/questionnaires/manage/<id>/` | admin | l'éditeur (questions, réglages, notation, accès, versions) |
| `/questionnaires/manage/<id>/attempts/` | admin | tentatives, résultats, stats |
| `/questionnaires/manage/<id>/preview/<n>/` | admin | prévisualisation |

---

## Créer un questionnaire (5 min)

1. `/questionnaires/manage/` → **Nouveau questionnaire** → un titre.
2. Onglet **Questions** : choisir un type, **Ajouter une question**.
3. Remplir l'énoncé, cocher les bonnes réponses, régler le poids si besoin.
4. **Enregistrer la question**.
5. Onglet **Paramètres** : nombre de tentatives, navigation, dates de dispo.
6. Onglet **Acces** : qui peut le voir, qui peut le commencer, ce qu'il voit de son résultat.
7. **Publier**. C'est en ligne.

Pour tester avant de publier : **Passer en mode TEST**, puis
`/questionnaires/<id>/?test=1`. Les tentatives de test ne comptent nulle part.

---

## Les 4 trucs à comprendre

### 1. Une version publiée ne se modifie jamais

Un questionnaire, c'est une identité + une pile de versions.

```
Questionnaire #12
├── v1  ARCHIVED     ← quelqu'un l'a passée, elle reste telle quelle
├── v2  PUBLISHED    ← en ligne
└── v3  DRAFT        ← en cours d'édition
```

Une version est modifiable **uniquement** en `DRAFT` et **sans aucune tentative**.
Dès qu'elle passe en TEST ou en PUBLISHED, elle est gelée.

Tu n'as rien à gérer : quand tu ouvres l'éditeur sur un questionnaire publié,
le bouton **Créer une version modifiable** en dérive une nouvelle (copie conforme).
Publier la nouvelle archive l'ancienne.

### 2. Chaque réponse est collée à sa version

```
Tentative → Version exacte → Réponses → Résultat
```

Tu peux réécrire l'énoncé, changer les options, inverser la bonne réponse :
les scores déjà calculés ne bougent pas d'un poil. Il y a un test qui fait
exactement ça pour le prouver.

En plus, chaque réponse embarque un **snapshot** (l'énoncé et les libellés
au moment où la personne a répondu), donc on peut rejouer une vieille
tentative même des années après.

### 2 bis. Mais les participants ne repartent pas de zéro

Quand tu publies une nouvelle version, leurs réponses sont **reportées**
dessus (appariées par clé stable, donc un libellé modifié ne casse rien) :

| Situation du participant | Ce qui se passe |
|---|---|
| Il était **en cours** | Sa tentative passe sur la nouvelle version, il garde ses réponses et découvre les nouvelles questions |
| Il avait **terminé**, rien de nouveau à répondre | Une nouvelle tentative est créée, remplie, et **re-notée aussitôt** |
| Il avait **terminé**, tu as ajouté une question | Une nouvelle tentative l'attend, ses anciennes réponses déjà dedans ; il ne complète que ce qui manque |

**Son ancien résultat n'est jamais touché.** Il en obtient simplement un
nouveau à côté. Une réponse dont la question ou l'option a disparu est
abandonnée, et comptée dans le rapport.

Avant de publier, l'éditeur t'annonce l'effet exact : combien de participants,
combien seront re-notés, combien devront compléter, combien de réponses seront
perdues.

Ça se désactive dans **Réglages → « Reporter les réponses lors d'une nouvelle
version »**, ou ponctuellement en passant `carry_over: false` à la publication.

### 3. Les IDs sont stables

Chaque question et chaque option a une `stable_key` reconduite d'une version
à l'autre. C'est ce qui permet de comparer deux versions et d'écrire des
conditions qui survivent aux changements de libellés.

**Ne jamais référencer une question par sa position.**

### 4. Ça sauvegarde tout seul

Il n'y a pas de bouton « enregistrer mes réponses ». Chaque modification part
au serveur immédiatement. Le bouton **Terminer** ne fait que clôturer et
calculer le score.

Si le réseau tombe : la valeur reste en mémoire + `localStorage`, l'indicateur
passe à *Hors ligne*, et ça repart tout seul au retour. Rien n'est perdu.

---

## L'API

Tout est en JSON, cookie de session + header `X-CSRFToken` (comme le reste du site).

### Côté utilisateur

```http
GET  /api/questionnaires/available/        ce à quoi j'ai droit
POST /api/questionnaires/:id/start/        démarrer (ou reprendre)
GET  /api/questionnaires/:id/current/      où j'en suis
POST /api/questionnaires/:id/answers/      sauvegarder une réponse
GET  /api/questionnaires/:id/state/        resynchroniser après coupure
POST /api/questionnaires/:id/finish/       terminer + calculer le score
GET  /api/questionnaires/:id/results/me/   mon historique
GET  /api/users/:userId/badges/            mes badges
```

Le corps d'un `answers/` :

```json
{
  "question_id": 42,
  "value": {"option_ids": [7]},
  "client_sequence": 3,
  "idempotency_key": "uuid-genere-par-le-client"
}
```

`client_sequence` et `idempotency_key` sont optionnels mais fortement conseillés :
ils évitent qu'une requête en retard écrase une réponse plus récente, et qu'un
rejeu crée un doublon. Une requête périmée revient en `409 stale_write` avec la
valeur actuelle pour que le client se recale.

### Côté admin

```http
POST   /api/questionnaires/                              créer
PUT    /api/questionnaires/:id/                          réglages
DELETE /api/questionnaires/:id/                          archive si utilisé, supprime si vierge
POST   /api/questionnaires/:id/duplicate/
POST   /api/questionnaires/:id/versions/editable/        dériver une version modifiable
GET    /api/questionnaires/:id/versions/compare/?from=1&to=3
GET    /api/questionnaires/:id/versions/:n/impact/         effet du report avant publication
POST   /api/questionnaires/:id/versions/:n/publish/
POST   /api/questionnaires/:id/versions/:n/restore/
POST   /api/questionnaires/:id/versions/:n/invalidate/
GET    /api/questionnaires/:id/attempts/
GET    /api/questionnaires/:id/results/
GET    /api/questionnaires/:id/statistics/
GET    /api/questionnaires/:id/audit/
```

Liste complète : `urls.py`.

---

## Les fichiers

```
question_types.py   les 28 types de questions          ← le point d'extension
services.py         tentatives : start / save / finish
scoring.py          calcul des scores
conditions.py       questions conditionnelles
versioning.py       créer / publier / comparer / restaurer
carryover.py        report des réponses d'une version à la suivante
access.py           qui peut voir, qui peut commencer
permissions.py      droits admin (+ pont avec le Role de mainapp)
editing.py          CRUD questions/options avec validation
snapshots.py        reconstruction d'une tentative passée
serializers.py      admin_* (tout) vs runner_* (sans corrigé)
api.py              endpoints utilisateur
api_admin.py        endpoints admin
http.py             décorateur JSON + gestion d'erreurs
badges.py           attribution des badges
auditing.py         journal
models/             les 12 modèles
```

Front : `static/questionnaire_*.js` + `templates/questionnaires/`.

---

## Ajouter un type de question

C'est le seul fichier à toucher. Exemple complet :

```python
# question_types.py
@register
class PressureType(NumericType):
    id           = "pressure"
    label        = "Pression"
    units        = ("Pa", "hPa", "bar", "psi")
    default_unit = "hPa"
```

C'est tout. Pas de migration (les `choices` viennent d'un appelable), pas de
changement d'API (le catalogue est construit depuis le registre), pas de
changement de front (l'éditeur et le moteur de rendu lisent le catalogue).

Pour un type qui ne rentre dans aucune famille existante, hériter de
`QuestionType` et implémenter `normalize_answer`, `comparable` et
`validate_config`. Voir `CountryType` ou `DateRangeType` comme modèles.

---

## Le scoring

Par défaut : bonne réponse = +1, mauvaise = 0. Configurable par question :

```json
{
  "weight": 2,
  "correct_score": 1,
  "incorrect_score": -0.5,
  "partial": true,
  "partial_mode": "proportional"
}
```

Avec `proportional`, 2 bonnes réponses sur 3 donnent 2/3 des points.
Les autres modes sont `all_or_nothing` et `threshold`.

Au niveau de la version :

```json
{
  "pass_threshold_percent": 60,
  "floor_negative": true,
  "levels": [
    {"name": "Bronze", "min_percent": 50},
    {"name": "Or",     "min_percent": 90}
  ]
}
```

---

## Les conditions

Pour afficher une question seulement si une autre a une certaine réponse :

```json
{
  "question": "<stable_key de la question source>",
  "operator": "EQUALS",
  "value": "<stable_key de l'option>"
}
```

Combinable :

```json
{"op": "OR", "conditions": [
  {"question": "abc", "operator": "LT", "value": 18},
  {"question": "abc", "operator": "GT", "value": 65}
]}
```

Opérateurs : `EQUALS`, `NOT_EQUALS`, `CONTAINS`, `NOT_CONTAINS`, `GT`, `LT`,
`GTE`, `LTE`, `ANSWERED`, `NOT_ANSWERED`. Groupes `AND` / `OR` imbriquables.

Évalué **côté serveur uniquement**. Si une question devient invisible, sa
réponse est conservée mais sort du score — si l'utilisateur revient sur son
choix, elle est toujours là.

---

## Les accès

Format : une liste de groupes. `AND` dans un groupe, `OU` entre les groupes.

```json
[
  [{"rule_type": "ROLE", "role": "Premium"},
   {"rule_type": "BADGE", "badge_code": "BASIC_COMPLETED"}],
  [{"rule_type": "ROLE", "role": "Admin"}]
]
```

Se lit : *(Premium ET badge) OU Admin*.

Types de règles : `EVERYONE`, `USER` (`user_id`), `ROLE` (`role`),
`BADGE` (`badge_code`). `"negate": true` inverse une règle.

Sans aucune règle → ouvert à tout utilisateur connecté.

Trois choses distinctes se règlent séparément :
- **visibilité** — qui voit que ça existe
- **accessibilité** — qui peut le commencer
- **visibilité des résultats** — score, %, réussite, corrigé, explications…
  (8 cases indépendantes)

---

## Pièges

- **Une version en TEST est déjà gelée.** Pour corriger, il faut en dériver une
  nouvelle. C'est voulu (une tentative de test doit rester reproductible), mais
  ça surprend.
- **Publier une version en archive une autre**, mais ceux qui étaient en train
  de répondre dessus peuvent terminer : une version archivée accepte encore les
  tentatives déjà ouvertes. Une version *désactivée* ou *invalidée*, non — c'est
  une décision délibérée.
- **Une tentative reportée ne consomme pas de tentative.** Sinon publier une
  nouvelle version enfermerait dehors tous ceux qui ont un quota de 1.
- **Le type `city` refuse d'être créé sans liste de villes.** Pas de saisie
  libre : `{"cities": [{"code": "PAR", "name": "Paris"}]}`.
- **`DELETE` n'efface pas** un questionnaire qui a des tentatives, il l'archive.
  Normal : les résultats doivent rester.
- **Les badges sont attribués mais pas affichés.** Le modèle et l'API tournent,
  l'UI n'est pas branchée (c'était demandé comme ça).
- **L'expiration des tentatives** est constatée à la lecture. Un balayage
  `expire_stale_attempts()` existe mais n'est branché sur aucun cron.
- **Dérive préexistante de `mainapp`** : `Role.user` est `ForeignKey` dans le
  code et `OneToOneField` en base, donc `makemigrations` (lancé par le
  Dockerfile) génère une migration `0007` à chaque démarrage. Antérieur à ce
  module, pas touché.

---

## Tests

```bash
python manage.py test profils.questionnaires --parallel 4
```

213 tests : types de questions, versioning, tentatives, autosave, concurrence,
permissions, scoring, conditions, mode test, badges, API.

Les trois qui comptent le plus :

- `test_results_are_immune_to_later_edits` — un résultat reste identique après
  réécriture complète du questionnaire
- `test_a_test_attempt_never_awards_a_real_badge` — l'étanchéité du mode TEST
- `test_a_late_request_never_overwrites_a_newer_answer` — l'anti-écrasement

Le détail de l'architecture et des arbitrages est dans le dossier de conception.
