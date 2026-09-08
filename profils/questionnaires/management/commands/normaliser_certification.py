"""Normalisation du vocabulaire du dispositif de certification.

Le dispositif s'appelle un *badge de certification*. Il valorise un parcours
evalue : il n'ouvre aucun droit et n'autorise personne a exercer quoi que ce
soit. Les appellations du type << permis de travailler >> et toute formulation
laissant croire a une autorisation sont donc proscrites.

Cette commande fait deux choses, et rien d'autre :

  1. elle compte les passations et les badges AVANT le traitement ;
  2. elle reecrit les libelles fautifs, puis recompte APRES.

Elle ne cree, ne supprime et ne re-attribue jamais ni une passation ni un
badge : les compteurs avant/apres doivent etre identiques, et la commande
echoue bruyamment si ce n'est pas le cas. Ce qui change, ce sont des mots.

Rejouable : un second passage ne trouve plus aucune occurrence et ne modifie
rien. Le mode par defaut est une simulation ; il faut `--apply` pour ecrire.

Usage :
    python manage.py normaliser_certification                  # simulation
    python manage.py normaliser_certification --apply          # ecriture
    python manage.py normaliser_certification --json rap.json  # rapport machine
    docker compose exec web python manage.py normaliser_certification --apply
"""

import json
import re

from django.contrib.auth.models  import User
from django.core.management.base import BaseCommand, CommandError
from django.db                   import transaction

from profils.questionnaires import constants as c
from profils.questionnaires.models import (
    Badge, Questionnaire, QuestionnaireAttempt, QuestionnaireVersion, UserBadge,
)

# --------------------------------------------------------------------------
# Vocabulaire
# --------------------------------------------------------------------------
#
# Deux familles de fautes, deux corrections differentes :
#   APPELLATIONS : le dispositif est mal nomme          -> on le renomme
#   PORTEE       : le texte promet un droit ou un permis -> on retablit le sens
#
# Chaque regle porte un code : c'est lui qui figure dans le rapport, colonne
# << motif >>, et qui permet d'expliquer chaque ligne une par une.

APPELLATIONS = (
    ("APP-PERMIS-TRAVAILLER", re.compile(r"permis\s+de\s+travailler",            re.I), "badge de certification"),
    ("APP-PERMIS-TRAVAIL",    re.compile(r"permis\s+de\s+travail\b",             re.I), "badge de certification"),
    ("APP-PERMIS-EXERCER",    re.compile(r"permis\s+d['e]\s*exercer",            re.I), "badge de certification"),
    ("APP-PERMIS-SEUL",       re.compile(r"\ble\s+permis\b(?!\s+de\s+conduire)", re.I), "le badge de certification"),
    ("APP-LICENCE",           re.compile(r"licence\s+d['e]\s*exercice",          re.I), "badge de certification"),
    ("APP-AUTORISATION",      re.compile(r"autorisation\s+de\s+travailler",      re.I), "badge de certification"),
)

PORTEE = (
    ("POR-DROIT",     re.compile(r"(?:donne|ouvre|confere)\s+(?:le\s+)?droit\s+(?:de|a|d')\s*\w+", re.I),
                      "atteste des competences evaluees"),
    ("POR-AUTORISE",  re.compile(r"autorise\s+(?:le\s+|la\s+|les\s+)?\w+\s+a\s+(?:travailler|exercer)", re.I),
                      "valorise le parcours du titulaire"),
    ("POR-PERMET",    re.compile(r"permet\s+de\s+(?:travailler|exercer)", re.I),
                      "valorise les competences demontrees"),
    ("POR-NECESSAIRE",re.compile(r"(?:obligatoire|necessaire|requis)\s+pour\s+(?:travailler|exercer)", re.I),
                      "valorise pour candidater"),
)

REGLES = APPELLATIONS + PORTEE

MOTIFS = {
    "APP-PERMIS-TRAVAILLER": "appellation proscrite : le dispositif n'est pas un permis",
    "APP-PERMIS-TRAVAIL":    "appellation proscrite : le dispositif n'est pas un permis",
    "APP-PERMIS-EXERCER":    "appellation proscrite : le dispositif n'est pas un permis",
    "APP-PERMIS-SEUL":       "appellation proscrite : le dispositif n'est pas un permis",
    "APP-LICENCE":           "appellation proscrite : le dispositif n'est pas une licence d'exercice",
    "APP-AUTORISATION":      "appellation proscrite : le dispositif n'autorise rien",
    "POR-DROIT":             "portee fautive : le badge n'ouvre aucun droit",
    "POR-AUTORISE":          "portee fautive : le badge valorise, il n'autorise pas",
    "POR-PERMET":            "portee fautive : le badge valorise, il n'autorise pas",
    "POR-NECESSAIRE":        "portee fautive : le badge n'est pas une condition d'acces",
}

