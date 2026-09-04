"""Vocabulaire partagé du systeme de questionnaires.

Tout ce qui est un "choix" (statut, type, operateur...) est declare ici sous
forme de tuple de couples afin de rester utilisable directement dans les
`choices` Django et dans les validations d'API.
"""

STATUS_DRAFT       = "DRAFT"
STATUS_TEST        = "TEST"
STATUS_PUBLISHED   = "PUBLISHED"
STATUS_DISABLED    = "DISABLED"
STATUS_ARCHIVED    = "ARCHIVED"
STATUS_INVALIDATED = "INVALIDATED"

QUESTIONNAIRE_STATUSES = (
    (STATUS_DRAFT,       "Brouillon"),
    (STATUS_TEST,        "Test"),
    (STATUS_PUBLISHED,   "Publie"),
    (STATUS_DISABLED,    "Desactive"),
    (STATUS_ARCHIVED,    "Archive"),
    (STATUS_INVALIDATED, "Invalide"),
)

VERSION_STATUSES = QUESTIONNAIRE_STATUSES

LOCKED_VERSION_STATUSES = (
    STATUS_TEST,
    STATUS_PUBLISHED,
    STATUS_DISABLED,
    STATUS_ARCHIVED,
    STATUS_INVALIDATED,
)

CLOSED_VERSION_STATUSES = (
    STATUS_DISABLED,
    STATUS_ARCHIVED,
    STATUS_INVALIDATED,
)

ATTEMPT_IN_PROGRESS = "IN_PROGRESS"
ATTEMPT_COMPLETED   = "COMPLETED"
ATTEMPT_ABANDONED   = "ABANDONED"
ATTEMPT_EXPIRED     = "EXPIRED"
ATTEMPT_INVALIDATED = "INVALIDATED"

ATTEMPT_STATUSES = (
    (ATTEMPT_IN_PROGRESS, "En cours"),
    (ATTEMPT_COMPLETED,   "Terminee"),
    (ATTEMPT_ABANDONED,   "Abandonnee"),
    (ATTEMPT_EXPIRED,     "Expiree"),
    (ATTEMPT_INVALIDATED, "Invalidee"),
)

FINAL_ATTEMPT_STATUSES = (
    ATTEMPT_COMPLETED,
    ATTEMPT_ABANDONED,
    ATTEMPT_EXPIRED,
    ATTEMPT_INVALIDATED,
)

FAMILY_CHOICE     = "choice"
FAMILY_NUMERIC    = "numeric"
FAMILY_TEMPORAL   = "temporal"
FAMILY_STRUCTURED = "structured"

QUESTION_FAMILIES = (
    (FAMILY_CHOICE,     "Choix"),
    (FAMILY_NUMERIC,    "Valeur numerique"),
    (FAMILY_TEMPORAL,   "Date et temps"),
    (FAMILY_STRUCTURED, "Valeur structuree"),
)

TYPE_SINGLE_CHOICE   = "single_choice"
TYPE_MULTIPLE_CHOICE = "multiple_choice"
TYPE_CHECKBOX        = "checkbox"
TYPE_YES_NO          = "yes_no"
TYPE_TRUE_FALSE      = "true_false"
TYPE_DROPDOWN        = "dropdown"
TYPE_MULTI_SELECT    = "multi_select"
TYPE_SCALE           = "scale"

TYPE_INTEGER     = "integer"
TYPE_DECIMAL     = "decimal"
TYPE_PERCENTAGE  = "percentage"
TYPE_TEMPERATURE = "temperature"
TYPE_DISTANCE    = "distance"
TYPE_WEIGHT      = "weight"
TYPE_HEIGHT      = "height"
TYPE_SPEED       = "speed"
TYPE_DURATION    = "duration"

TYPE_DATE        = "date"
TYPE_TIME        = "time"
TYPE_DATETIME    = "datetime"
TYPE_HOUR_MINUTE = "hour_minute"
TYPE_DATE_RANGE  = "date_range"

TYPE_COUNTRY = "country"
TYPE_CITY    = "city"
TYPE_YEAR    = "year"
TYPE_MONTH   = "month"
TYPE_WEEKDAY = "weekday"
TYPE_ADDRESS = "address"

RULE_KIND_ACCESS     = "ACCESS"
RULE_KIND_VISIBILITY = "VISIBILITY"

RULE_KINDS = (
    (RULE_KIND_ACCESS,     "Accessibilite"),
    (RULE_KIND_VISIBILITY, "Visibilite"),
)

RULE_EVERYONE = "EVERYONE"
RULE_USER     = "USER"
RULE_ROLE     = "ROLE"
RULE_BADGE    = "BADGE"

RULE_TYPES = (
    (RULE_EVERYONE, "Tout le monde"),
    (RULE_USER,     "Utilisateur"),
    (RULE_ROLE,     "Role"),
    (RULE_BADGE,    "Badge"),
)

ANSWERS_FREE                = "FREE"
ANSWERS_UNTIL_FINISH        = "UNTIL_FINISH"
ANSWERS_LOCKED_ON_VALIDATE  = "LOCKED_ON_VALIDATE"

ANSWER_EDIT_MODES = (
    (ANSWERS_FREE,               "Modifiables librement"),
    (ANSWERS_UNTIL_FINISH,       "Modifiables jusqu'a la fin de la tentative"),
    (ANSWERS_LOCKED_ON_VALIDATE, "Verrouillees des validation"),
)

NAVIGATION_FREE   = "FREE"
NAVIGATION_LINEAR = "LINEAR"

