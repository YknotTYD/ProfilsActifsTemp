"""Registre des types de questions.

C'est le point d'extension principal du systeme : ajouter un type de question
consiste a ecrire une sous-classe de `QuestionType` et a la decorer avec
`@register`. Aucune autre partie du systeme (modeles, API, scoring, conditions,
templates) n'a besoin d'etre modifiee.

Un handler est responsable de quatre choses, et de rien d'autre :

  * `validate_config`   -> valider la configuration saisie par l'admin
  * `normalize_answer`  -> transformer la saisie brute du client en valeur
                           canonique stockee en base (ou lever une erreur)
  * `evaluate`          -> comparer une valeur canonique aux reponses attendues
                           et retourner un ratio de justesse entre 0 et 1
  * `comparable`        -> exposer une valeur comparable pour les conditions

La valeur canonique est toujours un dict JSON-serialisable. Le format depend du
type mais reste stable : c'est lui qui est persiste dans `UserAnswer.value`.
"""

from datetime import date, datetime, time
from decimal  import Decimal, InvalidOperation

from . import constants as c
from .countries import COUNTRY_CODES, COUNTRY_NAMES

class ConfigError(ValueError):
    """Configuration de question invalide (cote administration)."""

class AnswerError(ValueError):
    """Reponse utilisateur invalide (cote utilisateur)."""

_REGISTRY: dict[str, "QuestionType"] = {}

def register(cls):
    """Decorateur d'enregistrement d'un type de question."""
    instance = cls()
    if instance.id in _REGISTRY:
        raise RuntimeError(f"type de question deja enregistre: {instance.id}")
    if not instance.widget:
        raise RuntimeError(
            f"le type {instance.id} ne declare aucun widget : le participant "
            f"n'aurait aucun moyen de repondre"
        )
    _REGISTRY[instance.id] = instance
    return cls

def get_type(type_id: str) -> "QuestionType":
    try:
        return _REGISTRY[type_id]
    except KeyError:
        raise ConfigError(f"type de question inconnu: {type_id}")

def all_types() -> list["QuestionType"]:
    return list(_REGISTRY.values())

def type_choices() -> list[tuple[str, str]]:
    return [(t.id, t.label) for t in _REGISTRY.values()]

def field(key, label, kind = "text", *, help = "", example = "",
          choices = None, default = None, unit = None) -> dict:
    """Descripteur d'un champ de configuration, consomme par l'editeur.

    C'est ce qui permet a l'interface d'administration de construire un vrai
    formulaire par type de question, avec libelles et exemples, au lieu de
    demander du JSON a la main.
    """
    return {
        "key":     key,
        "label":   label,
        "kind":    kind,
        "help":    help,
        "example": str(example) if example != "" else "",
        "choices": choices,
        "default": default,
        "unit":    unit,
    }

def catalog() -> list[dict]:
    """Description du catalogue, consommee par l'editeur d'administration."""
    return [
        {
            "id":           t.id,
            "family":       t.family,
            "label":        t.label,
            "hint":         t.hint,
            "example":      t.example,
            "uses_options": t.uses_options,
            "multiple":     t.multiple,
            "fixed_options": [label for _, label in getattr(t, "fixed_options", ())],
            "config_fields": t.config_fields(),
            "expected_kinds": list(t.expected_kinds),
            "value_input":  t.value_input,
            "value_choices": t.value_choices(),
            "expected_help": t.expected_help,
            "expected_rules": t.expected_rules(),
            "widget":       t.widget,
        }
        for t in _REGISTRY.values()
    ]

def _as_decimal(raw, field = "valeur") -> Decimal:
    if isinstance(raw, bool):
        raise AnswerError(f"{field}: un booleen n'est pas un nombre")
    try:
        return Decimal(str(raw))
    except (InvalidOperation, TypeError, ValueError):
        raise AnswerError(f"{field}: nombre invalide ({raw!r})")

def _as_int(raw, field = "valeur") -> int:
    value = _as_decimal(raw, field)
    if value != value.to_integral_value():
        raise AnswerError(f"{field}: un entier est attendu")
    return int(value)

def _clamp_ratio(value: float) -> float:
    return max(0.0, min(1.0, value))

def _rule_matches(rule: dict, value) -> bool:
    """Evalue une regle de reponse attendue sur une valeur comparable."""
    kind = rule.get("type")

    if kind == "exact":
        return value == _coerce_like(rule.get("value"), value)
    if kind == "one_of":
        return any(value == _coerce_like(v, value) for v in rule.get("values", []))
    if kind == "range":
        low, high = rule.get("min"), rule.get("max")
        if low is not None:
            low = _coerce_like(low, value)
            ok  = value >= low if rule.get("min_inclusive", True) else value > low
            if not ok:
                return False
        if high is not None:
            high = _coerce_like(high, value)
            ok   = value <= high if rule.get("max_inclusive", True) else value < high
            if not ok:
                return False
        return True
    if kind == "min":
        return value >= _coerce_like(rule.get("value"), value)
    if kind == "max":
        return value <= _coerce_like(rule.get("value"), value)
    raise ConfigError(f"regle de reponse attendue inconnue: {kind!r}")

def _coerce_like(raw, reference):
    """Aligne le type de `raw` sur celui de `reference` pour la comparaison."""
    if isinstance(reference, Decimal):
        return _as_decimal(raw)
    if isinstance(reference, int) and not isinstance(reference, bool):
        return _as_int(raw)
    return raw

def evaluate_rules(expected: dict, value) -> float:
    """Evalue un bloc `{"match": "any"|"all", "rules": [...]}`."""
    rules = expected.get("rules") or []
    if not rules:
        return 0.0
    match = expected.get("match", "any")
    hits  = [_rule_matches(r, value) for r in rules]
    return 1.0 if (all(hits) if match == "all" else any(hits)) else 0.0

RULE_LABELS = {
    "exact":  "Exactement cette valeur",
    "one_of": "L\'une de ces valeurs",
    "range":  "Comprise entre",
    "min":    "Superieure ou egale a",
    "max":    "Inferieure ou egale a",
}

