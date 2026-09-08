# Certification : les 20 questions

> Cahier des charges v1.0 du 31 août 2026, point 5.
> Le badge de certification **valorise, il n'autorise pas**. Il n'ouvre aucun
> droit, et aucune donnée du service n'entre dans la détermination de droits ou
> d'allocations.

## Le critère de sélection

L'épreuve tient en **20 questions**, réparties en 10 « métier » (connaissances
vérifiables du domaine déclaré), 6 « organisation et communication » (situations
de travail concrètes) et 4 mises en situation à réponse courte. Quatre filtres
décident de l'entrée d'une question : elle doit être **corrigeable
automatiquement** et sans jugement de valeur ; ne référer à **aucun statut
administratif**, situation personnelle ou parcours d'indemnisation ; être
**discriminante** sur les passations déjà enregistrées (taux de réussite entre
20 % et 80 % — une question que tout le monde réussit ou rate n'apprend rien) ;
et se traiter en **moins de 90 secondes**. L'épreuve complète tient ainsi sous
15 minutes, qui est le vrai plafond d'abandon.

Ce choix est celui de l'équipe produit. Il est révisable, mais il est écrit.

## Ce que le plafond signifie dans le code

`questionnaires.constants.CERTIFICATION_QUESTION_LIMIT = 20`.

Le plafond est vérifié **à la publication** d'une version, dans
`versioning.publish_version`, et nulle part ailleurs. Un brouillon peut porter
davantage de questions pendant qu'on le taille ; une version en ligne ne le
peut pas. Une tentative de publier 21 questions échoue avec un message qui dit
le compte.

Ce choix d'emplacement est délibéré : le contrôle se trouve sur le seul chemin
par lequel une épreuve devient réelle pour un candidat. Il n'y a pas de seconde
porte.

## La certification n'est pas un prérequis d'accès

Un recruteur consulte la fiche d'un candidat qui n'a jamais ouvert l'épreuve,
sans blocage ni écran intermédiaire. La certification enrichit un profil, elle
n'en conditionne pas la consultation.

## Passations et badges déjà enregistrés

Réduire l'épreuve laisse en base des réponses portant sur des questions
retirées, et des badges attribués sur un score qui les incluait. Trois
traitements étaient défendables ; voici celui qui est retenu et pourquoi les
deux autres ne le sont pas.

| Option | Retenue | Pourquoi |
|---|---|---|
| **Recalculer** sur les 20 questions restantes | **oui** | La personne garde le bénéfice de ce qu'elle a réellement produit, et ne voit jamais une note calculée sur des questions disparues. |
| Invalider les passations | non | Efface un travail réel et renvoie tout le monde à zéro sans faute de sa part. |
| Conserver en l'état, en marquant | non | Laisse affichée la note fantôme. C'est exactement ce que le cahier des charges exclut. |

### Ce que le recalcul fait, et ne fait pas

- **Ne supprime rien.** Les réponses aux questions retirées restent en base.
  Elles cessent de compter dans le score, et figurent dans le détail du
  résultat, marquées `retired_question`.
- **Réévalue les badges** sur les scores recalculés : un badge dont le critère
  n'est plus satisfait est retiré, un badge nouvellement mérité est attribué.
  Un recalcul peut faire gagner une certification autant qu'en faire perdre une
  — le score sur 20 questions peut franchir un seuil que 100 questions
  diluaient.
- **Ne touche jamais aux badges attribués manuellement** : ils ne dépendent
  d'aucun score.
- **Laisse tranquille** un questionnaire sans version publiée : sans version de
  référence, il n'y a pas de périmètre sur lequel recalculer.

### La mention affichée

Une note recalculée ne s'affiche jamais sans le dire. La page de résultats
porte, sous le score :

> Note recalculée le JJ/MM/AAAA sur les 20 questions de l'épreuve actuelle.
> N questions posées lors de votre passage ne font plus partie de l'épreuve et
> ne sont plus comptabilisées.

La trace complète (date, version de référence, score avant, score après) vit
dans `QuestionnaireAttempt.metadata["retraitement"]` et dans
`QuestionnaireResult.details["retraitement"]`, et est exposée par l'API sous
`retraitement`.

## Le script

```bash
python manage.py retraiter_passations                     # simulation
python manage.py retraiter_passations --apply             # écriture
python manage.py retraiter_passations --questionnaire 6   # une cible
python manage.py retraiter_passations --json rapport.json # rapport machine
```

Simulation par défaut : sans `--apply`, la transaction est annulée et la base
n'est pas touchée. **Rejouable** : un second passage ne trouve plus rien à
recalculer et affiche `Passations recalculees : 0`.

La commande rend les compteurs **avant** et **après** — passations, passations
réussies, résultats, badges — puis le détail : passations recalculées, dont
réussite acquise et réussite perdue, badges retirés, badges attribués. Chaque
recalcul et chaque retrait de badge est écrit au journal d'audit
(`RESCORE`, `BADGE_REVOKE`).

### État de la base de démonstration

Au mardi 8 septembre 2026, sur la base de développement courante : **20 passations, 18
réussies, 20 résultats, 26 badges**, et **0 passation à recalculer**. Les deux
épreuves seedées portent 9 et 8 questions ; aucune ne dépasse le plafond.
L'épreuve de 100 questions figurait dans le document annoté du 1er septembre,
elle n'a jamais existé dans nos données. Le mécanisme est en place et couvert
par des tests (`profils/questionnaires/tests/test_rescore.py`) ; il traitera
toute réduction future sans intervention manuelle.
