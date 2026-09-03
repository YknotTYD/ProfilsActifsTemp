##constants.py
"""Vocabulaire partage des profils professionnels.

Meme principe que `questionnaires/constants.py` : tout ce qui est un "choix"
est declare ici sous forme de tuple de couples, directement utilisable dans les
`choices` Django et dans la validation d'API.

Les echelles ordonnees (niveau de competence, niveau de langue, niveau de
diplome, ouverture d'une visibilite) sont doublees d'un dictionnaire de rangs.
C'est ce rang, stocke en base a cote du libelle, qui rend les comparaisons
possibles en SQL : `level_rank >= 3` s'indexe, `level >= "ADVANCED"` non.
Allonger une echelle revient donc a ajouter une constante et un rang, jamais a
migrer des donnees.
"""

# --------------------------------------------------------------------------- #
# Niveaux de competence (section 4)
# --------------------------------------------------------------------------- #

LEVEL_BEGINNER     = "BEGINNER"
LEVEL_INTERMEDIATE = "INTERMEDIATE"
LEVEL_ADVANCED     = "ADVANCED"
LEVEL_EXPERT       = "EXPERT"

SKILL_LEVELS = (
    (LEVEL_BEGINNER,     "Debutant"),
    (LEVEL_INTERMEDIATE, "Intermediaire"),
    (LEVEL_ADVANCED,     "Avance"),
    (LEVEL_EXPERT,       "Expert"),
)

#: rang de chaque niveau, seul ordre qui fasse foi
SKILL_LEVEL_RANKS = {
    LEVEL_BEGINNER:     1,
    LEVEL_INTERMEDIATE: 2,
    LEVEL_ADVANCED:     3,
    LEVEL_EXPERT:       4,
}

MAX_SKILL_LEVEL_RANK = max(SKILL_LEVEL_RANKS.values())


def skill_level_rank(level: str) -> int:
    """Rang d'un niveau ; 0 pour un niveau inconnu ou absent."""
    return SKILL_LEVEL_RANKS.get(level, 0)


# --------------------------------------------------------------------------- #
# Categories de competences
# --------------------------------------------------------------------------- #

SKILL_CATEGORY_LANGUAGE  = "LANGUAGE"
SKILL_CATEGORY_FRAMEWORK = "FRAMEWORK"
SKILL_CATEGORY_TOOL      = "TOOL"
SKILL_CATEGORY_DATABASE  = "DATABASE"
SKILL_CATEGORY_CLOUD     = "CLOUD"
SKILL_CATEGORY_METHOD    = "METHOD"
SKILL_CATEGORY_SOFT      = "SOFT"
SKILL_CATEGORY_OTHER     = "OTHER"

SKILL_CATEGORIES = (
    (SKILL_CATEGORY_LANGUAGE,  "Langage"),
    (SKILL_CATEGORY_FRAMEWORK, "Framework"),
    (SKILL_CATEGORY_TOOL,      "Outil"),
    (SKILL_CATEGORY_DATABASE,  "Base de donnees"),
    (SKILL_CATEGORY_CLOUD,     "Cloud et infrastructure"),
    (SKILL_CATEGORY_METHOD,    "Methode"),
    (SKILL_CATEGORY_SOFT,      "Savoir-etre"),
    (SKILL_CATEGORY_OTHER,     "Autre"),
)


# --------------------------------------------------------------------------- #
# Domaines professionnels (sections 2 et 12)
# --------------------------------------------------------------------------- #

FIELD_SOFTWARE       = "SOFTWARE"
FIELD_DATA           = "DATA"
FIELD_INFRASTRUCTURE = "INFRASTRUCTURE"
FIELD_SECURITY       = "SECURITY"
FIELD_DESIGN         = "DESIGN"
FIELD_PRODUCT        = "PRODUCT"
FIELD_MARKETING      = "MARKETING"
FIELD_SALES          = "SALES"
FIELD_FINANCE        = "FINANCE"
FIELD_HR             = "HR"
FIELD_LEGAL          = "LEGAL"
FIELD_HEALTH         = "HEALTH"
FIELD_EDUCATION      = "EDUCATION"
FIELD_INDUSTRY       = "INDUSTRY"
FIELD_LOGISTICS      = "LOGISTICS"
FIELD_HOSPITALITY    = "HOSPITALITY"
FIELD_OTHER          = "OTHER"