class QuestionType:

    id           = ""
    family       = ""
    label        = ""
    hint         = ""
    example      = ""
    uses_options = False
    multiple     = False
    expected_kinds: tuple = ()
    value_input  = "text"
    widget       = ""
    expected_help = ""

    def config_fields(self) -> list[dict]:
        """Champs de configuration, decrits pour que l'editeur les affiche."""
        return []

    def expected_rules(self) -> list[dict]:
        """Formes de reponse attendue proposees, avec les champs a saisir.

        C'est ce qui permet a l'editeur de construire un vrai constructeur de
        regles : il n'a pas a savoir qu'un intervalle de dates se decrit par un
        debut et une fin, ni qu'une adresse se decrit composant par composant.
        """
        return [
            {"kind": kind, "label": RULE_LABELS[kind], "fields": self.rule_fields(kind)}
            for kind in self.expected_kinds if kind != "combination"
        ]

    def rule_fields(self, kind: str) -> list[dict]:
        """Champs a saisir pour une forme de regle donnee."""
        if kind == "one_of":
            return [{"path": "values", "label": "valeurs acceptees",
                     "input": self.value_input, "multiple": True}]
        if kind == "range":
            return [{"path": "min", "label": "minimum", "input": self.value_input},
                    {"path": "max", "label": "maximum", "input": self.value_input}]
        return [{"path": "value", "label": "valeur", "input": self.value_input}]

    def value_choices(self) -> list | None:
        """Valeurs proposables pour une reponse attendue, si le vocabulaire est fixe.

        Renvoie None quand la saisie est libre dans les bornes du type, ou quand
        le vocabulaire depend de la configuration de la question (villes).
        """
        return None

    def validate_config(self, config: dict) -> dict:
        return dict(config or {})

    def validate_expected(self, expected: dict, config: dict) -> dict:
        expected = dict(expected or {})
        rules    = expected.get("rules") or []
        if not isinstance(rules, list):
            raise ConfigError("`rules` doit etre une liste")
        for rule in rules:
            if not isinstance(rule, dict) or rule.get("type") not in self.expected_kinds:
                raise ConfigError(
                    f"regle non supportee pour le type {self.id}: {rule!r}"
                )
        if expected.get("match", "any") not in ("any", "all"):
            raise ConfigError("`match` doit valoir 'any' ou 'all'")
        expected["rules"] = rules
        return expected

    def has_expected(self, question) -> bool:
        return bool((question.expected_config or {}).get("rules"))

    def normalize_answer(self, question, raw) -> dict | None:
        """Retourne la valeur canonique, ou None si la reponse est vide."""
        raise NotImplementedError

    def is_answered(self, value) -> bool:
        return value is not None

    def comparable(self, question, value):
        """Valeur utilisee par le moteur de conditions."""
        raise NotImplementedError

    def evaluate(self, question, value) -> tuple[float, dict]:
        """Retourne (ratio 0..1, details)."""
        if not self.has_expected(question):
            return 0.0, {"graded": False}
        ratio = evaluate_rules(question.expected_config, self.comparable(question, value))
        return ratio, {"graded": True, "ratio": ratio}

    def display(self, question, value, snapshot = None) -> str:
        """Rendu lisible d'une reponse, pour l'audit et les resultats."""
        return "" if value is None else str(value)

    def describe_expected(self, question, snapshot = None) -> str:
        rules = (question.expected_config or {}).get("rules") or []
        parts = []
        for rule in rules:
            kind = rule.get("type")
            if kind == "exact":
                parts.append(str(rule.get("value")))
            elif kind == "one_of":
                parts.append(" ou ".join(str(v) for v in rule.get("values", [])))
            elif kind == "range":
                parts.append(f"{rule.get('min')} a {rule.get('max')}")
            elif kind == "min":
                parts.append(f">= {rule.get('value')}")
            elif kind == "max":
                parts.append(f"<= {rule.get('value')}")
        return " / ".join(parts)

