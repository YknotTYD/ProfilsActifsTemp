##question_types.py
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


def catalog() -> list[dict]:
    """Description du catalogue, consommee par l'editeur d'administration."""
    return [
        {
            "id":           t.id,
            "family":       t.family,
            "label":        t.label,
            "uses_options": t.uses_options,
            "multiple":     t.multiple,
            "config_schema": t.config_schema(),
            "expected_kinds": list(t.expected_kinds),
        }
        for t in _REGISTRY.values()
    ]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

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


# --------------------------------------------------------------------------- #
# Classe de base
# --------------------------------------------------------------------------- #

class QuestionType:

    id           = ""
    family       = ""
    label        = ""
    uses_options = False   # la question porte-t-elle des QuestionOption ?
    multiple     = False   # plusieurs options selectionnables ?
    expected_kinds: tuple = ()   # regles de reponse attendue supportees

    # -- administration ---------------------------------------------------- #

    def config_schema(self) -> dict:
        """Champs de configuration acceptes, pour l'editeur."""
        return {}

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

    # -- utilisation ------------------------------------------------------- #

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


# --------------------------------------------------------------------------- #
# Famille : choix
# --------------------------------------------------------------------------- #

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

    def config_schema(self) -> dict:
        schema = {"shuffle_options": "bool"}
        if self.multiple:
            schema |= {
                "min_selected":      "int?",
                "max_selected":      "int?",
                "penalty_per_wrong": "float",
            }
        return schema

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


@register
class MultipleChoice(ChoiceType):
    id       = c.TYPE_MULTIPLE_CHOICE
    label    = "Choix multiple"
    multiple = True


@register
class Checkbox(ChoiceType):
    id       = c.TYPE_CHECKBOX
    label    = "Cases a cocher"
    multiple = True


@register
class Dropdown(ChoiceType):
    id    = c.TYPE_DROPDOWN
    label = "Liste deroulante"


@register
class MultiSelect(ChoiceType):
    id       = c.TYPE_MULTI_SELECT
    label    = "Liste multi-selection"
    multiple = True


class FixedChoiceType(ChoiceType):
    """Type a options imposees : les options sont creees automatiquement."""

    fixed_options: tuple = ()

    def config_schema(self) -> dict:
        return {}


@register
class YesNo(FixedChoiceType):
    id            = c.TYPE_YES_NO
    label         = "Oui / Non"
    fixed_options = (("yes", "Oui"), ("no", "Non"))


@register
class TrueFalse(FixedChoiceType):
    id            = c.TYPE_TRUE_FALSE
    label         = "Vrai / Faux"
    fixed_options = (("true", "Vrai"), ("false", "Faux"))


@register
class Scale(ChoiceType):
    """Echelle / notation.

    Les options portent la valeur numerique de l'echelon, ce qui permet a la
    fois une comparaison par identifiant et une condition numerique.
    """

    id             = c.TYPE_SCALE
    label          = "Echelle / notation"
    expected_kinds = ("combination", "exact", "one_of", "range", "min", "max")

    def config_schema(self) -> dict:
        return {"min": "int", "max": "int", "step": "int", "labels": "dict?"}

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


# --------------------------------------------------------------------------- #
# Famille : valeurs numeriques
# --------------------------------------------------------------------------- #

class NumericType(QuestionType):
    """Base des types numeriques.

    Valeur canonique : {"number": "21.5", "unit": "C"}
    Le nombre est stocke en chaine pour rester exact (Decimal) en JSON.
    """

    family         = c.FAMILY_NUMERIC
    expected_kinds = ("exact", "one_of", "range", "min", "max")
    integer_only   = False
    units: tuple   = ()
    default_unit   = None

    def config_schema(self) -> dict:
        schema = {"min": "number?", "max": "number?"}
        if not self.integer_only:
            schema["decimals"] = "int?"
        if self.units:
            schema["unit"]       = f"one of {list(self.units)}"
            schema["allow_unit_choice"] = "bool"
        return schema

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


@register
class DecimalType(NumericType):
    id    = c.TYPE_DECIMAL
    label = "Nombre decimal"


