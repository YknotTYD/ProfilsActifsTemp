# Classement et filtrage du catalogue

Note d'une page. Ce document décrit l'ordre dans lequel les profils sont
présentés au recruteur, les critères qui entrent dans ce classement, et ceux
qui n'y entrent pas.

Les garanties de pagination et leurs limites font l'objet d'une section
séparée, dans `professional-profiles.md`, §5.

## Ordre par défaut

Date de dernière mise à jour décroissante, puis identifiant du profil en clé de
départage. Deux colonnes dans le `ORDER BY`, jamais une seule : `updated_at`
seul laisse l'ordre des ex æquo au bon vouloir du moteur de base de données, et
deux appels successifs à la même page peuvent alors renvoyer des profils
différents, en oublier certains et en répéter d'autres.

Le code : `ProfessionalProfile.Meta.ordering`, et `search._SORTS` pour les
tris explicites.

## Les quatre tris proposés

| Tri | Colonnes, dans l'ordre |
|---|---|
| Pertinence (défaut) | score, expérience totale, date de mise à jour, identifiant |
| Expérience | expérience totale, score, identifiant |
| Mis à jour récemment | date de mise à jour, identifiant |
| Nom | nom, prénom, nom d'utilisateur, identifiant |

Chacun se termine par l'identifiant du profil. Aucun de ces tris ne peut donc
rendre deux résultats différents pour une même page sur un jeu de données figé.

## Aucun critère de popularité

Le classement ne comporte aucun critère de popularité, ni direct, ni dérivé, ni
indirect. Les compteurs de vues et de réactions existent en base, sur le modèle
vidéo, mais ils n'entrent dans aucune expression de tri et dans aucune
composante du score.

La vérification tient en une lecture : les composantes du score sont énumérées
au même endroit, dans `ranking.relevance_annotations`. Il n'y a pas d'autre
chemin par lequel un profil peut remonter dans la liste.

## Le score de pertinence

Le score est une expression SQL annotée sur la requête. Le tri et la pagination
se font donc en base, sur l'ensemble des profils correspondants, et non sur une
page déjà tronquée. C'est la différence entre les vingt premiers résultats
classés et vingt résultats au hasard, classés entre eux.

| Composante | Poids | Ce qu'elle mesure |
|---|---|---|
| Compétences correspondantes | 100 | Nombre de compétences demandées que le profil possède |
| Niveau de ces compétences | 10 | Somme des niveaux déclarés sur ces compétences |
| Années sur ces compétences | 4 | Somme des années, plafonnée à 10 |
| Expérience totale | 2 | Années d'expérience, plafonnée à 20 |
| Disponibilité | 25 | En recherche active ou ouvert aux opportunités |
| Domaine | 30 | Le domaine professionnel correspond à la recherche |
| Langues | 15 | Nombre de langues demandées au niveau requis |
| Présence d'une vidéo | 5 | Le profil a une vidéo de présentation publiée |

Les poids vivent dans `constants.RANKING_WEIGHTS`, les plafonds dans
`constants.RANKING_CAPS`. Ils s'ajustent sans toucher au moteur.

Les deux plafonds évitent qu'un seul critère écrase tous les autres : sans eux,
un profil affichant trente ans d'expérience passerait devant un profil qui
correspond réellement à la recherche.

`ranking.score_breakdown` renvoie le détail du score d'un profil, composante par
composante. Un classement que personne ne peut expliquer ne peut pas être
amélioré.

## Les filtres disponibles

- **Compétences** : plusieurs compétences, combinées en ET, toutes requises, ou
  en OU, au moins une. Avec niveau minimum et nombre d'années minimum.
- **Domaine professionnel.**
- **Localisation** : pays, ville.
- **Disponibilité** : statut précis, ou simplement les profils disponibles.
- **Type de contrat** : CDI, CDD, stage, alternance, freelance, temps
  partiel, intérim, bénévolat.
- **Mode de travail** : télétravail, hybride, présentiel.
- **Langues**, avec niveau minimum.
- **Formation** : diplôme minimum, domaine d'études.
- **Expérience** : nombre d'années minimum.
- **Texte libre** sur le nom, le titre et le résumé.

Le code : `search.apply_filters`. Une compétence inconnue du référentiel n'est
pas une erreur, elle est renvoyée à part pour que l'interface puisse le dire
plutôt que d'afficher zéro résultat sans explication.

## Ce qui n'est pas filtrable aujourd'hui

Le **statut de certification** n'est ni un filtre ni un tri. Les certifications
déclarées par le candidat et les badges obtenus par questionnaire existent tous
deux en base, mais ne sont pas exposés au moteur de recherche. C'est un manque
identifié, pas un choix.

## Deux garde-fous, avant tout classement

Ils s'appliquent dans `search.base_queryset`, et nulle part ailleurs, pour
qu'aucun chemin de recherche ne puisse les oublier.

Un profil que son propriétaire a rendu non recherchable n'apparaît jamais, pour
personne, administrateur compris : ce drapeau est un choix de l'utilisateur, pas
une permission. Et la visibilité de chaque profil est comparée à l'audience du
visiteur avant que quoi que ce soit ne soit classé.