class ChoiceType(QuestionType):
    """Base des types a options.

    Valeur canonique : {"option_ids": [12, 15]}
    Les identifiants d'options sont stables et persistes ; le texte affiche
    n'intervient jamais dans la comparaison.
    """

    family         = c.FAMILY_CHOICE
    uses_options   = True
    expected_kinds = ("combination",)
    min_options    = 2
    widget         = "choice"

    expected_help = ("Cochez la ou les bonnes reponses directement dans la liste "
                     "ci-dessus.")

    def config_fields(self) -> list[dict]:
        fields = [field(
            "shuffle_options", "Melanger l'ordre des reponses", "bool",
            help = "Chaque participant voit les propositions dans un ordre different.",
        )]
        if self.multiple:
            fields += [
                field("min_selected", "Minimum de cases a cocher", "int",
                      help = "Laissez vide pour ne rien imposer.", example = "2"),
                field("max_selected", "Maximum de cases a cocher", "int",
                      help = "Laissez vide pour ne rien imposer.", example = "3"),
                field("penalty_per_wrong", "Penalite par mauvaise case", "number",
                      default = 1,
                      help = "1 = une mauvaise coche annule une bonne. 0 = les mauvaises "
                             "coches sont ignorees. 0.5 = elles comptent a moitie.",
                      example = "1"),
            ]
        return fields

    def validate_config(self, config: dict) -> dict:
        config = dict(config or {})
        for key in ("min_selected", "max_selected"):
            if config.get(key) is not None:
                config[key] = _as_int(config[key], key)
        if config.get("penalty_per_wrong") is not None:
            config["penalty_per_wrong"] = float(config["penalty_per_wrong"])
        low, high = config.get("min_selected"), config.get("max_selected")
        if low is not None and high is not None and low > high:
            raise ConfigError("min_selected ne peut pas depasser max_selected")
        return config

    def validate_expected(self, expected: dict, config: dict) -> dict:
        expected     = dict(expected or {})
        combinations = expected.get("combinations") or []
        if not isinstance(combinations, list):
            raise ConfigError("`combinations` doit etre une liste de listes")
        for combo in combinations:
            if not isinstance(combo, list):
                raise ConfigError("chaque combinaison doit etre une liste de cles d'options")
        expected["combinations"] = combinations
        expected.setdefault("rules", [])
        return expected

    def has_expected(self, question) -> bool:
        if (question.expected_config or {}).get("combinations"):
            return True
        return question.options.filter(is_correct = True).exists()

    def normalize_answer(self, question, raw) -> dict | None:
        if raw is None:
            return None
        if isinstance(raw, dict):
            raw = raw.get("option_ids", raw.get("option_id"))
        if raw is None or raw == [] or raw == "":
            return None

        ids = raw if isinstance(raw, list) else [raw]
        ids = [_as_int(i, "option_id") for i in ids]

        if not self.multiple and len(ids) > 1:
            raise AnswerError("une seule option peut etre selectionnee")

        valid = set(question.options.values_list("id", flat = True))
        unknown = [i for i in ids if i not in valid]
        if unknown:
            raise AnswerError(f"option(s) inconnue(s) pour cette question: {unknown}")

        ids    = sorted(dict.fromkeys(ids))
        config = question.config or {}
        low    = config.get("min_selected")
        high   = config.get("max_selected")
        if low is not None and len(ids) < low:
            raise AnswerError(f"selectionnez au moins {low} option(s)")
        if high is not None and len(ids) > high:
            raise AnswerError(f"selectionnez au plus {high} option(s)")

        return {"option_ids": ids}

    def is_answered(self, value) -> bool:
        return bool(value and value.get("option_ids"))

    def comparable(self, question, value):
        return list((value or {}).get("option_ids") or [])

    def evaluate(self, question, value) -> tuple[float, dict]:
        selected = set(self.comparable(question, value))
        options  = {o.id: o for o in question.options.all()}

        combinations = (question.expected_config or {}).get("combinations") or []
        if combinations:
            by_key = {o.stable_key: o.id for o in options.values()}
            for combo in combinations:
                wanted = {by_key.get(str(k), k) for k in combo}
                if selected == wanted:
                    return 1.0, {"graded": True, "ratio": 1.0, "matched_combination": combo}
            return 0.0, {"graded": True, "ratio": 0.0, "matched_combination": None}

        correct = {oid for oid, o in options.items() if o.is_correct}
        if not correct:
            return 0.0, {"graded": False}

        good = len(selected & correct)
        bad  = len(selected - correct)

        if not self.multiple:
            ratio = 1.0 if (good == 1 and bad == 0) else 0.0
        else:
            penalty = float((question.config or {}).get("penalty_per_wrong", 1.0))
            ratio   = _clamp_ratio((good - penalty * bad) / len(correct))

        return ratio, {
            "graded":        True,
            "ratio":         ratio,
            "correct_hit":   good,
            "wrong_hit":     bad,
            "correct_total": len(correct),
        }

    def display(self, question, value, snapshot = None) -> str:
        ids = self.comparable(question, value)
        if snapshot and snapshot.get("options"):
            texts = {int(o["id"]): o["text"] for o in snapshot["options"]}
        else:
            texts = dict(question.options.values_list("id", "text"))
        return ", ".join(texts.get(i, f"#{i}") for i in ids)

    def describe_expected(self, question, snapshot = None) -> str:
        combinations = (question.expected_config or {}).get("combinations") or []
        if combinations:
            by_key = {o.stable_key: o.text for o in question.options.all()}
            return " | ".join(
                ", ".join(by_key.get(str(k), str(k)) for k in combo)
                for combo in combinations
            )
        return ", ".join(
            question.options.filter(is_correct = True).values_list("text", flat = True)
        )

@register
class SingleChoice(ChoiceType):
    id    = c.TYPE_SINGLE_CHOICE
    label = "Choix unique"
    hint    = "Une seule reponse possible parmi plusieurs."
    example = "Quelle est la capitale de la France ? -> Paris / Lyon / Marseille"

@register
class MultipleChoice(ChoiceType):
    id       = c.TYPE_MULTIPLE_CHOICE
    label    = "Choix multiple"
    multiple = True
    hint    = "Plusieurs reponses possibles. Le score peut etre partiel."
    example = "Lesquels de ces langages sont compiles ? -> Java, Rust, Python"

@register
class Checkbox(ChoiceType):
    id       = c.TYPE_CHECKBOX
    label    = "Cases a cocher"
    multiple = True
    hint    = "Cases a cocher, identique au choix multiple."
    example = "Quels outils utilisez-vous au quotidien ?"

@register
class Dropdown(ChoiceType):
    id    = c.TYPE_DROPDOWN
    label = "Liste deroulante"
    widget   = "dropdown"
    hint    = "Choix unique dans un menu deroulant. Pratique au-dela de 6 propositions."
    example = "Dans quel departement travaillez-vous ?"

@register
class MultiSelect(ChoiceType):
    id       = c.TYPE_MULTI_SELECT
    label    = "Liste multi-selection"
    widget   = "dropdown"
    multiple = True
    hint    = "Choix multiple dans une liste deroulante."
    example = "Quelles langues parlez-vous ?"

class FixedChoiceType(ChoiceType):
    """Type a options imposees : les options sont creees automatiquement."""

    fixed_options: tuple = ()

    def config_fields(self) -> list[dict]:
        return []

@register
class YesNo(FixedChoiceType):
    id            = c.TYPE_YES_NO
    label         = "Oui / Non"
    fixed_options = (("yes", "Oui"), ("no", "Non"))
    hint    = "Oui ou non. Les deux reponses sont creees automatiquement."
    example = "Avez-vous une voiture ?"

@register
class TrueFalse(FixedChoiceType):
    id            = c.TYPE_TRUE_FALSE
    label         = "Vrai / Faux"
    fixed_options = (("true", "Vrai"), ("false", "Faux"))
    hint    = "Vrai ou faux. Les deux reponses sont creees automatiquement."
    example = "Python est un langage compile. -> Vrai / Faux"

