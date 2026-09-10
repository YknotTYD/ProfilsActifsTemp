
# Compétences+

Outil de valorisation des compétences mettant en relation candidats et
recruteurs — piscine Survivor de Tech 3.

Compétences+ n'est pas un réseau social : aucune donnée du service n'est
utilisée pour déterminer des droits ou le montant d'allocations.


## Installation

```bash
  ./setup install
```

## Deploiement

```bash
  ./setup run [port]
```

Création d'un utilisateur administrateur
```bash
  ./setup shell
  python manage.py createsuperuser
```

Logs du site
```bash
  ./setup logs
```

## Comptes de demonstration

Chaque push sur `main` declenche le workflow [`Build`](.github/workflows/build.yml) :
il installe les dependances, compile le CSS, applique les migrations, cree les
comptes de demonstration ci-dessous puis publie l'application prete a l'emploi
(y compris sa base `db.sqlite3` deja peuplee) en artefact de build sur l'onglet
Actions.

| Role      | Utilisateur     | Mot de passe |
|-----------|-----------------|--------------|
| Admin     | `demo.admin`     | `Demo1234!`  |
| Recruiter | `demo.recruteur` | `Demo1234!`  |
| JobSeeker | `demo.candidat`  | `Demo1234!`  |

Pour les regenerer localement : `python manage.py seed_demo` (le mot de passe
peut etre change via la variable d'environnement `DEMO_PASSWORD`).


## Jeu de donnees pour les tests de charge

```bash
  python manage.py seed_volume                        # 500 profils, 300 avec video
  python manage.py seed_volume --profiles 50 --with-video 30
  python manage.py seed_volume --keep                 # ajoute sans effacer le lot
```

La commande est relancable sur une base vide : elle cree elle-meme le compte de
moderation dont elle a besoin. Elle n'efface que son propre lot, dont tous les
comptes portent le prefixe `charge-`.

Les videos passent par l'interface de soumission et parcourent le cycle de
moderation complet (soumission, validation, publication), et non par une
insertion directe en base. Le tirage est reproductible via `--seed`.

Comptez environ une minute trente pour 500 profils et 300 videos.

Verifier ensuite que la pagination du catalogue reste deterministe :

```bash
  python manage.py prove_pagination
```

La commande parcourt le catalogue deux fois, ecrit les deux releves
d'identifiants et leur comparaison dans `pagination-proof/`, et sort en code
non nul si l'ordre a bouge.

## Tech Stack

**Front** : gabarits Django, Tailwind CSS 4 compilé en CLI, JavaScript vanilla
(sans framework ni bundler)

**Back** : Django, API JSON maison (sans framework d'API)

**Base de données** : SQLite


## Authors

- [Eren Turkoglu](https://github.com/erenworld)
- [Ethan Bertin-Prévot](https://github.com/YknotTYD)
- [Julian Hemmer](https://github.com/julian-hemmer)
- [Pierre Maciejewski](https://github.com/pierre54200)