# Champs textuels ou le vocabulaire du dispositif est visible par un candidat.
CHAMPS_SCANNES = (
    (Badge,                ("name", "description")),
    (Questionnaire,        ("title", "description")),
    (QuestionnaireVersion, ("title", "description")),
)

# --------------------------------------------------------------------------
# Comptages
# --------------------------------------------------------------------------

def _compteurs() -> dict:
    """Photo chiffree de l'etat du dispositif, avant ou apres traitement."""
    passations = QuestionnaireAttempt.objects.all()
    return {
        "passations_total":     passations.count(),
        "passations_reelles":   passations.filter(is_test = False).count(),
        "passations_test":      passations.filter(is_test = True).count(),
        "passations_terminees": passations.filter(status = c.ATTEMPT_COMPLETED).count(),
        "passations_par_questionnaire": {
            str(qid): passations.filter(questionnaire_id = qid).count()
            for qid in Questionnaire.objects.values_list("id", flat = True).order_by("id")
        },
        "badges_definis":     Badge.objects.count(),
        "badges_actifs":      Badge.objects.filter(active = True).count(),
        "badges_attribues":   UserBadge.objects.count(),
        "porteurs_distincts": UserBadge.objects.values("user_id").distinct().count(),
    }

INVARIANTS = (
    "passations_total", "passations_reelles", "passations_test", "passations_terminees",
    "badges_definis", "badges_attribues", "porteurs_distincts",
)

def _comptes_fictifs() -> set:
    """Noms d'utilisateur crees par `seed_demo` : les personnes fictives.

    Le rapport doit pouvoir distinguer une personne fictive d'un compte reel ;
    la source de verite est la liste figee de `seed_demo`, pas une heuristique
    sur le nom.
    """
    try:
        from profils.mainapp.management.commands.seed_demo import (
            ADMIN_ACCOUNT, CANDIDATES, RECRUITERS,
        )
    except ImportError:                                     # jeu de demo absent
        return set()
    return (
        {candidat["username"]  for candidat  in CANDIDATES}
        | {recruteur["username"] for recruteur in RECRUITERS}
        | {ADMIN_ACCOUNT["username"]}
    )

# --------------------------------------------------------------------------
# Detection et reecriture
# --------------------------------------------------------------------------

def _corriger(texte: str):
    """Retourne (texte corrige, [codes de regle appliques])."""
    corrige, codes = texte, []
    for code, motif, remplacement in REGLES:
        nouveau, touches = motif.subn(remplacement, corrige)
        if touches:
            corrige = nouveau
            codes.append(code)
    return corrige, codes

def _relever() -> list:
    """Toutes les occurrences fautives presentes en base."""
    releve = []
    for modele, champs in CHAMPS_SCANNES:
        for objet in modele.objects.all().order_by("id"):
            for champ in champs:
                avant = getattr(objet, champ) or ""
                apres, codes = _corriger(avant)
                if not codes:
                    continue
                releve.append({
                    "modele": modele.__name__,
                    "id":     objet.pk,
                    "champ":  champ,
                    "avant":  avant,
                    "apres":  apres,
                    "regles": codes,
                    "objet":  objet,
                })
    return releve

def _personnes_touchees(releve: list, fictifs: set) -> list:
    """Qui, parmi les titulaires de badges, voit sa certification changer.

    Seul un badge detenu par quelqu'un peut faire changer *sa* certification :
    un questionnaire renomme change l'intitule d'une epreuve, pas le badge
    affiche sur un profil. On ne remonte donc que les porteurs des badges dont
    le libelle a ete corrige.
    """
    badges_touches = {
        ligne["id"]: ligne for ligne in releve if ligne["modele"] == "Badge"
    }
    if not badges_touches:
        return []

    personnes = []
    detentions = (
        UserBadge.objects
        .filter(badge_id__in = badges_touches)
        .select_related("user", "badge")
        .order_by("user__username", "badge__code")
    )
    for detention in detentions:
        ligne = badges_touches[detention.badge_id]
        personnes.append({
            "utilisateur": detention.user.username,
            "fictive":     detention.user.username in fictifs,
            "badge":       detention.badge.code,
            "champ":       ligne["champ"],
            "avant":       ligne["avant"],
            "apres":       ligne["apres"],
            "motifs":      [MOTIFS[code] for code in ligne["regles"]],
        })
    return personnes