PROFESSIONAL_FIELDS = (
    (FIELD_SOFTWARE,       "Developpement logiciel"),
    (FIELD_DATA,           "Donnees et IA"),
    (FIELD_INFRASTRUCTURE, "Infrastructure et systemes"),
    (FIELD_SECURITY,       "Cybersecurite"),
    (FIELD_DESIGN,         "Design"),
    (FIELD_PRODUCT,        "Produit et gestion de projet"),
    (FIELD_MARKETING,      "Marketing et communication"),
    (FIELD_SALES,          "Commerce et vente"),
    (FIELD_FINANCE,        "Finance et comptabilite"),
    (FIELD_HR,             "Ressources humaines"),
    (FIELD_LEGAL,          "Juridique"),
    (FIELD_HEALTH,         "Sante"),
    (FIELD_EDUCATION,      "Enseignement et formation"),
    (FIELD_INDUSTRY,       "Industrie et ingenierie"),
    (FIELD_LOGISTICS,      "Transport et logistique"),
    (FIELD_HOSPITALITY,    "Hotellerie et restauration"),
    (FIELD_OTHER,          "Autre"),
)


# --------------------------------------------------------------------------- #
# Couleur de banniere du profil
# --------------------------------------------------------------------------- #
#: choix simple d'une teinte plutot qu'une image : pas d'hebergement de
#: fichiers, et une bannière lisible sans URL a fournir. La valeur est le nom
#: du degrade, tenu a jour dans `static/profiles.css` (`.p-cover[data-cover]`).

COVER_NAVY   = "navy"
COVER_OCRE   = "ocre"
COVER_TEAL   = "teal"
COVER_FOREST = "forest"
COVER_PURPLE = "purple"
COVER_ROSE   = "rose"
COVER_SKY    = "sky"
COVER_SUNSET = "sunset"
COVER_SLATE  = "slate"
COVER_INDIGO = "indigo"

COVER_COLORS = (
    (COVER_NAVY,   "Marine"),
    (COVER_OCRE,   "Ocre"),
    (COVER_TEAL,   "Sarcelle"),
    (COVER_FOREST, "Foret"),
    (COVER_PURPLE, "Violet"),
    (COVER_ROSE,   "Rose"),
    (COVER_SKY,    "Ciel"),
    (COVER_SUNSET, "Coucher de soleil"),
    (COVER_SLATE,  "Ardoise"),
    (COVER_INDIGO, "Indigo"),
)

DEFAULT_COVER_COLOR = COVER_NAVY


# --------------------------------------------------------------------------- #
# Disponibilite et recherche d'emploi (section 10)
# --------------------------------------------------------------------------- #

AVAILABILITY_OPEN_TO_WORK          = "OPEN_TO_WORK"
AVAILABILITY_OPEN_TO_OPPORTUNITIES = "OPEN_TO_OPPORTUNITIES"
AVAILABILITY_CURRENTLY_EMPLOYED    = "CURRENTLY_EMPLOYED"
AVAILABILITY_NOT_LOOKING           = "NOT_LOOKING"

AVAILABILITY_STATUSES = (
    (AVAILABILITY_OPEN_TO_WORK,          "En recherche active"),
    (AVAILABILITY_OPEN_TO_OPPORTUNITIES, "Ouvert aux opportunites"),
    (AVAILABILITY_CURRENTLY_EMPLOYED,    "En poste"),
    (AVAILABILITY_NOT_LOOKING,           "Pas en recherche"),
)

#: statuts consideres comme "disponible" par le filtre `available = true`
AVAILABLE_STATUSES = (
    AVAILABILITY_OPEN_TO_WORK,
    AVAILABILITY_OPEN_TO_OPPORTUNITIES,
)

