"""Preuve que la pagination du catalogue est deterministe.

    python manage.py prove_pagination

Une affirmation ne vaut rien ici : la commande parcourt le catalogue page par
page, de la premiere a la derniere, deux fois de suite, ecrit les deux listes
d'identifiants obtenues et le resultat de leur comparaison, puis verifie que :

  * les deux parcours renvoient exactement la meme liste, dans le meme ordre ;
  * aucun identifiant n'apparait deux fois ;
  * aucun profil visible du catalogue n'a ete oublie en route ;
  * le total releve est bien celui annonce par la pagination.

Un echec sort en code de retour non nul : la commande est utilisable telle
quelle dans une integration continue.

Le parcours passe par `search.search`, c'est-a-dire par le chemin de code que
le catalogue emprunte reellement. Un script qui interrogerait la base
directement mesurerait son propre `ORDER BY`, pas celui de l'application.
"""

import difflib
from pathlib import Path

from django.contrib.auth.models import AnonymousUser, User
from django.core.management.base import BaseCommand, CommandError

from profils.profiles import constants as c
from profils.profiles.models import ProfessionalProfile
from profils.profiles.search import ProfileQuery, base_queryset, search

class Command(BaseCommand):
    help = "Parcourt le catalogue deux fois et prouve que l'ordre est deterministe."

    def add_arguments(self, parser):
        parser.add_argument(
            "--page-size", type = int, default = c.DEFAULT_PAGE_SIZE,
            help = f"Taille de page du parcours (defaut : {c.DEFAULT_PAGE_SIZE}).",
        )
        parser.add_argument(
            "--sort", default = c.SORT_RELEVANCE, choices = [v for v, _ in c.SORT_OPTIONS],
            help = f"Tri parcouru (defaut : {c.SORT_RELEVANCE}).",
        )
        parser.add_argument(
            "--user", default = None,
            help = "Nom d'utilisateur du visiteur simule. Par defaut : visiteur anonyme.",
        )
        parser.add_argument(
            "--output-dir", default = "pagination-proof",
            help = "Dossier ou ecrire les deux relevés et leur comparaison.",
        )

    def handle(self, *args, **options):
        viewer     = self._viewer(options["user"])
        page_size  = options["page_size"]
        sort       = options["sort"]
        directory  = Path(options["output_dir"])
        directory.mkdir(parents = True, exist_ok = True)

        first,  announced_first  = self._walk(viewer, sort, page_size)
        second, announced_second = self._walk(viewer, sort, page_size)

        first_file  = directory / "ids-passage-1.txt"
        second_file = directory / "ids-passage-2.txt"
        report_file = directory / "comparaison.txt"

        self._write_ids(first_file, first)
        self._write_ids(second_file, second)

        failures = self._check(first, second, announced_first, announced_second, viewer)
        report   = self._report(
            first, second, announced_first, viewer, sort, page_size,
            first_file, second_file, failures,
        )
        report_file.write_text(report, encoding = "utf-8")

        self.stdout.write(report)
        self.stdout.write("")
        for path in (first_file, second_file, report_file):
            self.stdout.write(f"ecrit : {path}")

        if failures:
            raise CommandError(
                f"{len(failures)} verification(s) en echec : la pagination n'est pas "
                f"deterministe. Voir {report_file}."
            )
        self.stdout.write(self.style.SUCCESS("\nPagination deterministe : verifiee."))

    def _viewer(self, username):
        if not username:
            return AnonymousUser()
        try:
            return User.objects.get(username = username)
        except User.DoesNotExist:
            raise CommandError(f"utilisateur introuvable : {username!r}")

    def _walk(self, viewer, sort, page_size) -> tuple[list[int], int]:
        """Identifiants releves page par page, et total annonce par la pagination.

        La boucle suit `has_next` plutot qu'un nombre de pages calcule d'avance :
        c'est ce que fait un client qui pagine, et c'est donc ce qu'il faut
        mesurer. `pages` ne sert que de garde-fou contre une boucle infinie si
        la pagination se contredisait.
        """
        ids, page, guard = [], 1, None

        while True:
            result = search(
                ProfileQuery.from_params({
                    "sort": sort, "page": str(page), "page_size": str(page_size),
                }),
                viewer,
            )
            pagination = result["pagination"]
            guard      = pagination["pages"] if guard is None else guard

            ids.extend(profile.pk for profile in result["profiles"])

            if not pagination["has_next"] or page >= guard:
                return ids, pagination["total"]
            page += 1

    def _write_ids(self, path: Path, ids: list[int]) -> None:
        path.write_text("".join(f"{pk}\n" for pk in ids), encoding = "utf-8")

    def _check(self, first, second, announced_first, announced_second, viewer) -> list[str]:
        """Liste des verifications en echec. Vide si tout va bien."""
        failures = []

        if first != second:
            failures.append(
                "les deux parcours ne renvoient pas la meme liste d'identifiants"
            )
        if announced_first != announced_second:
            failures.append(
                f"le total annonce a change entre les deux parcours : "
                f"{announced_first} puis {announced_second}"
            )

        duplicates = len(first) - len(set(first))
        if duplicates:
            failures.append(f"{duplicates} identifiant(s) apparaissent plusieurs fois")

        missing = set(base_queryset(viewer).values_list("pk", flat = True)) - set(first)
        if missing:
            failures.append(
                f"{len(missing)} profil(s) visible(s) n'ont ete renvoyes par aucune page"
            )

        if len(first) != announced_first:
            failures.append(
                f"{len(first)} profils releves pour {announced_first} annonces par "
                f"la pagination"
            )
        return failures

    def _report(self, first, second, announced, viewer, sort, page_size,
                first_file, second_file, failures) -> str:
        """Compte rendu lisible, ecrit sur disque et sur la sortie standard."""
        visible = base_queryset(viewer).count()
        total   = ProfessionalProfile.objects.count()
        missing = set(base_queryset(viewer).values_list("pk", flat = True)) - set(first)

        diff = list(difflib.unified_diff(
            [f"{pk}\n" for pk in first], [f"{pk}\n" for pk in second],
            fromfile = str(first_file), tofile = str(second_file),
        ))

        lines = [
            "Preuve de determinisme de la pagination du catalogue",
            "=" * 52,
            "",
            f"Visiteur         : {getattr(viewer, 'username', None) or 'anonyme'}",
            f"Tri              : {sort}",
            f"Taille de page   : {page_size}",
            "",
            f"Profils en base                        : {total}",
            f"Profils visibles de ce visiteur        : {visible}",
            f"Total annonce par la pagination        : {announced}",
            f"Identifiants releves, parcours 1       : {len(first)}",
            f"Identifiants releves, parcours 2       : {len(second)}",
            f"Identifiants distincts, parcours 1     : {len(set(first))}",
            "",
            "Un profil non recherchable ou dont la visibilite exclut ce visiteur",
            "est legitimement absent du catalogue : c'est au nombre de profils",
            "visibles, et non au nombre de profils en base, que le releve doit",
            "correspondre. Les deux sont donnes ci-dessus pour que l'ecart soit",
            "verifiable.",
            "",
            "Comparaison des deux parcours",
            "-" * 29,
            "".join(diff).rstrip() if diff else "Aucune difference : les deux fichiers sont identiques.",
            "",
        ]

        if missing:
            lines += [
                f"Profils visibles jamais renvoyes ({len(missing)}) : "
                f"{sorted(missing)}",
                "",
            ]

        if failures:
            lines += ["ECHEC", "-" * 5] + [f"  - {failure}" for failure in failures]
        else:
            lines += [
                "RESULTAT",
                "-" * 8,
                "  - les deux parcours renvoient la meme liste, dans le meme ordre",
                "  - aucun identifiant en double",
                "  - aucun profil visible oublie",
                "  - le total releve est celui annonce par la pagination",
            ]
        return "\n".join(lines) + "\n"
