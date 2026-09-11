# Déploiement et exploitation

Ce document complète la section rapide de
[`docs/architecture.md#11-lancer-tester-déployer`](architecture.md) : il
détaille la configuration, l'état de préparation production et les gestes
d'exploitation courants.

## Variables d'environnement

| Variable | Obligatoire | Rôle | Défaut |
|---|---|---|---|
| `DJANGO_SECRET_KEY` | oui | signature des sessions et jetons CSRF | — |
| `PORT` | non | port publié par `compose.yaml` | `8080` |
| `DEMO_PASSWORD` | non | mot de passe des comptes créés par `seed_demo` | `Demo1234!` |

`.env` n'est jamais versionné (`.gitignore`). `.env.example` liste le même
tableau à titre de gabarit. Une clé par environnement : celle de production ne
se partage pas, et la changer invalide toutes les sessions ouvertes et les
liens signés en cours.

## Lancer le service

Voir le [README](../README.md#installation) pour les commandes `./setup`.
`compose.yaml` monte `db.sqlite3` en volume (persistant hors du conteneur) et
active `develop.watch` : une modification du code resynchronise le conteneur
sans rebuild, sauf changement de `pyproject.toml` ou `uv.lock` qui déclenche un
rebuild complet.

Sonde de santé : `GET /health/` ouvre un curseur sur la base et répond `503`
si elle est indisponible — c'est le point à brancher sur un orchestrateur ou
un load balancer, pas la racine `/`.

## Build CI et artefact

`.github/workflows/build.yml` tourne à chaque push sur `main` (pas sur les
branches de PR) : installe les dépendances front et Python, compile Tailwind,
génère une clé secrète **jetable** (valable uniquement pour ce run), applique
les migrations, peuple les comptes de démonstration, puis publie
l'application prête à l'emploi — base `db.sqlite3` peuplée comprise — en
artefact de build (rétention 30 jours), consultable depuis l'onglet Actions.
Cet artefact n'est **pas** un déploiement : c'est un instantané téléchargeable
pour vérification ou démonstration.

## Sauvegarde et restauration

L'état persistant tient en deux emplacements, tous deux hors du conteneur via
volume :

- `db.sqlite3` — toutes les données applicatives ;
- `media/videos/` — les fichiers vidéo téléversés (les vidéos par lien externe
  n'y occupent aucune place).

Sauvegarder revient à copier ces deux chemins service arrêté (SQLite n'aime
pas être copié pendant une écriture concurrente). Il n'existe aujourd'hui
aucun script de sauvegarde automatisée dans le dépôt.

## État de préparation production

Le projet est un projet d'école et **n'est pas durci pour la production** en
l'état (voir `docs/architecture.md#12-ce-qui-nest-pas-là-et-pourquoi` pour le
détail). À reprendre avant toute mise en ligne réelle :

| Point | État actuel |
|---|---|
| `DEBUG` | à `True` dans `profils/settings.py` — expose la stack trace complète sur erreur |
| `ALLOWED_HOSTS` | vide — à renseigner avec le(s) nom(s) de domaine réel(s) |
| Base de données | SQLite — un seul fichier, pas de réplication, pas de gestion de connexions concurrentes à grande échelle |
| HTTPS | non imposé par la configuration Django (`SECURE_SSL_REDIRECT`, cookies `Secure` non réglés) |
| Validation des fichiers vidéo | le `content_type` annoncé par le client est cru sur parole, pas de vérification des magic bytes (`TODO` explicite dans `profils/profiles/views.py`) |
| Expiration des tentatives de questionnaire | `expire_stale_attempts()` existe mais n'est branché sur aucune tâche planifiée |
| Sauvegarde | aucune automatisation (voir ci-dessus) |

Ce tableau est à tenir à jour au fil des correctifs — le rayer au fur et à
mesure évite de re-découvrir les mêmes lacunes à chaque revue de sécurité.
