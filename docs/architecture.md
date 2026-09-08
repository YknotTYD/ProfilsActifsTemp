# Architecture du code

Ce document explique **tout le code du projet** : ce que fait chaque brique,
pourquoi elle est là, et comment les briques se parlent. Il complète les
documents plus ciblés :

- [`docs/professional-profiles.md`](professional-profiles.md) — la section profils, vue produit
- [`profils/profiles/README.md`](../profils/profiles/README.md) — le module profils, vue technique
- [`profils/questionnaires/README.md`](../profils/questionnaires/README.md) — le module questionnaires, vue technique
- [`swagger.yaml`](../swagger.yaml) — le contrat OpenAPI de l'API profils

---

## 1. En une phrase

**ProfilsActifs** est un réseau social de mise en relation entre demandeurs
d'emploi et recruteurs : un candidat publie une vidéo de présentation et un
profil professionnel structuré, un recruteur le trouve par la recherche ou la
grille de profils, le contacte par messagerie, et des questionnaires versionnés
permettent d'évaluer et de certifier les candidats.

C'est un projet **Django monolithique** (pas de framework d'API, pas de SPA) :
le serveur rend du HTML, et les pages interactives dialoguent ensuite avec une
API JSON maison. Base **SQLite**, CSS **Tailwind** compilé, JavaScript **vanilla**
sans build.

---

## 2. Carte du dépôt

```
manage.py                   point d'entrée Django
setup                       script Docker (install / run / start / stop / shell / logs)
Dockerfile, compose.yaml    conteneurisation
pyproject.toml, uv.lock     dépendances Python (uv)
package.json                dépendances front (Tailwind CLI, concurrently)
swagger.yaml                contrat OpenAPI de l'API profils
db.sqlite3                  la base (versionnée, peuplée par le workflow Build)

profils/                    le projet Django
├── settings.py             configuration
├── urls.py                 routage racine + redirections héritées
├── wsgi.py / asgi.py       points d'entrée serveur
├── mainapp/                socle : comptes, rôles, accueil, vidéos historiques
├── profiles/               profils professionnels, compétences, recherche, vidéos
├── questionnaires/         questionnaires versionnés, tentatives, scoring, badges
├── messaging/              conversations entre deux utilisateurs
└── notifications/          centre de notifications

templates/                  gabarits Django (racine + un dossier par module)
static/                     CSS compilé, JS, polices, images
static/src/input.css        source Tailwind (compilée vers static/style.css)
media/videos/               fichiers vidéo téléversés
public/                     images des témoignages
docs/                       cette documentation
```

### Deux dossiers à connaître

- `profils/mainapp/managment/` (sans le `e`) est un **doublon** de
  `profils/mainapp/management/`. Seul le second est chargé par Django ; le
  premier est un reliquat.
- `profils/questionnaires/management/` n'est pas encore suivi par git au moment
  où ce document est écrit.

---

## 3. Le socle Django

### `profils/settings.py`

Configuration volontairement minimale :

- `SECRET_KEY` vient de `.env` (via `python-dotenv`), `DEBUG = True` — c'est un
  projet d'école, **la configuration n'est pas durcie pour la production**.
- Cinq apps maison : `mainapp`, `questionnaires`, `profiles`, `notifications`,
  `messaging`.
- Un context processor maison, `mainapp.context_processors.navigation`.
- Un middleware maison, `mainapp.middleware.NoCacheStaticFilesMiddleware` : en
  `DEBUG`, il pose `Cache-Control: no-cache` sur toutes les réponses pour qu'une
  modification locale de CSS ou de JS se voie au rechargement suivant.
- Base SQLite, statiques dans `static/`, médias dans `media/`.

### `profils/urls.py`

Routage racine. Il monte les pages de `mainapp` explicitement, puis inclut les
`urls.py` des quatre autres modules **à la racine** (`path("", include(...))`) :
chaque module déclare donc ses chemins complets, ce qui garde le style plat du
projet (`/profiles/`, `/questionnaires/`, `/messages/`).

Il porte aussi trois **redirections 301** héritées : `/feed/`, `/api/feed/` et
`/api/videos/feed/` renvoient vers `/`. Le feed vertical a été remplacé par une
grille de profils paginée, mais ses adresses avaient circulé par mail et par
lien partagé — elles mènent à la grille plutôt qu'à une 404, en conservant la
query string.

### `mainapp/context_processors.navigation`

Une seule source de vérité pour la barre de navigation. Avant, chaque vue
décidait quels liens afficher en passant (ou en oubliant) `can_manage`,
`capabilities`, `can_message`... : la barre changeait d'une page à l'autre.
Tout est calculé ici une fois — rôle, libellé du rôle, `is_admin`, `is_staff`,
`is_recruiter`, `can_moderate_videos`, `can_manage_questionnaires` — et
`templates/partials/_navbar.html` n'a plus qu'à lire `nav`.

---

## 4. `mainapp` — le socle applicatif

C'est l'app historique : comptes, rôles, page d'accueil, et le premier système
de vidéos (antérieur à `profiles`).

### Modèles (`mainapp/models.py`)