@register
class PercentageType(NumericType):
    id           = c.TYPE_PERCENTAGE
    label        = "Pourcentage"
    units        = ("%",)
    default_unit = "%"

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


@register
class DistanceType(NumericType):
    id           = c.TYPE_DISTANCE
    label        = "Distance"
    units        = ("mm", "cm", "m", "km", "mi")
    default_unit = "m"


@register
class WeightType(NumericType):
    id           = c.TYPE_WEIGHT
    label        = "Poids"
    units        = ("g", "kg", "t", "lb")
    default_unit = "kg"


@register
class HeightType(NumericType):
    id           = c.TYPE_HEIGHT
    label        = "Taille"
    units        = ("cm", "m", "in", "ft")
    default_unit = "cm"


@register
class SpeedType(NumericType):
    id           = c.TYPE_SPEED
    label        = "Vitesse"
    units        = ("km/h", "m/s", "mph", "kn")
    default_unit = "km/h"


@register
class DurationType(NumericType):
    id           = c.TYPE_DURATION
    label        = "Duree"
    units        = ("s", "min", "h", "d")
    default_unit = "min"


# --------------------------------------------------------------------------- #
# Famille : date et temps
# --------------------------------------------------------------------------- #

class TemporalType(QuestionType):

    family         = c.FAMILY_TEMPORAL
    expected_kinds = ("exact", "one_of", "range", "min", "max")
    key            = "value"

    def parse(self, raw: str):
        raise NotImplementedError

    def format(self, parsed) -> str:
        return parsed.isoformat()

    def config_schema(self) -> dict:
        return {"min": "iso?", "max": "iso?"}

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
    expected_kinds = ("exact", "range")

    def config_schema(self) -> dict:
        return {"min": "iso?", "max": "iso?", "max_days": "int?"}

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


# --------------------------------------------------------------------------- #
# Famille : valeurs structurees
# --------------------------------------------------------------------------- #

class VocabularyType(QuestionType):
    """Type dont les reponses proviennent d'un vocabulaire controle."""

    family         = c.FAMILY_STRUCTURED
    expected_kinds = ("exact", "one_of")
    key            = "value"

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

    def config_schema(self) -> dict:
        return {"allowed": "list of ISO 3166-1 alpha-2 codes (optionnel)"}

    def validate_config(self, config: dict) -> dict:
        config  = dict(config or {})
        allowed = config.get("allowed") or []
        unknown = [code for code in allowed if code not in COUNTRY_CODES]
        if unknown:
            raise ConfigError(f"codes pays inconnus: {unknown}")
        return config

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

    def config_schema(self) -> dict:
        return {"cities": "list of {code, name, country?} (obligatoire)"}

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

    def validate_config(self, config: dict) -> dict:
        config = dict(config or {})
        config.setdefault("min", "1900")
        config.setdefault("max", "2200")
        return NumericType.validate_config(self, config)

    def display(self, question, value, snapshot = None) -> str:
        return value["number"] if self.is_answered(value) else ""


class OrdinalType(VocabularyType):

    entries: tuple = ()

    def config_schema(self) -> dict:
        return {}

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


@register
class WeekdayType(OrdinalType):
    id      = c.TYPE_WEEKDAY
    label   = "Jour de la semaine"
    key     = "weekday"
    entries = (
        (0, "Lundi"),    (1, "Mardi"),  (2, "Mercredi"), (3, "Jeudi"),
        (4, "Vendredi"), (5, "Samedi"), (6, "Dimanche"),
    )


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
    expected_kinds = ("exact",)

    DEFAULT_STREET_PATTERN = r"^[0-9A-Za-zÀ-ÿ' \-.]{1,120}$"
    DEFAULT_POSTAL_PATTERN = r"^[0-9A-Za-z \-]{2,12}$"

    def config_schema(self) -> dict:
        return {
            "countries":        "list of ISO codes (optionnel)",
            "cities":           "list of {code, name} (optionnel)",
            "postal_pattern":   "regex",
            "allow_street_text": "bool",
            "street_max_length": "int",
            "street_pattern":    "regex",
            "required_fields":   "list of field names",
        }

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