@register
class Scale(ChoiceType):
    """Echelle / notation.

    Les options portent la valeur numerique de l'echelon, ce qui permet a la
    fois une comparaison par identifiant et une condition numerique.
    """

    id             = c.TYPE_SCALE
    label          = "Echelle / notation"
    expected_kinds = ("combination", "exact", "one_of", "range", "min", "max")

    value_input   = "number"
    expected_help = ("Cochez les echelons corrects, ou definissez une regle "
                     "numerique (par exemple : entre 4 et 5).")
    hint    = "Une note sur une echelle, par exemple de 1 a 5."
    example = "Quel est votre niveau en Python ? -> 1 a 5"

    def config_fields(self) -> list[dict]:
        return [
            field("min",  "Premier echelon", "int", default = 1, example = "1"),
            field("max",  "Dernier echelon", "int", default = 5, example = "5"),
            field("step", "Pas entre deux echelons", "int", default = 1,
                  help = "1 = 1, 2, 3, 4, 5. Mettez 2 pour 1, 3, 5.", example = "1"),
        ]

    def validate_config(self, config: dict) -> dict:
        config = dict(config or {})
        config["min"]  = _as_int(config.get("min", 1), "min")
        config["max"]  = _as_int(config.get("max", 5), "max")
        config["step"] = _as_int(config.get("step", 1), "step")
        if config["step"] < 1:
            raise ConfigError("step doit etre >= 1")
        if config["min"] >= config["max"]:
            raise ConfigError("min doit etre strictement inferieur a max")
        return config

    def validate_expected(self, expected: dict, config: dict) -> dict:
        expected = ChoiceType.validate_expected(self, expected, config)
        return QuestionType.validate_expected(self, expected, config)

    def has_expected(self, question) -> bool:
        if (question.expected_config or {}).get("rules"):
            return True
        return ChoiceType.has_expected(self, question)

    def evaluate(self, question, value) -> tuple[float, dict]:
        rules = (question.expected_config or {}).get("rules") or []
        if rules:
            numeric = self.numeric_value(question, value)
            if numeric is None:
                return 0.0, {"graded": True, "ratio": 0.0}
            ratio = evaluate_rules(question.expected_config, numeric)
            return ratio, {"graded": True, "ratio": ratio, "value": int(numeric)}
        return ChoiceType.evaluate(self, question, value)

    def numeric_value(self, question, value):
        ids = self.comparable(question, value)
        if not ids:
            return None
        option = question.options.filter(id = ids[0]).first()
        if option is None or option.value in (None, ""):
            return None
        try:
            return _as_int(option.value)
        except AnswerError:
            return None

class NumericType(QuestionType):
    """Base des types numeriques.

    Valeur canonique : {"number": "21.5", "unit": "C"}
    Le nombre est stocke en chaine pour rester exact (Decimal) en JSON.
    """

    family         = c.FAMILY_NUMERIC
    expected_kinds = ("exact", "one_of", "range", "min", "max")
    widget         = "number"
    integer_only   = False
    units: tuple   = ()
    default_unit   = None

    value_input   = "number"
    expected_help = "Definissez la valeur exacte attendue, ou une plage acceptee."

    def config_fields(self) -> list[dict]:
        fields = [
            field("min", "Valeur minimale acceptee", "number",
                  help = "Une saisie hors bornes est refusee immediatement. "
                         "Laissez vide pour ne pas limiter.", example = "0"),
            field("max", "Valeur maximale acceptee", "number",
                  help = "Laissez vide pour ne pas limiter.", example = "100"),
        ]
        if not self.integer_only:
            fields.append(field(
                "decimals", "Nombre de decimales autorisees", "int",
                help = "2 accepte 1,25 mais refuse 1,256. Laissez vide pour ne rien imposer.",
                example = "2"))
        if self.units:
            fields += [
                field("unit", "Unite", "select", choices = list(self.units),
                      default = self.default_unit,
                      help = "L'unite affichee a cote du champ de saisie."),
                field("allow_unit_choice", "Laisser le participant choisir l'unite", "bool",
                      help = "Rarement utile : la comparaison avec la reponse attendue "
                             "ne convertit pas les unites."),
            ]
        return fields

    def validate_config(self, config: dict) -> dict:
        config = dict(config or {})
        for key in ("min", "max"):
            if config.get(key) is not None:
                config[key] = str(_as_decimal(config[key], key))
        if config.get("decimals") is not None:
            config["decimals"] = _as_int(config["decimals"], "decimals")
            if config["decimals"] < 0:
                raise ConfigError("decimals doit etre >= 0")
        unit = config.get("unit", self.default_unit)
        if self.units and unit is not None and unit not in self.units:
            raise ConfigError(f"unite invalide: {unit!r} (attendu: {list(self.units)})")
        if unit is not None:
            config["unit"] = unit
        low, high = config.get("min"), config.get("max")
        if low is not None and high is not None and Decimal(low) > Decimal(high):
            raise ConfigError("min ne peut pas depasser max")
        return config

    def normalize_answer(self, question, raw) -> dict | None:
        if raw is None or raw == "":
            return None
        unit = None
        if isinstance(raw, dict):
            unit = raw.get("unit")
            raw  = raw.get("number", raw.get("value"))
            if raw is None or raw == "":
                return None

        config = question.config or {}
        number = _as_decimal(raw)

        if self.integer_only and number != number.to_integral_value():
            raise AnswerError("un nombre entier est attendu")

        decimals = config.get("decimals")
        if decimals is not None:
            quantum = Decimal(1).scaleb(-decimals)
            if number != number.quantize(quantum, rounding = "ROUND_DOWN"):
                raise AnswerError(f"au plus {decimals} decimale(s)")

        if config.get("min") is not None and number < Decimal(config["min"]):
            raise AnswerError(f"la valeur doit etre >= {config['min']}")
        if config.get("max") is not None and number > Decimal(config["max"]):
            raise AnswerError(f"la valeur doit etre <= {config['max']}")

        expected_unit = config.get("unit", self.default_unit)
        if unit is None:
            unit = expected_unit
        elif self.units and unit not in self.units:
            raise AnswerError(f"unite invalide: {unit!r}")
        elif not config.get("allow_unit_choice", False) and expected_unit and unit != expected_unit:
            raise AnswerError(f"unite attendue: {expected_unit}")

        return {"number": str(number), "unit": unit}

    def is_answered(self, value) -> bool:
        return bool(value) and value.get("number") not in (None, "")

    def comparable(self, question, value):
        if not self.is_answered(value):
            return None
        return _as_decimal(value["number"])

    def display(self, question, value, snapshot = None) -> str:
        if not self.is_answered(value):
            return ""
        unit = value.get("unit") or ""
        return f"{value['number']}{(' ' + unit) if unit else ''}"

