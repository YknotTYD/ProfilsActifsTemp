# Module profiles

Profils professionnels : présentation, compétences structurées, expériences,
formations, certifications, langues, projets, et recherche de candidats.

App Django autonome. `mainapp` n'est pas touché ; le pont vers `Role` et le
système de permissions de `questionnaires` sont réutilisés plutôt que
recopiés.

---

## Démarrer

```bash
docker compose watch          # comme d'habitude
```

ou en local :

```bash
python manage.py migrate
python manage.py runserver
python manage.py test profils.profiles --parallel 4    # 193 tests
```

La migration `0002_seed_languages` charge un référentiel de ~30 langues au
premier `migrate` : rien à faire de plus pour que le sélecteur de langues soit
utilisable.

---

## Les pages

| URL | Qui | Quoi |
|---|---|---|
| `/profile/<username>/` | selon la visibilité | le profil public |
| `/profile/` | connecté | redirige vers son propre profil (le crée si besoin) |
| `/profiles/` | tout le monde | recherche de profils |
| `/profiles/edit/` | connecté | édition de son propre profil, par onglets |

---

## Ce qui est en place

- **Profil** : informations générales, localisation, domaine, disponibilité,
  type de contrat, télétravail/hybride/présentiel, mobilité, liens.
- **Compétences** (`Skill` / `UserSkill`) : référentiel canonique
  (`Java`/`java`/`JAVA` = une seule ligne, voir `skills.py`), niveau
  (`BEGINNER`→`EXPERT`), années d'expérience, ordre d'affichage.
- **Expériences, formations, certifications, projets** : chacun avec ses
  propres compétences associées, tirées du même référentiel.
- **Langues** : niveau CECRL.
- **Visibilité** (`visibility.py`) : `PUBLIC` / `REGISTERED_USERS` / `PRIVATE`
  sur le profil *et* indépendamment sur chaque section, plus `searchable`
  comme réglage à part entière — un profil peut être public et absent des
  résultats de recherche. Toutes les règles s'appliquent côté serveur.
- **Recherche** (`search.py`, `ranking.py`) : filtres combinables en base de
  données, `AND`/`OR` sur les compétences, score de pertinence annoté en SQL,
  pagination. Rien n'est chargé en mémoire pour être filtré ensuite.
- **Vidéos** (`ProfileVideo` / `ProfileVideoSkill`) : structure complète,
  section vide fonctionnelle. **Pas d'upload dans cette version.**
- **Préparation du feed** (`feed.py`) et **du matching candidat/offre**
  (`matching.py`) : le chaînage recherche → profils → vidéos existe et est
  testé, sans qu'aucun feed ni matching ne soit exposé.

## Ce qui ne l'est pas (volontairement)

- Upload et lecture vidéo réels — le projet n'a aucun stockage de fichiers
  (comme `mainapp.Video`, les URLs sont stockées telles quelles).
- Feed vertical façon TikTok.
- Matching candidat/offre complet (il n'existe pas encore de modèle d'offre).

---

## Se donner un profil de test

```python
from profils.profiles import constants as c, services
profile = services.get_profile(mon_user)
services.update_profile(profile, {"visibility": c.VISIBILITY_PUBLIC})
services.add_skill(profile, {"name": "Java", "level": c.LEVEL_EXPERT, "years_experience": 5})
```