| Modèle | Rôle |
|---|---|
| `Role` | rôle de l'utilisateur (`Recruiter` / `JobSeeker` / `Admin`) + date de naissance |
| `VideoLink` | vidéo de présentation soumise **par lien**, avec statut de modération |
| `VideoFile` | vidéo de présentation soumise **par fichier**, même cycle de modération |
| `Reaction` | like / dislike d'un utilisateur sur une `VideoLink` |

Deux détails qui expliquent le code :

- `strings_to_choice_char_fields(strings)` construit un `CharField` avec
  `choices` et `max_length` déduits d'un tuple de `constants.py`. Ajouter un
  rôle ou un statut se fait dans `constants.py`, pas dans le modèle.
- `VideoLink.likes` / `.dislikes` sont des **propriétés greffées après coup**
  (`VideoLink.likes = property(get_likes)`), pas des colonnes : elles comptent
  les `Reaction` à la lecture.
- Un `post_delete` supprime le fichier d'une `VideoFile` détruite, pour ne pas
  laisser d'orphelins dans `media/videos/`.
- `clean()` refuse un statut `REJECTED` sans motif — vérifié par le formulaire
  d'administration à chaque changement de statut.

> **État actuel** : la modération de ces deux modèles est **désactivée
> temporairement** dans les vues — `get_videos` et `get_video_filepaths`
> affichent toutes les vidéos quel que soit leur `status`. La modération réelle
> vit désormais dans `profiles` (`ProfileVideo`).

### Vues (`mainapp/views.py`)

- `main` — la page d'accueil `/`. Son contenu dépend du rôle :
  un recruteur ou un admin voit la **grille de profils**, un candidat voit le
  **statut de sa vidéo de présentation**.
- `candidate_grid` — pagine la grille à 20 profils par page
  (`constants.CANDIDATE_GRID_PAGE_SIZE`). Les deux sources de vidéos (`VideoLink`
  et `VideoFile`) n'ont pas de colonne d'ordre commune : elles sont assemblées en
  mémoire puis paginées. `get_page` absorbe les numéros absurdes (`?page=abc`,
  `?page=999`) plutôt que de renvoyer une erreur.
- `_candidate(user)` — la carte d'identité affichée sous une vignette. Elle est
  tirée du **profil professionnel** (`profiles`) : la grille n'a pas sa propre
  notion de candidat. Un utilisateur sans profil retombe sur son nom
  d'utilisateur au lieu de casser la page.
- `_my_video_status(user)` — résumé de la vidéo de présentation du candidat, lu
  dans `profiles.ProfileVideo`, la même source que `/profiles/me/video/`. Le
  formulaire de la page d'accueil postait autrefois vers `mainapp.VideoLink`,
  créant un second système de modération invisible du panneau dédié.
- `register` / `login` / `logout` / `quiz` / `cgu` — pages simples.
  `quiz` liste les questionnaires visibles par l'utilisateur en réutilisant
  `questionnaires.access.visible_questionnaires`.
- `health` — sonde `/health/` : ouvre un curseur sur la base et répond 503 si
  elle est indisponible.

### API (`mainapp/api.py`)

Formulaires HTML classiques (POST + redirection), pas du JSON :

- `register` — vérifie unicité du nom, correspondance des mots de passe,
  politique de mot de passe Django, date de naissance valide, et **âge minimum
  de 18 ans** (`_age_on` compte les années révolues, pas la différence
  d'années). Les erreurs repartent en query string vers `/register/` avec les
  champs déjà saisis.
- `login` — authentifie et redirige.
- `video_upload` — normalise l'URL (`https://` forcé, lien YouTube `watch?v=`
  converti en `embed/`) et crée une `VideoLink`.
- `video_delete` — suppression par son propriétaire uniquement (le filtre porte
  sur `user = request.user`).
- `react` — pose ou remplace un like/dislike, et **notifie le propriétaire** via
  `notifications.services.notify` si la réaction est nouvelle et qu'il ne s'agit
  pas de sa propre vidéo.
- `videofile_upload` — enregistre un fichier dans `media/videos/`. **Non routé** :
  aucune entrée d'`urls.py` n'y mène (le téléversement de fichier passe désormais
  par `/api/profiles/me/videos/file/`, dans `profiles`).

### Commande `seed_demo`

`python manage.py seed_demo` crée les trois comptes de démonstration
(`demo.admin`, `demo.recruteur`, `demo.candidat`, mot de passe réglable par
`DEMO_PASSWORD`) avec leurs profils, compétences et questionnaires. Le workflow
GitHub `Build` l'exécute à chaque push sur `main` et publie l'application prête
à l'emploi, base peuplée comprise, en artefact.

---

## 5. `profiles` — les profils professionnels

Le module le plus gros. Il est **autonome** : il ne touche pas à `mainapp`, il
réutilise seulement le rôle (`mainapp.Role`, via le pont de
`questionnaires.permissions`) et le compte utilisateur.

### 5.1 Le modèle de données