CONTRACT_CDI            = "CDI"
CONTRACT_CDD            = "CDD"
CONTRACT_INTERNSHIP     = "INTERNSHIP"
CONTRACT_APPRENTICESHIP = "APPRENTICESHIP"
CONTRACT_FREELANCE      = "FREELANCE"
CONTRACT_PART_TIME      = "PART_TIME"
CONTRACT_TEMPORARY      = "TEMPORARY"
CONTRACT_VOLUNTEER      = "VOLUNTEER"

CONTRACT_TYPES = (
    (CONTRACT_CDI,            "CDI"),
    (CONTRACT_CDD,            "CDD"),
    (CONTRACT_INTERNSHIP,     "Stage"),
    (CONTRACT_APPRENTICESHIP, "Alternance"),
    (CONTRACT_FREELANCE,      "Freelance"),
    (CONTRACT_PART_TIME,      "Temps partiel"),
    (CONTRACT_TEMPORARY,      "Interim"),
    (CONTRACT_VOLUNTEER,      "Benevolat"),
)

WORK_MODE_REMOTE = "REMOTE"
WORK_MODE_HYBRID = "HYBRID"
WORK_MODE_ONSITE = "ONSITE"

WORK_MODES = (
    (WORK_MODE_REMOTE, "Teletravail"),
    (WORK_MODE_HYBRID, "Hybride"),
    (WORK_MODE_ONSITE, "Presentiel"),
)

#: champ booleen du profil correspondant a chaque mode de travail
WORK_MODE_FIELDS = {
    WORK_MODE_REMOTE: "open_to_remote",
    WORK_MODE_HYBRID: "open_to_hybrid",
    WORK_MODE_ONSITE: "open_to_onsite",
}


# --------------------------------------------------------------------------- #
# Visibilite (section 11)
# --------------------------------------------------------------------------- #

VISIBILITY_PUBLIC           = "PUBLIC"
VISIBILITY_REGISTERED_USERS = "REGISTERED_USERS"
VISIBILITY_PRIVATE          = "PRIVATE"

VISIBILITIES = (
    (VISIBILITY_PUBLIC,           "Public"),
    (VISIBILITY_REGISTERED_USERS, "Utilisateurs inscrits"),
    (VISIBILITY_PRIVATE,          "Prive"),
)

#: ouverture croissante : un visiteur d'audience N voit tout ce qui est <= N
VISIBILITY_RANKS = {
    VISIBILITY_PUBLIC:           0,
    VISIBILITY_REGISTERED_USERS: 1,
    VISIBILITY_PRIVATE:          2,
}

#: audience d'un visiteur, comparee au rang ci-dessus
AUDIENCE_ANONYMOUS  = 0
AUDIENCE_REGISTERED = 1
AUDIENCE_OWNER      = 2

#: sections dont la visibilite se regle independamment (section 11)
SECTION_SKILLS         = "skills"
SECTION_EXPERIENCES    = "experiences"
SECTION_EDUCATION      = "education"
SECTION_CERTIFICATIONS = "certifications"
SECTION_LANGUAGES      = "languages"
SECTION_PROJECTS       = "projects"
SECTION_AVAILABILITY   = "availability"
SECTION_VIDEOS         = "videos"
SECTION_LINKS          = "links"

PROFILE_SECTIONS = (
    (SECTION_SKILLS,         "Competences"),
    (SECTION_EXPERIENCES,    "Experiences"),
    (SECTION_EDUCATION,      "Formations"),
    (SECTION_CERTIFICATIONS, "Certifications"),
    (SECTION_LANGUAGES,      "Langues"),
    (SECTION_PROJECTS,       "Projets"),
    (SECTION_AVAILABILITY,   "Disponibilite"),
    (SECTION_VIDEOS,         "Videos"),
    (SECTION_LINKS,          "Liens"),
)

#: nom du champ de `ProfileVisibility` portant chaque section
SECTION_VISIBILITY_FIELDS = {
    key: f"{key}_visibility" for key, _ in PROFILE_SECTIONS
}


# --------------------------------------------------------------------------- #
# Langues (section 8)
# --------------------------------------------------------------------------- #