@register
class IntegerType(NumericType):
    id           = c.TYPE_INTEGER
    label        = "Entier"
    integer_only = True
    hint    = "Un nombre entier, sans decimale."
    example = "Combien de collaborateurs dans votre equipe ?"

@register
class DecimalType(NumericType):
    id    = c.TYPE_DECIMAL
    label = "Nombre decimal"
    hint    = "Un nombre a virgule."
    example = "Quel est votre coefficient horaire ?"

@register
class PercentageType(NumericType):
    id           = c.TYPE_PERCENTAGE
    label        = "Pourcentage"
    units        = ("%",)
    default_unit = "%"
    hint    = "Un pourcentage entre 0 et 100."
    example = "Quel taux de reussite visez-vous ?"

    def validate_config(self, config: dict) -> dict:
        config = dict(config or {})
        config.setdefault("min", "0")
        config.setdefault("max", "100")
        return NumericType.validate_config(self, config)

@register
class TemperatureType(NumericType):
    id           = c.TYPE_TEMPERATURE
    label        = "Temperature"
    units        = ("C", "F", "K")
    default_unit = "C"
    hint    = "Une temperature, avec son unite."
    example = "Temperature de confort au bureau ? -> entre 18 et 22 C"

@register
class DistanceType(NumericType):
    id           = c.TYPE_DISTANCE
    label        = "Distance"
    units        = ("mm", "cm", "m", "km", "mi")
    default_unit = "m"
    hint    = "Une distance, avec son unite."
    example = "A quelle distance habitez-vous du bureau ?"

@register
class WeightType(NumericType):
    id           = c.TYPE_WEIGHT
    label        = "Poids"
    units        = ("g", "kg", "t", "lb")
    default_unit = "kg"
    hint    = "Un poids, avec son unite."
    example = "Quelle charge maximale peut porter cet equipement ?"

@register
class HeightType(NumericType):
    id           = c.TYPE_HEIGHT
    label        = "Taille"
    units        = ("cm", "m", "in", "ft")
    default_unit = "cm"
    hint    = "Une taille, avec son unite."
    example = "Quelle hauteur de plan de travail preferez-vous ?"

@register
class SpeedType(NumericType):
    id           = c.TYPE_SPEED
    label        = "Vitesse"
    units        = ("km/h", "m/s", "mph", "kn")
    default_unit = "km/h"
    hint    = "Une vitesse, avec son unite."
    example = "Quelle vitesse maximale sur cette portion ?"

@register
class DurationType(NumericType):
    id           = c.TYPE_DURATION
    label        = "Duree"
    units        = ("s", "min", "h", "d")
    default_unit = "min"
    hint    = "Une duree comme quantite (secondes, minutes, heures, jours)."
    example = "Combien de temps dure votre trajet ?"

class TemporalType(QuestionType):

    family         = c.FAMILY_TEMPORAL
    expected_kinds = ("exact", "one_of", "range", "min", "max")
    key            = "value"
    widget         = "temporal"

    def parse(self, raw: str):
        raise NotImplementedError

    def format(self, parsed) -> str:
        return parsed.isoformat()

    expected_help = "Definissez la valeur exacte attendue, ou une plage acceptee."

    def config_fields(self) -> list[dict]:
        return [
            field("min", "Pas avant", self.value_input,
                  help = "Laissez vide pour ne pas limiter."),
            field("max", "Pas apres", self.value_input,
                  help = "Laissez vide pour ne pas limiter."),
        ]

    def validate_config(self, config: dict) -> dict:
        config = dict(config or {})
        for bound in ("min", "max"):
            if config.get(bound):
                config[bound] = self.format(self.parse(config[bound]))
        return config

    def validate_expected(self, expected: dict, config: dict) -> dict:
        expected = QuestionType.validate_expected(self, expected, config)
        for rule in expected["rules"]:
            for field in ("value", "min", "max"):
                if rule.get(field) is not None:
                    rule[field] = self.format(self.parse(rule[field]))
            if rule.get("values"):
                rule["values"] = [self.format(self.parse(v)) for v in rule["values"]]
        return expected

    def normalize_answer(self, question, raw) -> dict | None:
        if raw is None or raw == "":
            return None
        if isinstance(raw, dict):
            raw = raw.get(self.key, raw.get("value"))
            if raw in (None, ""):
                return None

        parsed = self.parse(raw)
        config = question.config or {}
        if config.get("min") and parsed < self.parse(config["min"]):
            raise AnswerError(f"la valeur doit etre >= {config['min']}")
        if config.get("max") and parsed > self.parse(config["max"]):
            raise AnswerError(f"la valeur doit etre <= {config['max']}")
        return {self.key: self.format(parsed)}

    def is_answered(self, value) -> bool:
        return bool(value) and value.get(self.key) not in (None, "")

    def comparable(self, question, value):
        return value[self.key] if self.is_answered(value) else None

    def display(self, question, value, snapshot = None) -> str:
        return value[self.key] if self.is_answered(value) else ""