```
User
 └── ProfessionalProfile              titre, résumé, localisation, disponibilité, mobilité
      ├── ProfileVisibility            visibilité de chaque section, indépendamment
      ├── ProfileSearchSettings        searchable, appear_in_video_feed, contactable_by_recruiters
      ├── ProfileContractType          CDI, CDD, stage, alternance, freelance…
      ├── ProfileLink                  GitHub, portfolio, LinkedIn…
      ├── UserSkill        ──> Skill   compétence + niveau + années d'expérience
      │                        └── SkillAlias   autres orthographes du même mot
      ├── WorkExperience    ── WorkExperienceSkill   ──> Skill
      ├── Education         ── EducationSkill        ──> Skill
      ├── Certification     ── CertificationSkill    ──> Skill
      ├── UserLanguage      ──> Language             niveau CECRL
      ├── Project           ── ProjectSkill          ──> Skill
      └── ProfileVideo      ── ProfileVideoSkill     ──> Skill
           ├── VideoModerationEvent    historique complet des changements de statut
           ├── ProfileVideoView        une ligne par (spectateur, vidéo)
           └── ProfileVideoReaction    like / dislike
```

Tout est **normalisé** : aucune compétence n'est stockée en texte libre, sinon
la recherche par compétence serait impossible à rendre performante.

Les entrées datées (`WorkExperience`, `Education`) héritent d'une classe
abstraite `DatedEntry` (`start_date`, `end_date`, `is_current`, `order`), et les
tables de liaison compétence héritent de `SkillLink`.

### 5.2 `skills.py` — le référentiel canonique

Le problème : `Java`, `java` et `JAVA` doivent être **une seule ligne en base**.

Chaque nom saisi est réduit à une **clé normalisée** (`slug`), et c'est elle qui
porte l'unicité. La normalisation traite d'abord les caractères qui ont un sens
dans les noms techniques, avant de réduire le reste — un `slugify` naïf
écraserait `C++`, `C#` et `C` sur la même clé :

```
C++          -> cpp
C#           -> csharp
.NET         -> net
ASP.NET      -> asp-net
Objective-C  -> objective-c
JAVA / java  -> java
```

Deux noms différents qui désignent la même compétence (`NodeJS` / `Node.js`) ne
se rejoignent pas par normalisation : c'est le rôle de `SkillAlias`, qui pointe
une clé normalisée supplémentaire vers une compétence existante.

