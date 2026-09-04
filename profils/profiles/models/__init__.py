"""Modeles des profils professionnels.

Le modele est normalise : competences, experiences, formations,
certifications, langues, projets et videos sont de vraies tables reliees a un
referentiel commun (`Skill`, `Language`). Aucune de ces donnees n'est stockee
comme du texte libre, faute de quoi la recherche par competence de la section
12 serait impossible a rendre performante.

Relations :

    User
     └── ProfessionalProfile
          ├── ProfileVisibility          (visibilite par section)
          ├── ProfileSearchSettings      (searchable)
          ├── ProfileContractType        (contrats recherches)
          ├── ProfileLink                (portfolio, liens)
          ├── UserSkill        ──> Skill ──> SkillAlias
          ├── WorkExperience
          │    └── WorkExperienceSkill   ──> Skill
          ├── Education
          │    └── EducationSkill        ──> Skill
          ├── Certification
          │    └── CertificationSkill    ──> Skill
          ├── UserLanguage     ──> Language
          ├── Project
          │    └── ProjectSkill          ──> Skill
          └── ProfileVideo
               └── ProfileVideoSkill     ──> Skill
"""

from .profile import (
    ProfessionalProfile,
    ProfileContractType,
    ProfileLink,
    ProfileSearchSettings,
    ProfileVisibility,
)
from .skill import Skill, SkillAlias, SkillLink, UserSkill
from .background import (
    Certification,
    CertificationSkill,
    Education,
    EducationSkill,
    Project,
    ProjectSkill,
    WorkExperience,
    WorkExperienceSkill,
)
from .language import Language, UserLanguage
from .video import (
    ProfileVideo,
    ProfileVideoReaction,
    ProfileVideoSkill,
    ProfileVideoView,
    VideoModerationEvent,
)

__all__ = [
    "ProfessionalProfile",
    "ProfileVisibility",
    "ProfileSearchSettings",
    "ProfileContractType",
    "ProfileLink",
    "Skill",
    "SkillAlias",
    "SkillLink",
    "UserSkill",
    "WorkExperience",
    "WorkExperienceSkill",
    "Education",
    "EducationSkill",
    "Certification",
    "CertificationSkill",
    "Project",
    "ProjectSkill",
    "Language",
    "UserLanguage",
    "ProfileVideo",
    "ProfileVideoReaction",
    "ProfileVideoSkill",
    "ProfileVideoView",
    "VideoModerationEvent",
]
