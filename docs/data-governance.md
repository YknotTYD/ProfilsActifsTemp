# Données personnelles et accessibilité — état actuel

Ce document décrit **ce qui existe dans le code aujourd'hui** en matière de
données personnelles et d'accessibilité. Ce n'est ni un registre de
traitement, ni une déclaration de conformité au sens juridique : ces pièces
relèvent d'un cadrage du service juridique, non encore rendu (voir la section
*Écarts connus* ci-dessous). Ce document sert de base factuelle pour cette
discussion, pas de substitut.

## Droit de retrait (art. 21 RGPD)

Un candidat peut retirer son profil du catalogue via
`POST /api/profiles/me/withdrawal/` (`{action}`), réversible.

Effet du retrait :

- `visibility.can_view_profile` traite un profil retiré exactement comme un
  profil privé ou inexistant : réponse `404` neutre pour tout le monde sauf le
  propriétaire, y compris pour un recruteur l'ayant déjà consulté. La page ne
  révèle jamais que le compte existe (Open Graph compris).
- Le profil sort du fil recruteur (`mainapp.views.get_videos`,
  `get_video_filepaths`).
- Une conversation déjà ouverte avant le retrait n'est pas fermée — c'est le
  seul lien qui subsiste côté recruteur ; le produit n'a ni favoris ni
  historique de consultation côté recruteur qui permettraient de retrouver le
  profil autrement.

## Journal de consultation (art. 15 RGPD)

Chaque ouverture d'une fiche profil par un compte recruteur enregistre une
`ProfileConsultation` (profil concerné, organisation du recruteur, horodatage
— rien d'autre). Jamais enregistrée pour une consultation anonyme, jamais pour
le propriétaire lui-même. Déduplication : une même organisation n'ajoute pas
de ligne si elle a déjà consulté le profil dans les 30 dernières minutes.

Le propriétaire du profil consulte son propre journal sur
`/profiles/me/consultations/`, et reçoit une notification
`PROFILE_CONSULTED` à chaque nouvelle consultation (« Votre profil a été
consulté par `<organisation>` »).

## Accessibilité (RGAA 4.1)

Une déclaration d'accessibilité est publiée sur `/accessibilite/` et liée
depuis le pied de page. Elle documente honnêtement un état **« non
conforme »** : la passe du 10 septembre 2026 a ajouté lien d'évitement,
`<main id="main-content">`, `:focus-visible` visible au clavier, contrastes
≥ 4.5:1, navigation clavier des menus, pause pour les témoignages animés,
labels de formulaire correctement associés, landmarks nommés et plomberie
`<track>` pour les vidéos — mais sans audit RGAA formel, sans
sous-titres/transcriptions réels, sans test avec lecteur d'écran, et sans
rôles ARIA sur les composants à onglets. Cette liste d'écarts est celle
publiée dans la déclaration elle-même ; la mettre à jour ici sans la mettre à
jour sur `/accessibilite/` la rendrait mensongère.

## Ce qui n'existe pas encore

Constaté à la lecture du code, pas de jugement sur ce qui devrait exister :

- aucun enregistrement de **consentement** (vidéo ou autre) ;
- la suppression d'une vidéo est **logique** (statut `VIDEO_DELETED`), les
  octets restent en base/`media/` ;
- les vidéos par lien externe (YouTube/Vimeo) ne passent par aucune
  abstraction de stockage — seules les vidéos par fichier sont hébergées
  directement ;
- l'âge minimum (18 ans) est contrôlé à l'inscription, mais
  `Role.birth_date` reste `nullable` en base ;
- pas de journal de connexion dédié (distinct du journal de consultation
  ci-dessus, qui ne couvre que la consultation d'un profil par un recruteur).

## Écarts connus, en attente de cadrage

Le service juridique a demandé (courrier du 4 septembre 2026) un registre de
traitement, une déclaration d'accessibilité, un projet de CGU et une note sur
les critères de filtrage. **Le développement de conformité est actuellement
en pause** : l'équipe a redemandé un cadrage précis plutôt que d'avancer sur
des interprétations, sur les points suivants notamment — base légale et durée
de conservation des données, ouverture ou non aux mineurs 16-18 ans,
niveau RGAA cible (AA sur 3 écrans a été demandé). Ne pas relancer de
développement sur ces points avant que ce cadrage écrit revienne.

Une revue de sécurité distincte (Direction Numérique, 4 septembre 2026) a par
ailleurs demandé une abstraction du stockage vidéo (`store`/`status`/
`playbackUrl`/`delete`, identifiant opaque en base) et le passage du
questionnaire de certification par un fichier JSON versionné avec schéma
explicite. Ces deux chantiers ne sont pas reflétés dans ce document tant
qu'ils ne sont pas livrés en code.