CEFR_A1     = "A1"
CEFR_A2     = "A2"
CEFR_B1     = "B1"
CEFR_B2     = "B2"
CEFR_C1     = "C1"
CEFR_C2     = "C2"
CEFR_NATIVE = "NATIVE"

LANGUAGE_LEVELS = (
    (CEFR_A1,     "A1 - decouverte"),
    (CEFR_A2,     "A2 - survie"),
    (CEFR_B1,     "B1 - seuil"),
    (CEFR_B2,     "B2 - avance"),
    (CEFR_C1,     "C1 - autonome"),
    (CEFR_C2,     "C2 - maitrise"),
    (CEFR_NATIVE, "Langue maternelle"),
)

LANGUAGE_LEVEL_RANKS = {
    CEFR_A1: 1, CEFR_A2: 2, CEFR_B1: 3,
    CEFR_B2: 4, CEFR_C1: 5, CEFR_C2: 6, CEFR_NATIVE: 7,
}


def language_level_rank(level: str) -> int:
    return LANGUAGE_LEVEL_RANKS.get(level, 0)


# --------------------------------------------------------------------------- #
# Diplomes (section 6)
# --------------------------------------------------------------------------- #

DEGREE_NONE      = "NONE"
DEGREE_SECONDARY = "SECONDARY"
DEGREE_BAC       = "BAC"
DEGREE_BAC_2     = "BAC_2"
DEGREE_BAC_3     = "BAC_3"
DEGREE_BAC_5     = "BAC_5"
DEGREE_BAC_8     = "BAC_8"

DEGREE_LEVELS = (
    (DEGREE_NONE,      "Sans diplome"),
    (DEGREE_SECONDARY, "CAP, BEP"),
    (DEGREE_BAC,       "Baccalaureat"),
    (DEGREE_BAC_2,     "Bac +2"),
    (DEGREE_BAC_3,     "Bac +3 (licence)"),
    (DEGREE_BAC_5,     "Bac +5 (master, ingenieur)"),
    (DEGREE_BAC_8,     "Bac +8 (doctorat)"),
)

DEGREE_LEVEL_RANKS = {
    DEGREE_NONE: 0, DEGREE_SECONDARY: 1, DEGREE_BAC: 2, DEGREE_BAC_2: 3,
    DEGREE_BAC_3: 4, DEGREE_BAC_5: 5, DEGREE_BAC_8: 6,
}


def degree_level_rank(level: str) -> int:
    return DEGREE_LEVEL_RANKS.get(level, 0)


# --------------------------------------------------------------------------- #
# Liens professionnels (section 2)
# --------------------------------------------------------------------------- #

LINK_PORTFOLIO = "PORTFOLIO"
LINK_WEBSITE   = "WEBSITE"
LINK_GITHUB    = "GITHUB"
LINK_GITLAB    = "GITLAB"
LINK_LINKEDIN  = "LINKEDIN"
LINK_BEHANCE   = "BEHANCE"
LINK_DRIBBBLE  = "DRIBBBLE"
LINK_OTHER     = "OTHER"

LINK_KINDS = (
    (LINK_PORTFOLIO, "Portfolio"),
    (LINK_WEBSITE,   "Site web"),
    (LINK_GITHUB,    "GitHub"),
    (LINK_GITLAB,    "GitLab"),
    (LINK_LINKEDIN,  "LinkedIn"),
    (LINK_BEHANCE,   "Behance"),
    (LINK_DRIBBBLE,  "Dribbble"),
    (LINK_OTHER,     "Autre"),
)


# --------------------------------------------------------------------------- #
# Videos (sections 16 et 17)
# --------------------------------------------------------------------------- #

VIDEO_DRAFT      = "DRAFT"
VIDEO_PROCESSING = "PROCESSING"
VIDEO_PUBLISHED  = "PUBLISHED"
VIDEO_HIDDEN     = "HIDDEN"
VIDEO_DELETED    = "DELETED"

VIDEO_STATUSES = (
    (VIDEO_DRAFT,      "Brouillon"),
    (VIDEO_PROCESSING, "En traitement"),
    (VIDEO_PUBLISHED,  "Publiee"),
    (VIDEO_HIDDEN,     "Masquee"),
    (VIDEO_DELETED,    "Supprimee"),
)