# --------------------------------------------------------------------------
# Commande
# --------------------------------------------------------------------------

class Command(BaseCommand):
    help = (
        "Remplace les appellations proscrites (<< permis de travailler >>...) par "
        "<< badge de certification >> et retablit la portee du dispositif. "
        "Simulation par defaut ; --apply pour ecrire."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply", action = "store_true",
            help = "ecrit reellement les corrections (sans ce drapeau : simulation)",
        )
        parser.add_argument(
            "--json", dest = "json_path", default = None,
            help = "ecrit le rapport complet en JSON dans ce fichier",
        )

    def handle(self, *args, **options):
        applique = options["apply"]
        fictifs  = _comptes_fictifs()

        avant     = _compteurs()
        releve    = _relever()
        personnes = _personnes_touchees(releve, fictifs)

        if applique and releve:
            with transaction.atomic():
                for ligne in releve:
                    objet = ligne["objet"]
                    setattr(objet, ligne["champ"], ligne["apres"])
                    objet.save(update_fields = [ligne["champ"]])

        apres = _compteurs()

        derives = [cle for cle in INVARIANTS if avant[cle] != apres[cle]]
        if derives:
            raise CommandError(
                "Invariant rompu : ce traitement ne doit toucher qu'a des libelles, "
                f"or ces compteurs ont bouge : {', '.join(derives)}. "
                "La transaction a ete annulee." if applique else
                f"Invariant rompu en simulation : {', '.join(derives)}."
            )

        rapport = {
            "mode":      "APPLIQUE" if applique else "SIMULATION",
            "avant":     avant,
            "apres":     apres,
            "occurrences": [
                {cle: valeur for cle, valeur in ligne.items() if cle != "objet"}
                for ligne in releve
            ],
            "personnes": personnes,
            "personnes_fictives_touchees": sum(1 for p in personnes if p["fictive"]),
            "personnes_reelles_touchees":  sum(1 for p in personnes if not p["fictive"]),
        }

        self._afficher(rapport, applique)

        if options["json_path"]:
            with open(options["json_path"], "w", encoding = "utf-8") as fichier:
                json.dump(rapport, fichier, ensure_ascii = False, indent = 2)
            self.stdout.write(f"\nRapport JSON ecrit dans {options['json_path']}.")

    # ----------------------------------------------------------------------

    def _afficher(self, rapport, applique):
        ecrire = self.stdout.write
        avant, apres = rapport["avant"], rapport["apres"]

        ecrire(self.style.MIGRATE_HEADING(
            f"\nNormalisation du vocabulaire de certification — mode {rapport['mode']}"
        ))

        ecrire("\nCompteurs (avant -> apres)")
        for cle in INVARIANTS:
            ecrire(f"  {cle:<22} {avant[cle]:>6} -> {apres[cle]:>6}")
        ecrire("  passations par questionnaire :")
        for qid, nombre in avant["passations_par_questionnaire"].items():
            ecrire(f"    questionnaire {qid:<4} {nombre:>6} -> "
                   f"{apres['passations_par_questionnaire'].get(qid, 0):>6}")

        ecrire(f"\nLibelles fautifs trouves : {len(rapport['occurrences'])}")
        for ligne in rapport["occurrences"]:
            ecrire(f"  [{ligne['modele']}#{ligne['id']}.{ligne['champ']}] "
                   f"{', '.join(ligne['regles'])}")
            ecrire(f"      avant : {ligne['avant']}")
            ecrire(f"      apres : {ligne['apres']}")

        fictives = rapport["personnes_fictives_touchees"]
        reelles  = rapport["personnes_reelles_touchees"]
        ecrire(f"\nPersonnes dont la certification change : {fictives + reelles} "
               f"({fictives} fictive(s), {reelles} reelle(s))")
        for personne in rapport["personnes"]:
            etiquette = "fictive" if personne["fictive"] else "REELLE"
            ecrire(f"  {personne['utilisateur']:<24} [{etiquette}] badge "
                   f"{personne['badge']} — {' ; '.join(personne['motifs'])}")

        if not rapport["occurrences"]:
            ecrire(self.style.SUCCESS(
                "\nAucune occurrence : le vocabulaire est deja conforme, "
                "aucune certification n'a change."
            ))
        elif applique:
            ecrire(self.style.SUCCESS("\nCorrections ecrites."))
        else:
            ecrire(self.style.WARNING(
                "\nSimulation : rien n'a ete ecrit. Relancer avec --apply."
            ))