Fonctions clés : `normalize_skill_name`, `find_skill` (alias compris),
`resolve_skill` (crée au besoin, via `get_or_create` pour être insensible à la
concurrence), `resolve_skills` (liste dédoublonnée), `resolve_skill_reference`
(accepte un `id`, un slug ou un nom libre — le front envoie l'un ou l'autre),
et `add_alias` (qui refuse de fusionner deux compétences distinctes : c'est une
opération d'administration, pas un effet de bord).

Ce module **n'importe aucun modèle au chargement** : `models/skill.py` a besoin
de `normalize_skill_name`, et l'import inverse créerait un cycle.

### 5.3 `visibility.py` — trois réglages indépendants

C'est le point le plus facile à mal comprendre :

| Réglage | Question à laquelle il répond |
|---|---|
| `profile.visibility` | qui peut **ouvrir la page** du profil ? |
| `ProfileVisibility.<section>_visibility` | qui voit **cette section** une fois la page ouverte ? |
| `ProfileSearchSettings.searchable` | le profil apparaît-il **dans les résultats** ? |

Trois valeurs de visibilité (`PUBLIC` / `REGISTERED_USERS` / `PRIVATE`), trois
niveaux d'audience (`ANONYMOUS` = 0, `REGISTERED` = 1, `OWNER` = 2).

**La règle qui évite les mauvaises surprises** : la visibilité effective d'une
section est **la plus restrictive des deux**. Régler ses compétences sur
`PUBLIC` ne les sort pas d'un profil `PRIVATE`. Sans cet arbitrage, rendre son
profil privé laisserait fuir toutes les sections restées ouvertes.

`searchable` est **totalement indépendant** et n'a aucune exception, pas même
pour un administrateur : c'est un choix de l'utilisateur, pas une permission.

`PreviewViewer` est un visiteur simulé pour la prévisualisation du profil
public (`?preview=`). Son audience est plafonnée à `REGISTERED`, si bien qu'une
prévisualisation ne peut que **restreindre** ce qui est montré, jamais l'élargir.

Un profil privé répond **404, pas 403** — répondre « interdit » confirmerait au
passage que ce nom d'utilisateur possède un profil.

### 5.4 `permissions.py` — rôles et propriété

- Le pont vers `mainapp.Role` n'est pas réécrit : il vient de
  `questionnaires.permissions.user_roles`, qui agrège déjà `Role`, les groupes
  Django et `is_superuser` / `is_staff`.
- `is_platform_admin` **mémorise son résultat sur l'instance `User`**
  (`_profiles_is_admin_cache`). Sans cela, servir une page de résultats de
  recherche relancerait deux requêtes par ligne de résultat. L'instance ne
  survit pas à la requête, donc rien ne peut être périmé.
- `assert_can_edit` est le **seul verrou d'écriture** : on ne modifie que ses
  propres données professionnelles.
- `assert_owns_child` vérifie en plus le **rattachement de l'objet** : la route
  porte `/profiles/me/...`, mais l'identifiant de l'expérience, lui, vient du
  client. Sans ce second contrôle, un propriétaire légitime pourrait modifier
  l'expérience d'un autre en devinant son identifiant.
- Trois permissions applicatives : `profiles.manage_skill_catalog`,
  `profiles.view_private_profile`, `profiles.moderate_profile`. Être recruteur
  ne donne **aucun** accès particulier aux profils privés.

### 5.5 `search.py` + `ranking.py` — la recherche

**Tout se passe en base.** Les filtres sont des `WHERE`, le score est une
expression annotée, le tri et la pagination sont un `ORDER BY` et un `LIMIT` : à
aucun moment l'ensemble des profils n'est ramené en mémoire pour être trié ou
filtré ensuite.

`ProfileQuery.from_params(GET)` valide et normalise les critères ; la page de
recherche les revalide côté serveur, ce qui permet de **partager une URL avec
ses filtres** et de la retrouver telle quelle.

Deux garde-fous appliqués avant tout le reste, dans `base_queryset` :
un profil non `searchable` n'apparaît jamais pour personne, et la visibilité du
profil est comparée à l'audience du visiteur.

Combinaison des compétences : en `AND`, un `.filter()` par compétence (donc une
jointure distincte par compétence, ce qui exige qu'elles soient toutes
présentes) ; en `OR`, un seul `__in`.

Le classement (`ranking.relevance_expression`) calcule chaque composante par une
**sous-requête** plutôt que par une jointure agrégée : une requête qui joint à la
fois compétences et langues verrait chaque somme multipliée par le nombre de
lignes de l'autre relation. Les poids vivent dans `constants.RANKING_WEIGHTS` —
ajouter un critère, c'est écrire une composante de plus et lui donner un poids,
sans réécrire la fonction.

```
GET /api/profiles/search/?skill=java&skill=docker&mode=AND
    &min_level=INTERMEDIATE&contract=CDI&available=1&sort=relevance&page=2
```

### 5.6 `moderation.py` — la machine à états vidéo

Point d'entrée **unique** pour tout changement de statut d'une `ProfileVideo` :

```
DRAFT ──(propriétaire)──> PROCESSING ──(système)──> PENDING ──(admin)──> APPROVED
                              │                        │                    │
                              └──(système)──> REJECTED ─┘        (propriétaire) │
                                                 │                              ▼
                                    (propriétaire, re-soumission)          PUBLISHED
                                                                                │
                                                          (propriétaire/admin/système)
                                                                                ▼
                                                                             HIDDEN
```

Une transition absente de `constants.VIDEO_TRANSITIONS` est **refusée**, pas
exécutée sur la foi de l'appelant. Chaque changement écrit son
`VideoModerationEvent` (acteur, date, ancien et nouveau statut, raison) dans la
**même transaction** que la mise à jour.

Séparation volontaire avec `permissions.py` : ce module ne décide jamais si
*l'utilisateur courant* a le droit d'agir sur *cette* vidéo (c'est le travail de
`assert_owns_child` / `has_perm`, appelé par la vue avant) ; il vérifie
seulement que le **type d'acteur** annoncé (`OWNER`, `ADMIN`, `SYSTEM`) a le
droit de faire *cette* transition. `user` ne sert qu'à l'attribution dans
l'historique — il peut être `None` pour un traitement automatique.

`archive_stale_rejections()` archive les refus sortis de la fenêtre vivante
(`settings.REJECTION_HISTORY_DAYS`, 7 jours par défaut). La console de
modération archive aussi paresseusement à chaque lecture ; la commande
`python manage.py archive_moderation_history` sert à garder la table propre
sans dépendre d'un passage d'administrateur.

### 5.7 Les autres fichiers

| Fichier | Rôle |
|---|---|
| `services.py` | **toute** la logique d'écriture. Aucune charge utile n'est appliquée en bloc : liste blanche de champs + nettoyage par type. Un `**payload` laisserait un client fixer `total_experience_months` ou `level_rank`, qui sont calculés. Les valeurs dérivées sont recalculées à l'écriture. |
| `api.py` | couche de **transport uniquement**. Les routes `/me/` opèrent toujours sur le profil de l'utilisateur connecté, jamais sur un identifiant client. |
| `serializers.py` | deux familles : `owner_*` (vue complète, réglages compris) et `public_*` (vue visiteur, **construite par omission**). Une section interdite est **absente** de la réponse, pas présente avec `visible: false` — une donnée envoyée au navigateur est une donnée divulguée. |
| `views.py` | pages. La page de profil est rendue **côté serveur** à partir de la charge déjà expurgée : lisible sans JavaScript, et une section masquée est absente du HTML, pas cachée en CSS. |
| `http.py` | décorateur `api` propre au module ; les primitives d'enveloppe (`ok`, `fail`, `body`, `BadRequest`) sont **importées** de `questionnaires/http.py` pour ne pas avoir deux formats d'erreur. |
| `engagement.py` | vues (`register_view`, une seule par spectateur+vidéo) et réactions (`set_reaction`) du feed vidéo, avec notification du propriétaire. |
| `feed.py` | chaînon *recherche → profils → vidéos de ces profils* (`video_candidates`, `videos_for_skills`) et `playback()`, qui dit comment lire une vidéo quelle que soit sa source. **N'expose aucune route.** |
| `matching.py` | préparation du rapprochement candidat/offre. `profile_features` extrait le vecteur comparable d'un profil ; `query_from_offer` traduit une offre en `ProfileQuery`. **Le matching lui-même n'est pas implémenté** — il n'existe pas encore de modèle d'offre. |
| `constants.py` | tout le vocabulaire : niveaux, contrats, visibilités, sections, statuts vidéo, transitions, poids de classement. |

### 5.8 Les pages

| URL | Qui | Quoi |
|---|---|---|
| `/profile/<username>/` | selon la visibilité | profil public (rendu serveur) |
| `/profile/` | connecté | redirige vers son propre profil (**le crée s'il n'existe pas**) |
| `/profiles/` | tout le monde | recherche de profils |
| `/profiles/edit/` | connecté | édition par onglets |
| `/profiles/me/video/` | connecté | sa vidéo de présentation (une seule active) |
| `/profiles/admin/videos/` | modérateur | console de modération (404 sinon, pas 403) |

---

## 6. `questionnaires` — les questionnaires versionnés

App autonome elle aussi. Voir le [README du module](../profils/questionnaires/README.md)
pour le détail ; voici les idées structurantes.

### 6.1 Les quatre principes

**1 — Une version publiée ne se modifie jamais.**
Un questionnaire est une identité + une pile de versions
(`DRAFT` → `TEST`/`PUBLISHED` → `ARCHIVED`). Une version est modifiable
uniquement en `DRAFT` **et** sans aucune tentative. Modifier un questionnaire
figé revient à en dériver une nouvelle version, copie conforme.

**2 — Chaque réponse est collée à sa version.**
`Tentative → Version exacte → Réponses → Résultat`. On peut réécrire l'énoncé,
inverser la bonne réponse : les scores déjà calculés ne bougent pas. En plus,
chaque réponse embarque un **snapshot** (énoncé et libellés au moment de la
réponse), donc on peut rejouer une vieille tentative des années après. Le
snapshot ne contient **jamais** le corrigé, pour éviter toute fuite.

**2 bis — Mais les participants ne repartent pas de zéro** (`carryover.py`).
À la publication d'une nouvelle version, une tentative *en cours* est déplacée
telle quelle ; une tentative *terminée* n'est jamais touchée, mais une nouvelle
tentative pré-remplie est créée à côté et re-notée aussitôt s'il ne manque rien.
L'appariement se fait par **clé stable**, jamais par identifiant. Avant de
publier, l'éditeur annonce l'effet exact (combien de participants, de re-notes,
de réponses perdues).

**3 — Les identifiants sont stables.**
Chaque question et chaque option porte une `stable_key` reconduite d'une version
à l'autre. C'est ce qui permet de comparer deux versions, d'écrire des
conditions qui survivent aux changements de libellés, et d'exporter/importer un
questionnaire entre instances. **Ne jamais référencer une question par sa
position.**

**4 — Ça sauvegarde tout seul.**
Aucun bouton « enregistrer mes réponses » : chaque modification part
immédiatement. Une file par question, la dernière valeur gagne, une requête à la
fois. Chaque envoi porte une **clé d'idempotence** et un **numéro de séquence** :
un rejeu est sans effet, et une requête en retard ne peut pas écraser une valeur
plus récente (elle revient en `409 stale_write` avec la valeur courante, pour que
le client se recale). En cas de coupure, la valeur reste en mémoire +
`localStorage` et repart au retour de la connexion.

### 6.2 Le registre de types de questions

`question_types.py` (1 300 lignes) est **le point d'extension principal** :
29 types répartis en familles (`ChoiceType`, `NumericType`, `TemporalType`,
`DateRangeType`, `VocabularyType`, `AddressType`).

Un handler est responsable de quatre choses, et de rien d'autre :

| Méthode | Rôle |
|---|---|
| `validate_config` | valider la configuration saisie par l'admin |
| `normalize_answer` | transformer la saisie brute du client en **valeur canonique** JSON |
| `evaluate` | comparer la valeur canonique aux réponses attendues → ratio 0..1 |
| `comparable` | exposer une valeur comparable pour les conditions |

Ajouter un type, c'est écrire une sous-classe décorée `@register` — et rien
d'autre : pas de migration (les `choices` viennent d'un appelable), pas de
changement d'API (le catalogue est construit depuis le registre), pas de
changement de front (l'éditeur et le moteur de rendu lisent le catalogue).

### 6.3 Les autres fichiers

| Fichier | Rôle |
|---|---|
| `services.py` | cycle de vie des tentatives : start / save / resume / finish. Rien n'est accordé sur la foi du client. |
| `scoring.py` | moteur de scoring, séparé de l'affichage et des modèles. Poids, score correct/incorrect, partiel (`proportional`, `all_or_nothing`, `threshold`), seuil de réussite, paliers. |
| `conditions.py` | arbre JSON `AND`/`OR` avec 10 opérateurs, référencé par clés stables. **Évalué exclusivement côté serveur** : le front ne reçoit que les questions visibles. Une question devenue invisible garde sa réponse mais sort du score. |
| `versioning.py` | créer / publier / comparer / restaurer. Restaurer une ancienne version en crée une nouvelle à partir d'elle ; l'ancienne n'est jamais réécrite. |
| `access.py` | visibilité / accessibilité / visibilité des résultats — trois questions distinctes, réglées séparément. Règles en forme normale disjonctive (`AND` dans un groupe, `OR` entre groupes), types `EVERYONE` / `USER` / `ROLE` / `BADGE`, avec `negate`. |
| `permissions.py` | 10 permissions personnalisées déclarées sur `Questionnaire.Meta` (plus les 4 CRUD de Django, soit 14 constantes `PERM_*`), et le pont vers `mainapp.Role` (`user_roles`) réutilisé par `profiles`. |
| `editing.py` | CRUD questions/options, avec vérification que la version est modifiable + validation par le handler de type + journalisation. |
| `snapshots.py` | reconstruction d'une tentative passée. |
| `porting.py` | export/import JSON **portable** : aucune clé primaire, uniquement des clés stables. L'import passe par les mêmes fonctions de création que l'éditeur. |
| `badges.py` | attribution des badges (`@criterion` pour ajouter un critère). Une tentative en mode TEST n'attribue **jamais** de badge réel. |
| `auditing.py` | journal d'audit, point d'entrée unique. |
| `serializers.py` | `admin_*` (tout) vs `runner_*` / `public_*` (**sans corrigé**). C'est la garantie qu'un corrigé ne fuit pas par mégarde. |
| `api.py` / `api_admin.py` | endpoints utilisateur / admin. Chaque endpoint admin déclare la permission qu'il exige, vérifiée par le décorateur. |
| `http.py` | la petite couche HTTP JSON du projet (parsing, enveloppe d'erreur, méthode, permission) — **réutilisée par `profiles`, `messaging` et `notifications`**. |

### 6.4 Les modèles (12)

`Questionnaire` (identité + réglages : tentatives max, cooldown, limite de
temps, navigation, `carry_over_answers`, `result_visibility`),
`QuestionnaireVersion`, `Question`, `QuestionOption`,
`QuestionnaireAccessRule`, `QuestionnaireAttempt`, `UserAnswer`,
`UserAnswerSelection`, `QuestionnaireResult`, `Badge` (+ attribution),
`AuditLog`.

Le modèle est **normalisé** : questions, options et sélections d'options sont de
vraies lignes, ce qui garde possibles les statistiques et l'analyse. Le JSON
n'est utilisé que pour ce qui est réellement propre à un type de question
(`config`, `expected_config`, `scoring_config`, `condition`).

### 6.5 Commande `normaliser_certification`

`python manage.py normaliser_certification [--apply] [--json rapport.json]`

Réécrit les libellés fautifs du dispositif de certification : un badge
**valorise un parcours évalué**, il n'ouvre aucun droit — les formulations du
type « permis de travailler » sont proscrites. La commande compte les
passations et les badges avant et après, et **échoue bruyamment** si les
compteurs diffèrent : elle ne change que des mots. Le mode par défaut est une
simulation ; il faut `--apply` pour écrire. Rejouable sans effet.

---

## 7. `messaging` — les conversations

Petit module, mais avec une décision d'architecture explicite.

### Modèles

- `Conversation` — `initiator` + `recipient`, avec une **contrainte d'unicité**
  sur la paire : cliquer « Contacter » deux fois ne crée pas un second fil.
  Le `context` est une **clé étrangère générique** (`content_type` + `object_id`) :
  d'où est partie la conversation (une vidéo, un profil…) sans avoir à ajouter
  une colonne par source possible.
- `Message` — `conversation`, `sender`, `body` (tronqué à 4 000 caractères).

### `rules.py` — l'extensibilité, concrètement

Chaque règle d'ouverture est une fonction indépendante `(sender, recipient) -> bool`
enregistrée par décoration `@rule`. `can_start` autorise **dès qu'une règle le
permet**.

La seule règle active aujourd'hui est *« un recruteur peut contacter un
demandeur d'emploi ayant publié une vidéo »*. « Les autres types d'utilisateurs
ne peuvent pas initier ce type de contact » est tenu simplement **en n'écrivant
aucune autre règle**. En ajouter une plus tard n'oblige à toucher ni celle-ci ni
ses appelants.

`_has_a_published_video` reconnaît **les deux** chemins vidéo du projet
(`profiles.ProfileVideo` publiée et `mainapp.VideoLink` approuvée) : tant qu'ils
ne sont pas unifiés, ne regarder qu'un seul rendrait injoignable tout candidat
passé par l'autre.

**Répondre** dans une conversation ouverte n'est pas gouverné par ces règles :
c'est une question de participation (`Conversation.has_participant`), et les deux
participants y ont toujours droit.

### Pages

`/messages/` (liste), `/messages/start/` (POST), `/messages/<id>/` (fil, GET
affiche / POST ajoute puis redirige — pour éviter un renvoi au rafraîchissement).
De simples formulaires, dans le style de `mainapp` : pas besoin de JavaScript
pour lire et envoyer un message.

---

## 8. `notifications` — le centre de notifications

### Un seul modèle pour tous les types

`Notification` : `recipient`, `type` (`CharField` libre), cible **générique**
(`content_type` + `object_id`), `payload` JSON, `url`, `read_at`, `created_at`,
avec un index sur `(recipient, read_at, -created_at)`.

Deux choix expliquent la forme :

- **Cible générique** plutôt qu'une colonne par source (`video_id`,
  `message_id`, `profile_id`…), qui grossirait à chaque nouveau type.
- **`type` en `CharField` libre**, vérifié à l'écriture contre `types.py`,
  jamais par un `choices=` figé dans une migration. Ajouter un type — « candidature
  reçue », demain — est **une ligne**, pas une migration.

Types actuels : `VIDEO_APPROVED`, `VIDEO_REJECTED`, `VIDEO_HIDDEN`,
`NEW_MESSAGE`, `VIDEO_LIKED`, `VIDEO_DISLIKED`.

### `services.notify()` — le point d'entrée unique

Les autres apps l'appellent sans jamais toucher au modèle. C'est ce qui permet
d'ajouter un canal (email, push) plus tard **dans cette seule fonction**, sans
modifier ses appelants. `recipient is None` est un no-op silencieux, pour que
l'appelant n'ait pas à vérifier ce cas à chaque site d'appel.

### API

```http
GET  /api/notifications/               les 50 dernières + compte non-lus
GET  /api/notifications/unread-count/
POST /api/notifications/read-all/
POST /api/notifications/<id>/read/
```

---

## 9. Le frontend

Pas de framework, pas de bundler pour le JS. Deux briques :

### CSS

**Tailwind CSS 4** en CLI. La source est `static/src/input.css` (903 lignes,
avec les composants du projet) ; elle est compilée en `static/style.css` :

```bash
npm run build:css      # une passe, minifiée
npm run watch:css      # en continu
npm run dev            # Django + Tailwind en parallèle (concurrently)
```

`static/profiles.css` et `static/questionnaires.css` complètent, par module.

### JavaScript

Onze fichiers, chargés en `<script>`, sans build. Le socle commun est
`questionnaire_common.js`, qui expose :

- **`QAPI`** — un client `fetch` qui pose le `X-CSRFToken` lu dans la balise
  `<meta>`, envoie les cookies (`same-origin`) et déballe l'enveloppe JSON.
  Utilisé par **toutes** les pages interactives, y compris celles des profils.
- **`qEl`** — construction d'éléments DOM.
- **`QSaveIndicator`** — l'indicateur d'état de sauvegarde.

| Fichier | Rôle |
|---|---|
| `navbar.js` | menus déroulants + centre de notifications |
| `candidates_grid.js` | grille d'accueil. **Rien ne joue tant qu'on n'a rien demandé** : le gabarit ne pose qu'une vignette et un bouton « Lire » ; le `<video>` / `<iframe>` n'existe qu'à partir du clic et disparaît dès qu'on ouvre une autre carte. Une seule vidéo à la fois. |
| `profiles_editor.js` | édition du profil par onglets. Chaque onglet lit et écrit **directement l'API** : pas d'état intermédiaire à synchroniser, donc pas d'onglet qui affiche des données périmées. |
| `profiles_search.js` | **ne filtre rien** : il construit une requête, l'envoie à `/api/profiles/search/` et affiche ce que le serveur renvoie déjà trié, paginé et classé. |
| `questionnaire_runner.js` | passage d'un questionnaire (voir §6.1, principe 4) |
| `questionnaire_editor.js` | éditeur. **L'administrateur ne voit jamais de JSON** : chaque type décrit ses champs via `/api/questionnaires/types/`, et l'éditeur en construit un vrai formulaire. Le JSON reste accessible dans un bloc « Réglages avancés » replié. |
| `questionnaire_fields.js` | rendu des champs **piloté par la description renvoyée par l'API** : ajouter un type côté serveur ne demande ici qu'un cas de plus. |
| `questionnaire_admin.js` / `_attempts.js` / `_preview.js` | liste d'administration, suivi des tentatives, prévisualisation |

### Templates

`templates/` à la racine (accueil, inscription, connexion, CGU, quiz, grille,
pages d'erreur 400/403/404/500), plus un dossier par module. Les partiels
communs sont dans `templates/partials/` (`_navbar.html`, `_footer.html`,
`_testimonials.html`).

Principe constant : **les gabarits ne portent aucune logique métier.** Ils
reçoivent un état initial déjà expurgé et, pour les pages interactives,
dialoguent ensuite avec l'API.

---

## 10. Les motifs transverses

Ce sont eux qui donnent au projet sa cohérence malgré cinq apps distinctes.

### Une seule couche HTTP JSON

Le projet n'utilise **pas de framework d'API**. `questionnaires/http.py` fournit
le strict nécessaire — `ok`, `fail`, `body`, `get_int`, `get_bool`,
`BadRequest`, et un décorateur `api(methods, permission=...)` qui vérifie
méthode, authentification et permission. `profiles`, `messaging` et
`notifications` **l'importent** plutôt que de le recopier : sinon les modules
répondraient un jour avec trois formats d'erreur différents. Chacun n'ajoute
que son propre décorateur `api`, pour traduire ses exceptions métier.

### Vue → service → modèle

Partout : `api.py` / `views.py` ne font que du transport, `services.py` porte la
logique et la validation, `permissions.py` et `visibility.py` décident des accès.
**Aucune vue ne décide seule de ce qu'elle a le droit de renvoyer.**

### Rien n'est cru sur parole

La version utilisée, le numéro de tentative, la visibilité des questions, le
verrouillage des réponses, le score, l'appartenance d'un objet à un profil : tout
est déterminé **côté serveur**. Le frontend n'est jamais considéré comme fiable.

### Filtrer par omission, pas par drapeau

Une donnée que le visiteur n'a pas le droit de voir est **absente** de la
réponse — jamais présente avec un `visible: false`. Une donnée envoyée au
navigateur est une donnée divulguée, quoi que le front en fasse ensuite.

### 404 plutôt que 403

Un profil privé, une console d'administration : la réponse est 404. Répondre
« interdit » confirmerait l'existence de la ressource.

### Le travail se fait en base

Recherche, classement, tri, pagination, filtrage des vidéos visibles : tout est
exprimé en SQL. Rien n'est ramené en mémoire pour être filtré ensuite.

### Registres plutôt que `choices=` figés

Types de questions (`@register`), critères de badge (`@criterion`), règles de
messagerie (`@rule`), types de notification (dictionnaire) : chacun s'étend par
une déclaration, **sans migration**.

---

## 11. Lancer, tester, déployer

### En local

```bash
python manage.py migrate
npm run dev                  # Django + Tailwind en parallèle
```

### Avec Docker

```bash
./setup run [port]           # démarre (8080 par défaut) puis nettoie à la sortie
./setup start [port]         # démarre et laisse tourner
./setup stop
./setup shell                # shell dans le conteneur
./setup logs
```

Le `Dockerfile` construit en deux étages (build `uv sync`, puis image finale
`python:3.14-alpine`) et lance
`makemigrations && migrate && collectstatic && runserver`.
`compose.yaml` monte `db.sqlite3` en volume et active `develop.watch` pour la
synchronisation à chaud.

### Comptes de démonstration

| Rôle | Utilisateur | Mot de passe |
|---|---|---|
| Admin | `demo.admin` | `Demo1234!` |
| Recruiter | `demo.recruteur` | `Demo1234!` |
| JobSeeker | `demo.candidat` | `Demo1234!` |

Régénération : `python manage.py seed_demo` (mot de passe réglable par
`DEMO_PASSWORD`).

### Tests

**586 tests** au total :

| App | Tests |
|---|---|
| `questionnaires` | 285 |
| `profiles` | 253 |
| `messaging` | 19 |
| `notifications` | 15 |
| `mainapp` | 14 |

```bash
python manage.py test --parallel 4                       # tout
python manage.py test profils.profiles --parallel 4
python manage.py test profils.questionnaires --parallel 4
```

Les trois tests qui portent le plus de sens :

- `test_results_are_immune_to_later_edits` — un résultat reste identique après
  réécriture complète du questionnaire ;
- `test_a_test_attempt_never_awards_a_real_badge` — l'étanchéité du mode TEST ;
- `test_a_late_request_never_overwrites_a_newer_answer` — l'anti-écrasement de
  l'autosave.

`profiles/tests/test_security.py` (36 tests) est une suite dédiée : accès à un
profil privé, modification du profil d'autrui, fuite de données par l'API ou par
une carte de résultat.

### CI

`.github/workflows/build.yml` — à chaque push sur `main` : `npm ci`,
`build:css`, `uv sync`, génération d'une clé secrète de build, migrations,
`seed_demo`, puis publication de l'application prête à l'emploi (base peuplée
comprise) en artefact de build.

---

## 12. Ce qui n'est pas là, et pourquoi

Une lecture honnête du code demande de savoir ce qui est **délibérément absent** :

| Sujet | État |
|---|---|
| **Modération `mainapp`** | Désactivée temporairement : `get_videos` et `get_video_filepaths` affichent toutes les vidéos quel que soit leur statut. La modération réelle vit dans `profiles`. |
| **Deux systèmes vidéo** | `mainapp.VideoLink` / `VideoFile` (historique) et `profiles.ProfileVideo` (moderne, modéré) coexistent. `messaging.rules` reconnaît les deux exprès. |
| **Feed vertical** | Retiré, remplacé par la grille paginée. `feed.py` conserve le chaînage recherche → vidéos, testé, mais **n'expose aucune route**. |
| **Matching candidat/offre** | `matching.py` prépare les deux moitiés, mais il n'existe pas encore de modèle d'offre. |
| **Badges** | Modèle, attribution et API en place ; **l'interface n'affiche rien** (c'était demandé ainsi). |
| **Expiration des tentatives** | Constatée à la lecture. `expire_stale_attempts()` existe mais n'est branché sur aucun cron. |
| **Validation des fichiers vidéo** | Pas de vérification des magic bytes : le `content_type` annoncé par le client est cru sur parole (`TODO` explicite dans `profiles/views.py`). |
| **Configuration de production** | `DEBUG = True`, `ALLOWED_HOSTS = []`, SQLite. C'est un projet d'école. |
| **Dérive `mainapp`** | `Role.user` est `ForeignKey` dans le code et `OneToOneField` en base, donc `makemigrations` (lancé par le Dockerfile) régénère une migration à chaque démarrage. Antérieur aux modules récents, laissé tel quel. |
