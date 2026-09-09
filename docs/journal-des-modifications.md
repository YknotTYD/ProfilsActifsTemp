# Journal des modifications - retour au cahier des charges v1.0

> Ce journal contient lui-même des occurrences des termes proscrits, puisqu'il
> décrit leur retrait. C'est assumé : un journal qui n'ose pas nommer ce qu'il
> supprime ne documente rien.

## Correspondance des modifications

| Code | Modification |
|---|---|
| **I‑1** | Aucun lien, même indicatif, entre l'engagement et les droits sociaux |
| **I‑2** | Suppression des compteurs d'engagement publics |
| **I‑3** | Retour à une grille de profils paginée, 20 par page, lecture sur clic |
| **I‑4** | « Permis de travailler » → badge de certification |
| **I‑5** | Questionnaire ramené à 20 questions, progression sauvegardée, non‑prérequis |
| **I‑6** | Nom de travail du Ministre retiré partout ; le service s'appelle Compétences+ |
| **I‑B** | Bandeau permanent dans l'espace candidat |

## Lundi 7 septembre 2026

| Heure | Modification |
|---|---|---|
| 13:37 | Page d'erreur 404 dédiée, aux couleurs du service (`templates/404.html`) | I‑B |
| 14:06 | Mention légale en pied de page ; pages d'erreur 400, 403 et 500 (`templates/400.html`, `403.html`, `500.html`, `partials/_footer.html`) | I‑B |
| 17:03 | Retrait des compteurs de « j'aime » du flux, de la fiche publique et des sérialiseurs ; la donnée reste en base, les sorties sont coupées (`profils/profiles/engagement.py`, `feed.py`, `serializers.py`, `templates/profiles/profile.html`) | I‑2 |
| 17:35 | Suppression du flux vertical plein écran ; grille de profils paginée à 20 par page, lecture vidéo à la demande sur clic (`profils/mainapp/views.py`, `constants.py`, `templates/candidates_grid.html`, `static/candidates_grid.js`) | I‑3 |
| 17:35 | Redirections permanentes (301) de `/feed/`, `/api/feed/` et `/api/videos/feed/` vers la grille, paramètres conservés — un lien ancien ne renvoie plus d'erreur (`profils/urls.py`) | I‑3 |
| 17:35 | Test de non‑régression : la page échoue si `autoplay`, `loop` ou `muted` réapparaissent au rendu (`profils/mainapp/tests.py`) | I‑3 |
| 17:37 | Bandeau permanent dans la barre de navigation, portant la phrase validée mot pour mot ; inclus par tous les gabarits de l'espace candidat, y compris connexion, inscription et pages d'erreur (`templates/partials/_navbar.html`) | I‑B |

## Mardi 8 septembre 2026 — matin

| Heure | Modification |
|---|---|---|
| 08:04 | Dispositif renommé « badge de certification » dans l'interface, les gabarits et la documentation ; nouvelles illustrations par rang (`profils/questionnaires/badges.py`, `serializers.py`, `templates/partials/_cert_shelf.html`, `static/badge/`) | I‑4 |
| 08:04 | Commande `normaliser_certification` : réécrit les appellations proscrites en base, compte passations et badges avant/après, échoue si ces compteurs bougent. Simulation par défaut, `--apply` pour écrire, rapport JSON (`profils/questionnaires/management/commands/normaliser_certification.py`) | I‑4 |

## Mardi 8 septembre 2026 — livraison de 12h00