@register
class DateType(TemporalType):
    id    = c.TYPE_DATE
    label = "Date"
    key   = "date"
    value_input = "date"
    hint    = "Une date, sans heure."
    example = "Quand avez-vous obtenu votre diplome ?"

    def parse(self, raw):
        if isinstance(raw, date) and not isinstance(raw, datetime):
            return raw
        try:
            return date.fromisoformat(str(raw))
        except ValueError:
            raise AnswerError(f"date invalide: {raw!r} (format attendu AAAA-MM-JJ)")

@register
class TimeType(TemporalType):
    id    = c.TYPE_TIME
    label = "Heure"
    key   = "time"
    value_input = "time"
    hint    = "Une heure precise, secondes comprises."
    example = "A quelle heure demarre votre astreinte ?"

    def parse(self, raw):
        if isinstance(raw, time):
            return raw
        try:
            return time.fromisoformat(str(raw))
        except ValueError:
            raise AnswerError(f"heure invalide: {raw!r} (format attendu HH:MM[:SS])")

@register
class DateTimeType(TemporalType):
    id    = c.TYPE_DATETIME
    label = "Date et heure"
    key   = "datetime"
    value_input = "datetime"
    hint    = "Une date et une heure."
    example = "Quand a eu lieu l'incident ?"

    def parse(self, raw):
        if isinstance(raw, datetime):
            return raw
        try:
            return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            raise AnswerError(f"date/heure invalide: {raw!r}")

@register
class HourMinuteType(TemporalType):
    id    = c.TYPE_HOUR_MINUTE
    label = "Heure / minute"
    key   = "time"
    value_input = "time"
    hint    = "Une heure et des minutes, sans les secondes."
    example = "A quelle heure arrivez-vous le matin ?"

    def parse(self, raw):
        if isinstance(raw, time):
            return raw.replace(second = 0, microsecond = 0)
        try:
            parsed = time.fromisoformat(str(raw))
        except ValueError:
            raise AnswerError(f"heure invalide: {raw!r} (format attendu HH:MM)")
        return parsed.replace(second = 0, microsecond = 0)

    def format(self, parsed) -> str:
        return parsed.strftime("%H:%M")

@register
class DateRangeType(QuestionType):
    """Intervalle de dates.

    Valeur canonique : {"start": "2026-01-01", "end": "2026-01-31"}
    """

    id             = c.TYPE_DATE_RANGE
    family         = c.FAMILY_TEMPORAL
    label          = "Intervalle de dates"
    widget         = "date_range"
    expected_kinds = ("exact", "range")

    value_input   = "date"
    expected_help = "La reponse est correcte si l'intervalle donne tombe dans celui attendu."

    def rule_fields(self, kind: str) -> list[dict]:
        if kind == "exact":
            return [{"path": "start", "label": "du", "input": "date"},
                    {"path": "end",   "label": "au", "input": "date"}]
        return [{"path": "min", "label": "pas avant", "input": "date"},
                {"path": "max", "label": "pas apres", "input": "date"}]
    hint    = "Un intervalle entre deux dates."
    example = "Sur quelle periode etiez-vous en conge ?"

    def config_fields(self) -> list[dict]:
        return [
            field("min", "Pas avant", "date", help = "Laissez vide pour ne pas limiter."),
            field("max", "Pas apres", "date", help = "Laissez vide pour ne pas limiter."),
            field("max_days", "Duree maximale de l'intervalle (jours)", "int",
                  help = "Laissez vide pour ne pas limiter.", example = "7"),
        ]

    def _parse(self, raw):
        try:
            return date.fromisoformat(str(raw))
        except ValueError:
            raise AnswerError(f"date invalide: {raw!r} (format attendu AAAA-MM-JJ)")

    def validate_config(self, config: dict) -> dict:
        config = dict(config or {})
        for bound in ("min", "max"):
            if config.get(bound):
                config[bound] = self._parse(config[bound]).isoformat()
        if config.get("max_days") is not None:
            config["max_days"] = _as_int(config["max_days"], "max_days")
        return config

    def normalize_answer(self, question, raw) -> dict | None:
        if not raw:
            return None
        if not isinstance(raw, dict):
            raise AnswerError("un intervalle attend {'start': ..., 'end': ...}")
        if not raw.get("start") or not raw.get("end"):
            return None

        start, end = self._parse(raw["start"]), self._parse(raw["end"])
        if start > end:
            raise AnswerError("la date de debut doit preceder la date de fin")

        config = question.config or {}
        if config.get("min") and start < self._parse(config["min"]):
            raise AnswerError(f"debut avant la borne minimale {config['min']}")
        if config.get("max") and end > self._parse(config["max"]):
            raise AnswerError(f"fin apres la borne maximale {config['max']}")
        if config.get("max_days") and (end - start).days + 1 > config["max_days"]:
            raise AnswerError(f"intervalle limite a {config['max_days']} jour(s)")

        return {"start": start.isoformat(), "end": end.isoformat()}

    def is_answered(self, value) -> bool:
        return bool(value) and bool(value.get("start")) and bool(value.get("end"))

    def comparable(self, question, value):
        if not self.is_answered(value):
            return None
        return [value["start"], value["end"]]

    def evaluate(self, question, value) -> tuple[float, dict]:
        if not self.has_expected(question):
            return 0.0, {"graded": False}
        if not self.is_answered(value):
            return 0.0, {"graded": True, "ratio": 0.0}

        for rule in question.expected_config["rules"]:
            if rule.get("type") == "exact":
                if value["start"] == rule.get("start") and value["end"] == rule.get("end"):
                    return 1.0, {"graded": True, "ratio": 1.0}
            elif rule.get("type") == "range":
                low  = rule.get("min")
                high = rule.get("max")
                if (low is None or value["start"] >= low) and (high is None or value["end"] <= high):
                    return 1.0, {"graded": True, "ratio": 1.0}
        return 0.0, {"graded": True, "ratio": 0.0}

    def display(self, question, value, snapshot = None) -> str:
        return f"{value['start']} -> {value['end']}" if self.is_answered(value) else ""

