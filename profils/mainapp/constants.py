##constants.py

# TODO: make these dicts?

ROLES = ("Recruiter", "JobSeeker", "Admin")
REACTIONS = ("like", "dislike")

VIDEOFILE_STORAGE_PATH = "videos/"
MINIMUM_REGISTRATION_AGE = 18

# Moderation minimale du feed video (spec "Moderation video, presentation,
# messagerie et notifications", section 1) : aucune video n'est visible du
# feed recruteur/admin avant validation. "PENDING" en premiere position fixe
# le defaut du champ (voir `strings_to_choice_char_fields`).
VIDEO_LINK_PENDING  = "PENDING"
VIDEO_LINK_APPROVED = "APPROVED"
VIDEO_LINK_REJECTED = "REJECTED"

VIDEO_LINK_STATUSES = (VIDEO_LINK_PENDING, VIDEO_LINK_APPROVED, VIDEO_LINK_REJECTED)