| Modification | Modification |
|---|---|
| Retrait du champ `likes` du schéma `VideoStats` de la spécification OpenAPI. L'API ne le renvoyait plus ; la documentation le promettait encore (`swagger.yaml`) | I‑2 |
| Retrait de la référence à un réseau social tiers dans la documentation de l'app profils, remplacée par la description du dispositif réellement en place (`profils/profiles/README.md`) | I‑6 |
| Nom du paquet, description et URLs alignés sur Compétences+ ; suppression du suffixe de travail hérité de l'amorçage (`package.json`) | I‑6 |
| Accroche du dépôt réécrite : le service est un outil de valorisation des compétences, pas un réseau social ; mention explicite de la non‑utilisation des données pour des droits ou allocations (`README.md`) | I‑1, I‑6 |
| Branche de travail portant le nom d'un réseau social tiers renommée `feature/recruiter-profile-grid`. **Aucune branche n'est supprimée**, l'historique est conservé | I‑6 |
| Suppression d'un répertoire de commandes en double (`profils/mainapp/managment/`, faute de frappe), code mort contenant une ancienne version du jeu de données de démonstration avec les réactions. Reste dans l'historique git | I‑2, I‑6 |
| Plafond produit `CERTIFICATION_QUESTION_LIMIT = 20`, vérifié à la publication d'une version et nulle part ailleurs : un brouillon peut en porter plus pendant qu'on le taille, une version en ligne ne le peut pas (`profils/questionnaires/constants.py`, `versioning.py`) | I‑5 |
| `score_attempt` accepte un périmètre de clés stables : une passation peut être rejouée sur les seules questions encore en vigueur, sans qu'aucune réponse soit supprimée (`profils/questionnaires/scoring.py`) | I‑5 |
| Commande `retraiter_passations` : recalcule les passations antérieures à la réduction, réévalue les badges, rend les compteurs avant/après et un rapport JSON. Simulation par défaut, rejouable (`profils/questionnaires/management/commands/retraiter_passations.py`) | I‑5 |
| Mention de recalcul affichée sous le score et exposée par l'API : aucune note recalculée ne s'affiche sans dire sur quel périmètre (`profils/questionnaires/serializers.py`, `templates/questionnaires/results.html`, `static/questionnaires.css`) | I‑5 |
| Note écrite du choix des 20 questions, du critère de sélection et de la décision sur les passations existantes (`docs/certification-20-questions.md`) | I‑5 |
| 13 tests couvrant le plafond de publication et le retraitement, dont la perte et le gain de badge (`profils/questionnaires/tests/test_rescore.py`) | I‑5 |
| Test de couverture du moteur réparti sur plusieurs questionnaires, le moteur connaissant plus de types de questions que le plafond n'autorise de questions publiées (`profils/questionnaires/tests/test_runner_contract.py`) | I‑5 |

## Vérifications à la livraison

**Recherche lexicale sur l'ensemble du dépôt** — sortie brute jointe
(`docs/recherche-lexicale.txt`). Treize occurrences subsistent, chacune justifiée.
Aucune n'est dans l'interface, les CGU, un nom de variable, une migration, un
jeu de données ou un fichier de traduction :

| Emplacement | Occurrences | Raison |
|---|---|---|
| `profils/questionnaires/management/commands/normaliser_certification.py` | 2 | Motifs de recherche de la commande qui interdit ces formulations |
| `docs/architecture.md` | 1 | Documentation de cette même commande |
| `docs/journal-des-modifications.md` | 5 | Ce journal, qui nomme les modifications auxquelles il répond et les occurrences qu'il assume |
| `docs/certification-20-questions.md` | 2 | La note qui écrit que le badge n'ouvre aucun droit, et le critère qui exclut toute référence à un parcours d'indemnisation |
| `README.md` | 1 | L'accroche qui énonce la non‑utilisation des données pour des droits ou allocations |
| `templates/partials/_navbar.html` | 1 | Le bandeau lui‑même, texte validé |
| `Compétences+Diagram.png` | 1 | Faux positif : octets binaires d'une image |

Les neuf occurrences documentaires disent toutes la même chose — que ce lien
n'existe pas. C'est le seul emploi restant de ce vocabulaire.

Le fichier de sortie s'exclut lui-même de la recherche : il porte les motifs en
en-tête et se trouverait à chaque passage. L'exclusion est écrite dans son
en-tête, avec la commande exacte.

**Suite de tests** — 599 tests, aucun échec.

**Trois parcours rejoués de bout en bout**, sur base propre, après retraits :

| Parcours | Résultat |
|---|---|
| Inscription d'un candidat | compte créé, session ouverte |
| Dépôt d'une vidéo | fichier accepté, profil à jour |
| Consultation d'un profil par un recruteur | page et API, sur un candidat sans certification |

**Bandeau** — vérifié écran par écran : accueil, connexion, inscription,
recherche de profils, fiche candidat, espace certification, CGU, et les pages
d'erreur 400 / 403 / 404 / 500.

**Retraitement des passations** — sur la base de développement courante :
20 passations, 18 réussies, 20 résultats, 26 badges, **0 passation à
recalculer** ; sur un jeu de démonstration régénéré : 19, 17, 19, 25, **0
également** (aucune
épreuve ne dépasse le plafond).