class VocabularyType(QuestionType):
    """Type dont les reponses proviennent d'un vocabulaire controle."""

    family         = c.FAMILY_STRUCTURED
    expected_kinds = ("exact", "one_of")
    key            = "value"
    widget         = "vocabulary"

    def vocabulary(self, question) -> dict:
        """{code: libelle} des valeurs acceptees."""
        raise NotImplementedError

    def normalize_answer(self, question, raw) -> dict | None:
        if raw is None or raw == "":
            return None
        if isinstance(raw, dict):
            raw = raw.get(self.key, raw.get("value"))
            if raw in (None, ""):
                return None
        code = str(raw)
        if code not in self.vocabulary(question):
            raise AnswerError(f"valeur hors vocabulaire pour {self.id}: {code!r}")
        return {self.key: code}

    def is_answered(self, value) -> bool:
        return bool(value) and value.get(self.key) not in (None, "")

    def comparable(self, question, value):
        return value[self.key] if self.is_answered(value) else None

    def display(self, question, value, snapshot = None) -> str:
        if not self.is_answered(value):
            return ""
        return self.vocabulary(question).get(value[self.key], value[self.key])

@register
class CountryType(VocabularyType):
    id    = c.TYPE_COUNTRY
    label = "Pays"
    key   = "country"

    expected_help = "Choisissez le ou les pays acceptes."
    hint    = "Un pays, choisi dans la liste officielle ISO."
    example = "Dans quel pays exercez-vous ?"

    def config_fields(self) -> list[dict]:
        return [field(
            "allowed", "Restreindre a certains pays", "countries",
            help = "Laissez vide pour proposer les 249 pays. Sinon, seuls les pays "
                   "choisis seront proposes au participant.",
        )]

    def validate_config(self, config: dict) -> dict:
        config  = dict(config or {})
        allowed = config.get("allowed") or []
        unknown = [code for code in allowed if code not in COUNTRY_CODES]
        if unknown:
            raise ConfigError(f"codes pays inconnus: {unknown}")
        return config

    def value_choices(self) -> list:
        return [[code, name] for code, name in COUNTRY_NAMES.items()]

    def vocabulary(self, question) -> dict:
        allowed = (question.config or {}).get("allowed") or []
        if allowed:
            return {code: COUNTRY_NAMES[code] for code in allowed}
        return dict(COUNTRY_NAMES)

@register
class CityType(VocabularyType):
    """Ville : vocabulaire obligatoirement declare dans la configuration.

    Il n'existe volontairement pas de saisie libre : l'administrateur fournit
    la liste des villes acceptees.
    """

    id    = c.TYPE_CITY
    label = "Ville"
    key   = "city"

    expected_help = "Choisissez la ou les villes acceptees."
    hint    = "Une ville, choisie dans une liste que vous definissez."
    example = "Sur quel site travaillez-vous ? -> Paris, Lyon, Marseille"

    def config_fields(self) -> list[dict]:
        return [field(
            "cities", "Villes proposees", "cities",
            help = "Obligatoire : il n'y a pas de saisie libre. Le participant choisira "
                   "dans cette liste.",
            example = "Paris, Lyon, Marseille",
        )]

    def validate_config(self, config: dict) -> dict:
        config = dict(config or {})
        cities = config.get("cities") or []
        if not cities:
            raise ConfigError("le type ville exige une liste `cities` non vide")
        normalized = []
        for city in cities:
            if isinstance(city, str):
                city = {"code": city, "name": city}
            if not city.get("code") or not city.get("name"):
                raise ConfigError("chaque ville doit avoir un `code` et un `name`")
            if city.get("country") and city["country"] not in COUNTRY_CODES:
                raise ConfigError(f"pays inconnu pour la ville {city['code']!r}")
            normalized.append(city)
        config["cities"] = normalized
        return config

    def vocabulary(self, question) -> dict:
        return {c_["code"]: c_["name"] for c_ in (question.config or {}).get("cities", [])}

@register
class YearType(NumericType):
    id             = c.TYPE_YEAR
    family         = c.FAMILY_STRUCTURED
    label          = "Annee"
    integer_only   = True
    hint    = "Une annee."
    example = "En quelle annee avez-vous commence ?"

    def validate_config(self, config: dict) -> dict:
        config = dict(config or {})
        config.setdefault("min", "1900")
        config.setdefault("max", "2200")
        return NumericType.validate_config(self, config)

    def display(self, question, value, snapshot = None) -> str:
        return value["number"] if self.is_answered(value) else ""

class OrdinalType(VocabularyType):

    entries: tuple = ()

    def config_fields(self) -> list[dict]:
        return []

    def value_choices(self) -> list:
        return [[str(code), label] for code, label in self.entries]

    def vocabulary(self, question) -> dict:
        return {str(code): label for code, label in self.entries}

    def comparable(self, question, value):
        code = VocabularyType.comparable(self, question, value)
        return None if code is None else int(code)

    def normalize_answer(self, question, raw) -> dict | None:
        if isinstance(raw, (int, float)) and not isinstance(raw, bool):
            raw = str(_as_int(raw))
        return VocabularyType.normalize_answer(self, question, raw)

@register
class MonthType(OrdinalType):
    id      = c.TYPE_MONTH
    label   = "Mois"
    key     = "month"
    entries = (
        (1, "Janvier"),   (2, "Fevrier"),  (3, "Mars"),      (4, "Avril"),
        (5, "Mai"),       (6, "Juin"),     (7, "Juillet"),   (8, "Aout"),
        (9, "Septembre"), (10, "Octobre"), (11, "Novembre"), (12, "Decembre"),
    )
    hint    = "Un mois de l'annee."
    example = "Quel mois preferez-vous pour vos conges ?"

@register
class WeekdayType(OrdinalType):
    id      = c.TYPE_WEEKDAY
    label   = "Jour de la semaine"
    key     = "weekday"
    entries = (
        (0, "Lundi"),    (1, "Mardi"),  (2, "Mercredi"), (3, "Jeudi"),
        (4, "Vendredi"), (5, "Samedi"), (6, "Dimanche"),
    )
    hint    = "Un jour de la semaine."
    example = "Quel jour de la semaine vous arrange le mieux ?"

