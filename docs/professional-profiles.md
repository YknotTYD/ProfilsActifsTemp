# Système de profils professionnels

Vue d'ensemble de la nouvelle section "profils professionnels" du site : ce
qu'elle fait, comment elle est construite, et comment la prendre en main.
Documentation technique complète : [profils/profiles/README.md](../profils/profiles/README.md).

---

## 1. Ce que ça fait

Un utilisateur peut se construire un **profil professionnel complet**
(photo, titre, présentation, compétences avec niveau, expériences,
formations, certifications, langues, projets), régler **qui a le droit de
voir quoi**, et être trouvé par les autres via une **recherche de candidats**
qui combine compétences, niveau, expérience, localisation, disponibilité et
type de contrat.

Une section vidéos existe déjà dans l'interface et dans le modèle de
données, prête à recevoir de vraies vidéos plus tard, mais **aucun upload
n'est implémenté dans cette version**.

## 2. Où c'est, dans le site

| URL | Ce que c'est |
|---|---|
| `/profile/<username>/` | Le profil public de quelqu'un |
| `/profile/` | Redirige vers son propre profil (le crée s'il n'existe pas encore) |
| `/profiles/` | La page de recherche de profils |
| `/profiles/edit/` | L'édition de son propre profil, par onglets |

Le module vit entièrement dans `profils/profiles/` (backend Django) et dans
`static/profiles*.{css,js}` + `templates/profiles/` (frontend). Il ne touche
ni `mainapp` ni `questionnaires` : les trois apps sont indépendantes,
seulement reliées par le compte utilisateur commun (`auth.User`) et par le
rôle recruteur/candidat de `mainapp.Role`.

## 3. Le modèle de données, en une image

```
User
 └── ProfessionalProfile              (le profil : titre, résumé, localisation, disponibilité…)
      ├── ProfileVisibility            (visibilité de chaque section, indépendamment)
      ├── ProfileSearchSettings        (apparaît ou non dans les recherches)
      ├── ProfileContractType          (CDI, freelance, stage…)
      ├── ProfileLink                  (GitHub, portfolio…)
      ├── UserSkill        ──> Skill   (compétence + niveau + années d'expérience)
      │                        └── SkillAlias   (autres orthographes du même mot)
      ├── WorkExperience    ── skills utilisées
      ├── Education         ── skills associées
      ├── Certification     ── skills associées
      ├── UserLanguage      ──> Language
      ├── Project           ── skills utilisées
      └── ProfileVideo      ── skills présentées   (structure prête, pas d'upload)
```

**Point clé : `Skill` est un référentiel unique.** Que quelqu'un tape
`Java`, `java` ou `JAVA`, c'est toujours la même ligne en base — la
comparaison se fait sur une clé normalisée (`skills.py`), pas sur le texte
brut. C'est ce qui rend la recherche par compétence possible : sans ça,
chercher "Java" raterait la moitié des profils qui l'ont orthographié
autrement.

## 4. Visibilité : trois réglages qui ne se marchent pas dessus

C'est le point le plus facile à mal comprendre, donc à bien avoir en tête :

1. **`profile.visibility`** — `PUBLIC` / `REGISTERED_USERS` / `PRIVATE`.
   Décide qui a le droit d'ouvrir la page du profil.
2. **`ProfileVisibility`** — une valeur par section (compétences,
   expériences, formations…). Décide ce qu'on voit *une fois la page
   ouverte*. Une section ne peut jamais être plus ouverte que le profil
   lui-même — la régler sur `PUBLIC` sur un profil `PRIVATE` ne la sort pas
   du profil privé.
3. **`ProfileSearchSettings.searchable`** — complètement indépendant des deux
   premiers. Un profil peut être public et rester invisible dans les
   résultats de recherche. Ce réglage n'a aucune exception, pas même pour un
   administrateur.

Toutes ces règles sont appliquées **côté serveur uniquement**
(`visibility.py`, `search.py`). Une section masquée n'est jamais envoyée au
navigateur avec un simple drapeau "à ne pas afficher" — elle est absente de
la réponse.

## 5. La recherche

`/api/profiles/search/` accepte des critères combinables :

```
GET /api/profiles/search/?skill=java&skill=docker&mode=AND
    &min_level=INTERMEDIATE&contract=CDI&available=1&sort=relevance
```

- **Compétences** : `AND` (toutes requises) ou `OR` (au moins une), avec
  niveau minimum et années d'expérience minimum.
- **Filtres** : domaine, ville/pays, disponibilité, type de contrat,
  télétravail/hybride/présentiel, diplôme minimum, langue.
- **Classement** : chaque profil reçoit un score de pertinence (plus de
  compétences couvertes, meilleur niveau, plus d'expérience pertinente,
  disponibilité, domaine qui correspond…), calculé et trié **en base de
  données** — jamais en récupérant tous les profils pour filtrer ensuite en
  Python. Les poids sont dans `constants.RANKING_WEIGHTS`, ajustables sans
  toucher au moteur.
- **Pagination** réelle, avec une limite de taille de page.

## 6. Sécurité : ce qui est vérifié, et où

Le frontend n'est jamais considéré comme fiable. Chaque écriture passe par
`permissions.assert_can_edit` (on ne modifie que son propre profil) et
`permissions.assert_owns_child` (un identifiant d'expérience, de formation,
etc. fourni par le client est toujours revérifié comme appartenant au bon
profil avant modification). Un profil privé répond `404`, pas `403` — pour
ne pas confirmer qu'un compte existe à quelqu'un qui n'a pas le droit de le
voir.

## 7. Ce qui est préparé pour plus tard, sans être construit maintenant

- **Vidéos** (`ProfileVideo`, `ProfileVideoSkill`) : le modèle, les statuts
  (`DRAFT` → `PUBLISHED` → …), la relation aux compétences et les règles de
  visibilité existent et sont testés. Pas d'upload ni de lecture réelle.
- **Feed vertical** (`feed.py`) : le chaînage
  *recherche → profils trouvés → leurs vidéos* fonctionne déjà en interne
  (`video_candidates`, `videos_for_skills`), mais **aucune route de feed
  n'est exposée** — pas de faux carrousel.
- **Matching candidat/offre** (`matching.py`) : traduit un profil en
  caractéristiques comparables, et une offre (sous forme de dictionnaire, il
  n'existe pas encore de modèle "Offre") en requête de recherche. Le
  rapprochement complet candidat ↔ offre n'est pas implémenté.

## 8. Tests

193 tests (`profils/profiles/tests/`), qui couvrent la canonicalisation des
compétences et l'absence de doublons, la création/modification/suppression
de chaque section, les trois niveaux de visibilité, la recherche (AND/OR,
filtres, classement, pagination, exclusion des profils non recherchables),
et une suite de sécurité dédiée (accès à un profil privé, modification du
profil d'un autre utilisateur, fuite de données par l'API ou par une carte
de recherche).

```bash
python manage.py test profils.profiles --parallel 4
```

Les 285 tests déjà présents (questionnaires, mainapp) continuent de passer
sans modification.
