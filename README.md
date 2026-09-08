
# ProfilsActifs

Outil de valorisation des compétences mettant en relation candidats et
recruteurs — piscine Survivor de Tech 3.

ProfilsActifs n'est pas un réseau social : aucune donnée du service n'est
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


## Tech Stack

**Front**: React

**Back**: Django

**Database**: Sqlite


## Authors

- [Eren Turkoglu](https://github.com/erenworld)
- [Ethan Bertin-Prévot](https://github.com/YknotTYD)
- [Julian Hemmer](https://github.com/julian-hemmer)
- [Pierre Maciejewski](https://github.com/pierre54200)