NAVIGATION_MODES = (
    (NAVIGATION_FREE,   "Navigation libre"),
    (NAVIGATION_LINEAR, "Lineaire"),
)

OP_EQUALS       = "EQUALS"
OP_NOT_EQUALS   = "NOT_EQUALS"
OP_CONTAINS     = "CONTAINS"
OP_NOT_CONTAINS = "NOT_CONTAINS"
OP_GT           = "GT"
OP_LT           = "LT"
OP_GTE          = "GTE"
OP_LTE          = "LTE"
OP_ANSWERED     = "ANSWERED"
OP_NOT_ANSWERED = "NOT_ANSWERED"

CONDITION_OPERATORS = (
    OP_EQUALS, OP_NOT_EQUALS,
    OP_CONTAINS, OP_NOT_CONTAINS,
    OP_GT, OP_LT, OP_GTE, OP_LTE,
    OP_ANSWERED, OP_NOT_ANSWERED,
)

LOGIC_AND = "AND"
LOGIC_OR  = "OR"
LOGIC_OPERATORS = (LOGIC_AND, LOGIC_OR)

PARTIAL_PROPORTIONAL   = "proportional"
PARTIAL_ALL_OR_NOTHING = "all_or_nothing"
PARTIAL_THRESHOLD      = "threshold"

PARTIAL_MODES = (PARTIAL_PROPORTIONAL, PARTIAL_ALL_OR_NOTHING, PARTIAL_THRESHOLD)

DEFAULT_QUESTION_SCORING = {
    "weight":            1.0,
    "correct_score":     1.0,
    "incorrect_score":   0.0,
    "unanswered_score":  0.0,
    "partial":           True,
    "partial_mode":      PARTIAL_PROPORTIONAL,
    "partial_threshold": 0.5,
}

DEFAULT_VERSION_SCORING = {
    "pass_threshold_percent": 60.0,
    "floor_negative":         True,
    "levels":                 [],
}

DEFAULT_RESULT_VISIBILITY = {
    "show_score":            True,
    "show_percentage":       True,
    "show_pass_fail":        True,
    "show_user_answers":     True,
    "show_correct_answers":  False,
    "show_incorrect_answers": False,
    "show_explanations":     False,
    "show_badge":            False,
}

AUDIT_CREATE          = "CREATE"
AUDIT_UPDATE          = "UPDATE"
AUDIT_DELETE          = "DELETE"
AUDIT_PUBLISH         = "PUBLISH"
AUDIT_INVALIDATE      = "INVALIDATE"
AUDIT_ARCHIVE         = "ARCHIVE"
AUDIT_DISABLE         = "DISABLE"
AUDIT_RESTORE         = "RESTORE"
AUDIT_DUPLICATE       = "DUPLICATE"
AUDIT_VERSION_CREATE  = "VERSION_CREATE"
AUDIT_ACCESS_CHANGE   = "ACCESS_CHANGE"
AUDIT_QUESTION_CHANGE = "QUESTION_CHANGE"
AUDIT_OPTION_CHANGE   = "OPTION_CHANGE"
AUDIT_SCORING_CHANGE  = "SCORING_CHANGE"
AUDIT_TEST_MODE       = "TEST_MODE"
AUDIT_BADGE_AWARD     = "BADGE_AWARD"

AUDIT_ACTIONS = tuple(
    (a, a) for a in (
        AUDIT_CREATE, AUDIT_UPDATE, AUDIT_DELETE, AUDIT_PUBLISH,
        AUDIT_INVALIDATE, AUDIT_ARCHIVE, AUDIT_DISABLE, AUDIT_RESTORE,
        AUDIT_DUPLICATE, AUDIT_VERSION_CREATE, AUDIT_ACCESS_CHANGE,
        AUDIT_QUESTION_CHANGE, AUDIT_OPTION_CHANGE, AUDIT_SCORING_CHANGE,
        AUDIT_TEST_MODE, AUDIT_BADGE_AWARD,
    )
)

BADGE_SOURCE_RESULT = "QUESTIONNAIRE_RESULT"
BADGE_SOURCE_MANUAL = "MANUAL"
BADGE_SOURCE_SYSTEM = "SYSTEM"

BADGE_SOURCES = (
    (BADGE_SOURCE_RESULT, "Resultat de questionnaire"),
    (BADGE_SOURCE_MANUAL, "Attribution manuelle"),
    (BADGE_SOURCE_SYSTEM, "Systeme"),
)

PERM_CREATE       = "questionnaires.add_questionnaire"
PERM_UPDATE       = "questionnaires.change_questionnaire"
PERM_DELETE       = "questionnaires.delete_questionnaire"
PERM_VIEW         = "questionnaires.view_questionnaire"
PERM_PUBLISH      = "questionnaires.publish_questionnaire"
PERM_ARCHIVE      = "questionnaires.archive_questionnaire"
PERM_INVALIDATE   = "questionnaires.invalidate_questionnaire"
PERM_TEST         = "questionnaires.test_questionnaire"
PERM_MANAGE_VERSIONS = "questionnaires.manage_versions"
PERM_MANAGE_ACCESS   = "questionnaires.manage_access"
PERM_VIEW_ATTEMPTS   = "questionnaires.view_attempts"
PERM_VIEW_RESULTS    = "questionnaires.view_results"
PERM_VIEW_STATS      = "questionnaires.view_statistics"
PERM_MANAGE_BADGES   = "questionnaires.manage_badges"