#: seul statut dans lequel une video peut etre servie a un visiteur
VISIBLE_VIDEO_STATUSES = (VIDEO_PUBLISHED,)


# --------------------------------------------------------------------------- #
# Recherche (sections 12 a 14)
# --------------------------------------------------------------------------- #

MATCH_MODE_AND = "AND"
MATCH_MODE_OR  = "OR"

MATCH_MODES = (
    (MATCH_MODE_AND, "Toutes les competences"),
    (MATCH_MODE_OR,  "Au moins une competence"),
)

SORT_RELEVANCE  = "relevance"
SORT_EXPERIENCE = "experience"
SORT_RECENT     = "recent"
SORT_NAME       = "name"

SORT_OPTIONS = (
    (SORT_RELEVANCE,  "Pertinence"),
    (SORT_EXPERIENCE, "Experience"),
    (SORT_RECENT,     "Mis a jour recemment"),
    (SORT_NAME,       "Nom"),
)

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE     = 50

#: Poids du score de pertinence (section 14).
#:
#: Regles a preserver si ces valeurs bougent : une competence demandee de plus
#: doit peser davantage qu'un niveau plus eleve sur une competence deja
#: acquise, sans quoi un profil couvrant moins de competences pourrait passer
#: devant. D'ou W_SKILL_MATCH nettement superieur a W_SKILL_LEVEL * 4.
RANKING_WEIGHTS = {
    "skill_match":      100,   # par competence demandee effectivement detenue
    "skill_level":       10,   # par rang de niveau cumule sur ces competences
    "skill_years":        4,   # par annee d'experience sur ces competences
    "total_experience":   2,   # par annee d'experience professionnelle totale
    "availability":      25,   # profil en recherche active ou ouvert
    "field_match":       30,   # domaine professionnel demande
    "language_match":    15,   # par langue demandee au niveau requis
    "has_video":          5,   # reserve au futur feed video (section 18)
}

#: plafonds, pour qu'un critere secondaire ne submerge jamais les competences
RANKING_CAPS = {
    "skill_years":      10,
    "total_experience": 20,
}


# --------------------------------------------------------------------------- #
# Permissions applicatives
# --------------------------------------------------------------------------- #

PERM_MANAGE_SKILLS   = "profiles.manage_skill_catalog"
PERM_VIEW_PRIVATE    = "profiles.view_private_profile"
PERM_MODERATE        = "profiles.moderate_profile"

#: limites de saisie, appliquees cote serveur
MAX_SKILLS_PER_PROFILE = 100
MAX_YEARS_EXPERIENCE   = 60
MAX_SKILL_NAME_LENGTH  = 80


# --------------------------------------------------------------------------- #
# Referentiel de langues initial (section 8)
# --------------------------------------------------------------------------- #

#: langues chargees par la migration de donnees. La table reste ouverte : une
#: langue absente d'ici peut etre ajoutee sans migration.
SEED_LANGUAGES = (
    ("fr", "Francais"),   ("en", "Anglais"),    ("es", "Espagnol"),
    ("de", "Allemand"),   ("it", "Italien"),    ("pt", "Portugais"),
    ("nl", "Neerlandais"),("ru", "Russe"),      ("ar", "Arabe"),
    ("zh", "Chinois"),    ("ja", "Japonais"),   ("ko", "Coreen"),
    ("pl", "Polonais"),   ("tr", "Turc"),       ("sv", "Suedois"),
    ("da", "Danois"),     ("no", "Norvegien"),  ("fi", "Finnois"),
    ("el", "Grec"),       ("he", "Hebreu"),     ("hi", "Hindi"),
    ("ro", "Roumain"),    ("cs", "Tcheque"),    ("hu", "Hongrois"),
    ("uk", "Ukrainien"),  ("vi", "Vietnamien"), ("th", "Thai"),
    ("id", "Indonesien"), ("ca", "Catalan"),    ("bn", "Bengali"),
)