@register
class AddressType(QuestionType):
    """Adresse structuree.

    Chaque composant est valide separement : le pays et la ville proviennent
    d'un vocabulaire controle, le code postal d'une expression reguliere, et le
    libelle de voie n'est accepte que si la configuration l'autorise
    explicitement, avec une longueur et un motif imposes. Il n'y a donc jamais
    de champ de saisie libre non contraint.
    """

    id             = c.TYPE_ADDRESS
    family         = c.FAMILY_STRUCTURED
    label          = "Adresse structuree"
    widget         = "address"
    expected_kinds = ("exact",)

    DEFAULT_STREET_PATTERN = r"^[0-9A-Za-zÀ-ÿ' \-.]{1,120}$"
    DEFAULT_POSTAL_PATTERN = r"^[0-9A-Za-z \-]{2,12}$"

    expected_help = "Renseignez l'adresse exacte attendue, champ par champ."

    def rule_fields(self, kind: str) -> list[dict]:
        return [
            {"path": "value.street_number", "label": "numero",      "input": "number"},
            {"path": "value.street",        "label": "voie",        "input": "text"},
            {"path": "value.postal_code",   "label": "code postal", "input": "text"},
            {"path": "value.city",          "label": "ville",       "input": "text"},
            {"path": "value.country",       "label": "pays",        "input": "text"},
        ]
    hint    = "Une adresse decomposee en champs valides separement."
    example = "Quelle est l'adresse du site concerne ?"

    def config_fields(self) -> list[dict]:
        return [
            field("countries", "Restreindre a certains pays", "countries",
                  help = "Laissez vide pour proposer tous les pays."),
            field("cities", "Villes proposees", "cities",
                  help = "Si vous renseignez une liste, la ville devient un menu deroulant "
                         "au lieu d'un champ de saisie."),
            field("allow_street_text", "Autoriser la saisie du nom de voie", "bool",
                  default = True,
                  help = "Decochez pour n'accepter que numero, code postal, ville et pays."),
            field("street_max_length", "Longueur maximale du nom de voie", "int",
                  default = 120, example = "120"),
            field("required_fields", "Champs obligatoires", "select-multi",
                  choices = ["country", "city", "postal_code", "street_number", "street"],
                  default = ["country", "city", "postal_code"],
                  help = "Une adresse incomplete sur ces champs sera refusee."),
        ]

    def validate_config(self, config: dict) -> dict:
        import re

        config  = dict(config or {})
        unknown = [c_ for c_ in (config.get("countries") or []) if c_ not in COUNTRY_CODES]
        if unknown:
            raise ConfigError(f"codes pays inconnus: {unknown}")

        for key, default in (
            ("postal_pattern", self.DEFAULT_POSTAL_PATTERN),
            ("street_pattern", self.DEFAULT_STREET_PATTERN),
        ):
            pattern = config.get(key) or default
            try:
                re.compile(pattern)
            except re.error as exc:
                raise ConfigError(f"{key} invalide: {exc}")
            config[key] = pattern

        config["street_max_length"]  = _as_int(config.get("street_max_length", 120), "street_max_length")
        config["allow_street_text"]  = bool(config.get("allow_street_text", True))
        config.setdefault("required_fields", ["country", "city", "postal_code"])
        return config

    def normalize_answer(self, question, raw) -> dict | None:
        import re

        if not raw:
            return None
        if not isinstance(raw, dict):
            raise AnswerError("une adresse attend un objet structure")

        config = question.config or {}
        value  = {}

        country = raw.get("country")
        if country:
            allowed = config.get("countries") or []
            if country not in COUNTRY_CODES or (allowed and country not in allowed):
                raise AnswerError(f"pays invalide: {country!r}")
            value["country"] = country

        city = raw.get("city")
        if city:
            cities = {c_["code"] for c_ in (config.get("cities") or [])}
            if cities and city not in cities:
                raise AnswerError(f"ville hors vocabulaire: {city!r}")
            if not cities and not re.match(config.get("street_pattern", self.DEFAULT_STREET_PATTERN), str(city)):
                raise AnswerError(f"ville invalide: {city!r}")
            value["city"] = str(city)

        postal = raw.get("postal_code")
        if postal:
            if not re.match(config.get("postal_pattern", self.DEFAULT_POSTAL_PATTERN), str(postal)):
                raise AnswerError(f"code postal invalide: {postal!r}")
            value["postal_code"] = str(postal)

        number = raw.get("street_number")
        if number not in (None, ""):
            value["street_number"] = _as_int(number, "street_number")

        street = raw.get("street")
        if street:
            if not config.get("allow_street_text", True):
                raise AnswerError("le libelle de voie n'est pas accepte pour cette question")
            street = str(street)
            if len(street) > config.get("street_max_length", 120):
                raise AnswerError("libelle de voie trop long")
            if not re.match(config.get("street_pattern", self.DEFAULT_STREET_PATTERN), street):
                raise AnswerError("libelle de voie invalide")
            value["street"] = street

        if not value:
            return None

        missing = [f for f in config.get("required_fields", []) if not value.get(f)]
        if missing:
            raise AnswerError(f"champs d'adresse manquants: {missing}")
        return value

    def is_answered(self, value) -> bool:
        return bool(value)

    def comparable(self, question, value):
        if not value:
            return None
        parts = (
            value.get("street_number"), value.get("street"), value.get("postal_code"),
            value.get("city"), value.get("country"),
        )
        return " ".join(str(p) for p in parts if p not in (None, ""))

    def evaluate(self, question, value) -> tuple[float, dict]:
        if not self.has_expected(question):
            return 0.0, {"graded": False}
        for rule in question.expected_config["rules"]:
            expected = rule.get("value") or {}
            if all(str(value.get(k, "")) == str(v) for k, v in expected.items()):
                return 1.0, {"graded": True, "ratio": 1.0}
        return 0.0, {"graded": True, "ratio": 0.0}

    def display(self, question, value, snapshot = None) -> str:
        return self.comparable(question, value) or ""
